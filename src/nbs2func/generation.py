from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Nbs2FuncConfig
from .core.instrument_mapping import validate_song_instruments_for_version
from .core.minecraft_version import (
    MinecraftVersionError,
    get_minecraft_version_profile,
    write_pack_mcmeta,
)
from .core.nbs_reader import read_nbs
from .core.tempo_control import (
    TempoControlError,
    build_tempo_control_report,
    tempo_report_lines,
)
from .layout import build_layout_strategy, layout_song
from .layout.geometry import BlockPosition, LayoutError
from .layout.models import LayoutProgressEvent, StereoLayoutConfig
from .modules.playback_assist import (
    PlaybackAssistModuleConfig,
    playback_assist_debug_info,
    total_track_length_from_layout,
)
from .output.block_builder import (
    RUNTIME_LOGIC_BUILD_PLAN,
    STRUCTURE_ONLY_BUILD_PLAN,
    STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN,
    build_generated_plan,
    filter_generated_plan,
)
from .output.command_writer import CommandWriterConfig, write_mcfunction
from .output.schematic_writer import (
    resolve_schematic_origin,
    schematic_warnings,
    write_schematic,
)


@dataclass(frozen=True)
class GenerationEvent:
    kind: str
    message: str
    detail: str | None = None
    current: int | None = None
    total: int | None = None
    key: str | None = None
    overall_current: int | None = None
    overall_total: int | None = None
    overall_percent: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    output_format: str
    datapack_path: Path | None = None
    schematic_path: Path | None = None
    warnings: tuple[str, ...] = ()
    diagnostics: GenerationDiagnostics | None = None


@dataclass(frozen=True)
class GenerationDiagnostics:
    song: object
    layout: object
    write_result: object | None = None
    writer_output_path: Path | None = None
    tempo_report: object | None = None
    playback_debug: object | None = None
    schematic_origin: BlockPosition | None = None
    schematic_warnings: tuple[str, ...] = ()
    profile_report: str | None = None


ProgressCallback = Callable[[GenerationEvent], None]


def emit(
    callback: ProgressCallback | None,
    kind: str,
    message: str,
    detail: str | None = None,
    current: int | None = None,
    total: int | None = None,
    key: str | None = None,
    overall_current: int | None = None,
    overall_total: int | None = None,
    overall_percent: float | None = None,
    unit: str | None = None,
) -> None:
    if callback is not None:
        callback(
            GenerationEvent(
                kind=kind,
                message=message,
                detail=detail,
                current=current,
                total=total,
                key=key,
                overall_current=overall_current,
                overall_total=overall_total,
                overall_percent=overall_percent,
                unit=unit,
            )
        )


OVERALL_STAGE_RANGES: dict[str, tuple[float, float]] = {
    "read_nbs": (0.0, 5.0),
    "validate_config": (5.0, 8.0),
    "candidate_generation": (8.0, 20.0),
    "pass1_assignment_validation": (20.0, 35.0),
    "pass2_retry_candidates": (35.0, 42.0),
    "pass2_assignment_validation": (42.0, 48.0),
    "pass3_retry_candidates": (48.0, 52.0),
    "pass3_assignment_validation": (52.0, 55.0),
    "build_layout": (8.0, 55.0),
    "build_block_plan": (55.0, 75.0),
    "write_datapack": (75.0, 95.0),
    "write_schematic": (95.0, 98.0),
    "write_outputs": (75.0, 98.0),
    "done": (100.0, 100.0),
}


def overall_percent_for_stage(
    stage_key: str,
    current: int | None = None,
    total: int | None = None,
) -> float:
    start, end = OVERALL_STAGE_RANGES.get(stage_key, (0.0, 100.0))
    if total is None or total <= 0 or current is None:
        return start
    ratio = max(0.0, min(1.0, current / total))
    return start + (end - start) * ratio


def monotonic_overall_progress(
    previous: float,
    incoming: float | None,
    *,
    done: bool = False,
) -> float:
    if done:
        return 100.0
    if incoming is None:
        return previous
    return max(previous, incoming)


def generate_from_config(
    config: Nbs2FuncConfig,
    progress_callback: ProgressCallback | None = None,
    *,
    include_diagnostics: bool = False,
) -> GenerationResult:
    """Generate nbs2func outputs from a resolved config."""

    try:
        args = _args_namespace_from_config(config)
        path = Path(args.file)
        overall_percent = 0.0

        def emit_progress(
            stage_key: str,
            message: str,
            *,
            current: int | None = None,
            total: int | None = None,
            unit: str | None = None,
            key: str | None = None,
            detail: str | None = None,
        ) -> None:
            nonlocal overall_percent
            incoming = overall_percent_for_stage(stage_key, current, total)
            overall_percent = monotonic_overall_progress(overall_percent, incoming)
            emit(
                progress_callback,
                "progress",
                message,
                detail=detail or stage_key,
                current=current,
                total=total,
                key=key or stage_key,
                overall_percent=overall_percent,
                unit=unit,
            )

        emit(progress_callback, "phase", "Validating config...")
        emit_progress("validate_config", "Validating config", current=0, total=1)
        version_profile = get_minecraft_version_profile(args.minecraft_version)
        if args.tempo_control_mode == "command" and not args.enable_playback_assist:
            raise ValueError(
                "--tempo-control-mode command requires --enable-playback-assist so "
                "the tick rate command has a playback start command block."
            )
        if not path.exists():
            raise FileNotFoundError(
                f"NBS file not found: {path}. Pass a valid .nbs path, or run "
                "without arguments to use examples/demo.nbs."
            )
        if not path.is_file():
            raise ValueError(f"path is not a file: {path}")
        emit_progress("validate_config", "Validating config", current=1, total=1)

        emit(progress_callback, "phase", "Reading NBS file...")
        emit_progress("read_nbs", "Reading NBS file", current=0, total=1)
        song = read_nbs(path)
        emit_progress("read_nbs", "Reading NBS file", current=1, total=1)

        tempo_report = None
        if args.tempo_control_mode != "none":
            tempo_report = build_tempo_control_report(
                song,
                minecraft_version_profile=version_profile,
                backend=args.tempo_control_backend,
                rate_decimals=args.tempo_rate_decimals,
                game_ticks_per_song_tick=args.game_ticks_per_song_tick,
            )
            for line in tempo_report_lines(tempo_report):
                emit(progress_callback, "notice", line)
            if args.tempo_control_mode == "report":
                emit(
                    progress_callback,
                    "notice",
                    "Mode: report only; no tick rate command will be generated.",
                )
            elif args.tempo_control_mode == "command":
                emit(
                    progress_callback,
                    "notice",
                    "Mode: command; playback assist will set the tick rate on start.",
                )

        validate_song_instruments_for_version(song, version_profile)

        emit(progress_callback, "phase", "Building layout...")
        emit_progress("build_layout", "Building layout", current=0, total=1)
        def layout_progress(event: LayoutProgressEvent) -> None:
            emit_progress(
                event.stage,
                event.message,
                detail=event.stage,
                current=event.current,
                total=event.total,
                unit=event.unit,
                key=event.key,
            )

        strategy = build_layout_strategy(
            mode=args.layout_mode,
            origin=BlockPosition(args.origin_x, args.origin_y, args.origin_z),
            track_direction=args.direction,
            selected_track_id=args.track_id,
            stereo_config=_stereo_layout_config(
                args,
                enable_progress_logging=(
                    include_diagnostics and args.layout_mode == "note_based_stereo"
                ),
                progress_callback=layout_progress
                if progress_callback is not None
                else None,
            ),
        )
        profile_report = None
        profiler = cProfile.Profile() if args.profile and include_diagnostics else None
        if profiler is not None:
            profiler.enable()
        try:
            layout = layout_song(song, strategy)
        finally:
            if profiler is not None:
                profiler.disable()
                profile_report = _profile_report_text(profiler)
        if layout.collisions:
            raise LayoutError(
                "Did not generate output because block collision errors were found."
            )
        if (
            layout.note_based_preview is not None
            and layout.note_based_preview.failed_assignment_count > 0
        ):
            raise LayoutError(
                "Did not generate output because some emitters were not assigned."
            )
        emit_progress("build_layout", "Building layout", current=1, total=1)

        emit(progress_callback, "phase", "Building block plan...")
        block_plan_total = _block_plan_progress_total(layout)
        emit_progress(
            "build_block_plan",
            "Building block plan",
            current=0,
            total=block_plan_total,
            unit="cells",
        )
        playback_config, playback_total_track_length = _playback_config(
            args,
            layout,
            version_profile,
            tempo_report,
        )
        playback_debug = None
        if args.enable_playback_assist:
            playback_debug = playback_assist_debug_info(playback_config)

        output_root = Path(args.output)
        datapack_name = args.datapack_name or path.stem
        datapack_root = output_root / sanitize_output_folder_name(datapack_name)
        writer_output_path = datapack_root
        writer_config = _writer_config(
            args,
            version_profile,
            tempo_report,
            playback_config,
            playback_total_track_length,
        )
        def block_plan_progress(current: int, total: int) -> None:
            emit_progress(
                "build_block_plan",
                "Building block plan",
                current=current,
                total=total,
                unit="cells",
            )

        full_build_plan = build_generated_plan(
            layout,
            writer_config,
            progress_callback=block_plan_progress
            if progress_callback is not None
            else None,
        )
        datapack_plan = full_build_plan
        schematic_plan = (
            filter_generated_plan(full_build_plan, STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN)
            if args.output_format == "both"
            else filter_generated_plan(full_build_plan, STRUCTURE_ONLY_BUILD_PLAN)
        )
        runtime_plan = filter_generated_plan(full_build_plan, RUNTIME_LOGIC_BUILD_PLAN)

        datapack_path: Path | None = None
        schematic_path: Path | None = None
        schematic_origin: BlockPosition | None = None
        write_result = None
        warnings: list[str] = []

        if args.output_format in {"datapack", "both"}:
            emit(progress_callback, "phase", "Writing datapack...")
            emit_progress(
                "write_datapack",
                "Writing datapack",
                current=0,
                total=1,
                unit="files",
            )
            _clean_datapack_build_dir(datapack_root, args, version_profile)
            if args.no_split_functions:
                write_pack_mcmeta(datapack_root, version_profile)
                writer_output_path = (
                    datapack_root
                    / "data"
                    / args.function_namespace
                    / version_profile.function_dir_name
                    / args.build_function_dir
                    / "start.mcfunction"
                )
            def datapack_progress(current: int, total: int, message: str) -> None:
                emit_progress(
                    "write_datapack",
                    message,
                    current=current,
                    total=total,
                    unit="files",
                )

            write_result = write_mcfunction(
                layout,
                writer_output_path,
                writer_config,
                plan=(runtime_plan if args.output_format == "both" else datapack_plan),
                progress_callback=datapack_progress
                if progress_callback is not None
                else None,
            )
            datapack_path = datapack_root
            emit(progress_callback, "output", f"Generated datapack: {datapack_root}")
            if args.no_split_functions:
                emit(
                    progress_callback,
                    "output",
                    f"Generated mcfunction: {writer_output_path}",
                )

        if args.output_format in {"schem", "both"}:
            emit(progress_callback, "phase", "Writing schematic...")
            emit_progress(
                "write_schematic",
                "Writing schematic",
                current=0,
                total=max(1, len(schematic_plan.blocks)),
                unit="blocks",
            )
            generation_origin = BlockPosition(args.origin_x, args.origin_y, args.origin_z)
            schematic_origin = resolve_schematic_origin(
                schematic_plan,
                args.schematic_origin_mode,
                generation_origin,
            )
            schematic_output = (
                Path(args.schematic_output)
                if args.schematic_output is not None
                else output_root / f"{sanitize_datapack_name(path.stem)}.schem"
            )
            schematic_path = write_schematic(
                schematic_plan,
                schematic_output,
                version_profile=version_profile,
                schematic_origin=schematic_origin,
                schematic_name=args.schematic_name,
            )
            emit_progress(
                "write_schematic",
                "Writing schematic",
                current=max(1, len(schematic_plan.blocks)),
                total=max(1, len(schematic_plan.blocks)),
                unit="blocks",
            )
            emit(progress_callback, "output", f"Generated schematic: {schematic_path}")
            emit(
                progress_callback,
                "output",
                f"  schematic origin: {_format_position(schematic_origin)}",
            )
            if args.output_format == "schem" and (
                args.enable_starter_module or args.enable_playback_assist
            ):
                warnings.extend(
                    (
                        "Schematic output does not include starter or playback "
                        "assist modules.",
                        "These modules require mcfunction support to execute runtime logic.",
                    )
                )
            if args.output_format == "both":
                emit(
                    progress_callback,
                    "notice",
                    "The .schem file contains all blocks including command blocks.",
                )
                emit(
                    progress_callback,
                    "notice",
                    "The .mcfunction output contains runtime logic such as scoreboard, "
                    "summon, and execute.",
                )
            warnings.extend(schematic_warnings(schematic_plan))

        for warning in warnings:
            emit(progress_callback, "warning", warning)

        diagnostics = None
        if include_diagnostics:
            diagnostics = GenerationDiagnostics(
                song=song,
                layout=layout,
                write_result=write_result,
                writer_output_path=writer_output_path if write_result is not None else None,
                tempo_report=tempo_report,
                playback_debug=playback_debug,
                schematic_origin=schematic_origin,
                schematic_warnings=tuple(warnings),
                profile_report=profile_report,
            )
        return GenerationResult(
            output_format=args.output_format,
            datapack_path=datapack_path,
            schematic_path=schematic_path,
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )
    except Exception as exc:
        emit(progress_callback, "error", str(exc))
        raise


def sanitize_datapack_name(name: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]+", "_", name.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "nbs_song"


def sanitize_output_folder_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join(
        "_"
        if char in invalid or ord(char) < 32
        else char
        for char in name
    )
    cleaned = cleaned.strip().strip(".")
    return cleaned or "nbs_song"


def _clean_datapack_build_dir(
    datapack_root: Path,
    args: argparse.Namespace,
    version_profile,
) -> None:
    build_dir = (
        datapack_root
        / "data"
        / args.function_namespace
        / version_profile.function_dir_name
        / args.build_function_dir
    )
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
        except OSError as exc:
            raise OSError(f"Could not clean old build output {build_dir}: {exc}") from exc


def _block_plan_progress_total(layout) -> int:
    if getattr(layout, "note_based_preview", None) is not None:
        return max(1, len(layout.note_based_preview.assignments))
    return max(1, len(layout.cells))


def _profile_report_text(profiler: cProfile.Profile) -> str:
    output = io.StringIO()
    stats = pstats.Stats(profiler, stream=output)
    stats.strip_dirs().sort_stats("cumulative").print_stats(30)
    return output.getvalue()


def _stereo_layout_config(
    args: argparse.Namespace,
    *,
    enable_progress_logging: bool = False,
    progress_callback=None,
) -> StereoLayoutConfig:
    return StereoLayoutConfig(
        max_hearing_distance=args.max_hearing_distance,
        min_distance=args.min_distance,
        max_stereo_angle_degrees=args.max_stereo_angle_degrees,
        center_threshold=args.center_threshold,
        center_split_policy=args.center_split_policy,
        center_split_overrides=_parse_center_split_overrides(args.center_split_override),
        center_split_mode=args.center_split_mode,
        center_split_pan=args.center_split_pan,
        max_auto_center_splits=args.max_auto_center_splits,
        enable_collision_resolver=not args.disable_collision_resolver,
        enable_depth_mirror_fallback=not args.disable_depth_mirror_fallback,
        enable_radius_relax_fallback=not args.disable_radius_relax_fallback,
        max_angle_deviation_degrees=args.max_angle_deviation_degrees,
        angle_search_step_degrees=args.angle_search_step_degrees,
        radius_relax_step=args.radius_relax_step,
        max_radius_relax=args.max_radius_relax,
        min_world_y=args.min_world_y,
        max_world_y=args.max_world_y,
        enable_pan_zone_layout=not args.disable_pan_zone_layout,
        allow_adjacent_pan_zone_fallback=args.allow_adjacent_pan_zone_fallback,
        pan_zone_search_radius_limit=args.pan_zone_search_radius_limit,
        max_candidates_per_emitter=args.max_candidates_per_emitter,
        max_candidate_y_layers=args.max_candidate_y_layers,
        max_candidate_lateral_positions=args.max_candidate_lateral_positions,
        radius_search_tolerance=args.radius_search_tolerance,
        max_lateral_distance=args.max_lateral_distance,
        pan_zone_reference_radius=args.pan_zone_reference_radius,
        enable_depth_mirror_candidates=not args.disable_depth_mirror_candidates,
        preferred_depth_sign=args.preferred_depth_sign,
        allow_negative_depth_offsets=not args.disallow_negative_depth_offsets,
        depth_mirror_penalty=args.depth_mirror_penalty,
        lateral_step_penalty=args.lateral_step_penalty,
        allow_adjacent_pan_zone_fallback_for_failed=(
            not args.disable_adjacent_pan_zone_fallback_for_failed
        ),
        retry_max_candidates_per_emitter=args.retry_max_candidates_per_emitter,
        enable_same_side_zone_split_fallback=args.enable_same_side_zone_split_fallback,
        same_side_split_volume_factor=args.same_side_split_volume_factor,
        min_rail_center_y_gap=args.min_rail_center_y_gap,
        activation_slot_radius=args.activation_slot_radius,
        max_collision_records=args.max_collision_records,
        max_collision_examples_per_group=args.max_collision_examples_per_group,
        preview_time_limit_seconds=args.preview_time_limit_seconds,
        fail_fast_on_too_many_collisions=not args.no_fail_fast_on_too_many_collisions,
        max_collision_records_before_abort=args.max_collision_records_before_abort,
        enable_progress_logging=enable_progress_logging,
        progress_callback=progress_callback,
        enable_note_level_center_split=not args.disable_note_level_center_split,
        center_split_left_pan=args.center_split_left_pan,
        center_split_right_pan=args.center_split_right_pan,
        center_split_volume_factor=args.center_split_volume_factor,
        max_note_level_center_splits=args.max_note_level_center_splits,
    )


def _playback_config(
    args: argparse.Namespace,
    layout,
    version_profile,
    tempo_report,
) -> tuple[PlaybackAssistModuleConfig, int]:
    music_start_position = BlockPosition(
        args.music_start_x,
        args.music_start_y,
        args.music_start_z,
    )
    playback_total_track_length = total_track_length_from_layout(
        layout,
        args.direction,
        music_start_position,
    )
    return (
        PlaybackAssistModuleConfig(
            enable_playback_assist=args.enable_playback_assist,
            player_name=args.playback_player_name,
            playback_vehicle_tag=args.playback_vehicle_tag,
            starter_tag=args.starter_tag,
            count_objective=args.count_objective,
            vehicle_spawn_position=_optional_position(
                args.vehicle_spawn_x,
                args.vehicle_spawn_y,
                args.vehicle_spawn_z,
            ),
            music_start_position=music_start_position,
            command_module_origin=_optional_position(
                args.command_module_origin_x,
                args.command_module_origin_y,
                args.command_module_origin_z,
            ),
            track_direction=args.direction,
            total_track_length=playback_total_track_length,
            generate_playback_buttons=not args.no_playback_buttons,
            playback_button_block=args.playback_button_block,
            prepare_button_position=_optional_position(
                args.prepare_button_x,
                args.prepare_button_y,
                args.prepare_button_z,
            ),
            start_button_position=_optional_position(
                args.start_button_x,
                args.start_button_y,
                args.start_button_z,
            ),
            minecraft_version_profile=version_profile,
            tempo_control_mode=args.tempo_control_mode,
            tempo_control_report=tempo_report,
            reset_tick_rate_after_playback=not args.no_reset_tick_rate_after_playback,
        ),
        playback_total_track_length,
    )


def _writer_config(
    args: argparse.Namespace,
    version_profile,
    tempo_report,
    playback_config: PlaybackAssistModuleConfig,
    playback_total_track_length: int,
) -> CommandWriterConfig:
    return CommandWriterConfig(
        enable_starter_module=args.enable_starter_module or args.enable_playback_assist,
        command_block_position=BlockPosition(
            args.command_block_x,
            args.command_block_y,
            args.command_block_z,
        ),
        starter_tag=args.starter_tag,
        starter_track_block=args.starter_track_block,
        starter_cell_offset=args.starter_cell_offset,
        split_functions=not args.no_split_functions,
        function_namespace=args.function_namespace,
        build_function_dir=args.build_function_dir,
        minecraft_version_profile=version_profile,
        max_commands_per_build_part=args.max_commands_per_build_part,
        schedule_delay_ticks_between_parts=args.schedule_delay_ticks_between_parts,
        build_player_name=args.build_player_name,
        player_load_radius_chunks=args.player_load_radius_chunks,
        player_tp_chunk_load_wait_ticks=args.player_tp_chunk_load_wait_ticks,
        player_tp_after_build_wait_ticks=args.player_tp_after_build_wait_ticks,
        player_tp_window_length_blocks=args.player_tp_window_length_blocks,
        player_tp_window_lateral_width_blocks=args.player_tp_window_lateral_width_blocks,
        build_tp_y=args.build_tp_y,
        build_finish_tp_position=_optional_position(
            args.build_finish_tp_x,
            args.build_finish_tp_y,
            args.build_finish_tp_z,
        ),
        enable_playback_assist=args.enable_playback_assist,
        playback_player_name=args.playback_player_name,
        playback_vehicle_tag=args.playback_vehicle_tag,
        count_objective=args.count_objective,
        vehicle_spawn_position=playback_config.vehicle_spawn_position,
        music_start_position=playback_config.music_start_position,
        command_module_origin=playback_config.command_module_origin,
        playback_track_direction=args.direction,
        playback_total_track_length=playback_total_track_length,
        generate_playback_buttons=not args.no_playback_buttons,
        playback_button_block=args.playback_button_block,
        prepare_button_position=playback_config.prepare_button_position,
        start_button_position=playback_config.start_button_position,
        requested_origin_y=args.origin_y,
        tempo_control_mode=args.tempo_control_mode,
        tempo_control_report=tempo_report,
        reset_tick_rate_after_playback=not args.no_reset_tick_rate_after_playback,
    )


def _format_position(position: BlockPosition) -> str:
    return f"({position.x},{position.y},{position.z})"


def _optional_position(
    x: int | None,
    y: int | None,
    z: int | None,
) -> BlockPosition | None:
    if x is None and y is None and z is None:
        return None
    if x is None or y is None or z is None:
        raise ValueError("Custom positions require X, Y, and Z.")
    return BlockPosition(x, y, z)


def _parse_center_split_overrides(values: list[str]) -> dict[int, str]:
    overrides: dict[int, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(
                "center_split_override must use TRACK_ID=split or TRACK_ID=none"
            )
        raw_track_id, raw_action = value.split("=", 1)
        try:
            track_id = int(raw_track_id)
        except ValueError as exc:
            raise ValueError(
                f"Invalid center split override track id: {raw_track_id!r}"
            ) from exc
        action = raw_action.strip().lower()
        if action not in {"split", "none"}:
            raise ValueError(
                f"Invalid center split override for track {track_id}: {raw_action!r}"
            )
        overrides[track_id] = action
    return overrides


def _args_namespace_from_config(config: Nbs2FuncConfig) -> argparse.Namespace:
    overrides = config.center_split_overrides or {}
    return argparse.Namespace(
        file=config.input_path,
        output=config.output,
        datapack_name=config.datapack_name,
        output_format=config.output_format,
        schematic_origin_mode=config.schematic_origin_mode,
        schematic_output=config.schematic_output,
        schematic_name=config.schematic_name,
        analyze_stereo=config.analyze_stereo,
        analyze_layout_spatial=config.analyze_layout_spatial,
        group_config=config.group_config,
        analysis_output=config.analysis_output,
        analysis_window_size=config.analysis_window_size,
        analysis_hop_size=config.analysis_hop_size,
        analysis_detail=config.analysis_detail,
        origin_x=config.origin_x,
        origin_y=config.origin_y,
        origin_z=config.origin_z,
        layout_mode=config.layout_mode,
        track_id=config.track_id,
        direction=config.direction,
        max_hearing_distance=config.max_hearing_distance,
        min_distance=config.min_distance,
        max_stereo_angle_degrees=config.max_stereo_angle_degrees,
        center_threshold=config.center_threshold,
        center_split_policy=config.center_split_policy,
        center_split_mode=config.center_split_mode,
        center_split_override=[
            f"{track_id}={action}"
            for track_id, action in sorted(overrides.items())
        ],
        center_split_pan=config.center_split_pan,
        max_auto_center_splits=config.max_auto_center_splits,
        disable_collision_resolver=not config.enable_collision_resolver,
        disable_depth_mirror_fallback=not config.enable_depth_mirror_fallback,
        disable_radius_relax_fallback=not config.enable_radius_relax_fallback,
        max_angle_deviation_degrees=config.max_angle_deviation_degrees,
        angle_search_step_degrees=config.angle_search_step_degrees,
        radius_relax_step=config.radius_relax_step,
        max_radius_relax=config.max_radius_relax,
        min_world_y=config.min_world_y,
        max_world_y=config.max_world_y,
        disable_pan_zone_layout=not config.enable_pan_zone_layout,
        allow_adjacent_pan_zone_fallback=config.allow_adjacent_pan_zone_fallback,
        pan_zone_search_radius_limit=config.pan_zone_search_radius_limit,
        max_candidates_per_emitter=config.max_candidates_per_emitter,
        max_candidate_y_layers=config.max_candidate_y_layers,
        max_candidate_lateral_positions=config.max_candidate_lateral_positions,
        radius_search_tolerance=config.radius_search_tolerance,
        max_lateral_distance=config.max_lateral_distance,
        pan_zone_reference_radius=config.pan_zone_reference_radius,
        disable_depth_mirror_candidates=not config.enable_depth_mirror_candidates,
        preferred_depth_sign=config.preferred_depth_sign,
        disallow_negative_depth_offsets=not config.allow_negative_depth_offsets,
        depth_mirror_penalty=config.depth_mirror_penalty,
        lateral_step_penalty=config.lateral_step_penalty,
        disable_adjacent_pan_zone_fallback_for_failed=(
            not config.allow_adjacent_pan_zone_fallback_for_failed
        ),
        retry_max_candidates_per_emitter=config.retry_max_candidates_per_emitter,
        enable_same_side_zone_split_fallback=config.enable_same_side_zone_split_fallback,
        same_side_split_volume_factor=config.same_side_split_volume_factor,
        min_rail_center_y_gap=config.min_rail_center_y_gap,
        activation_slot_radius=config.activation_slot_radius,
        max_collision_records=config.max_collision_records,
        max_collision_examples_per_group=config.max_collision_examples_per_group,
        preview_time_limit_seconds=config.preview_time_limit_seconds,
        no_fail_fast_on_too_many_collisions=not config.fail_fast_on_too_many_collisions,
        max_collision_records_before_abort=config.max_collision_records_before_abort,
        profile=config.profile,
        disable_note_level_center_split=not config.enable_note_level_center_split,
        center_split_left_pan=config.center_split_left_pan,
        center_split_right_pan=config.center_split_right_pan,
        center_split_volume_factor=config.center_split_volume_factor,
        max_note_level_center_splits=config.max_note_level_center_splits,
        enable_starter_module=config.enable_starter_module,
        command_block_x=config.command_block_x,
        command_block_y=config.command_block_y,
        command_block_z=config.command_block_z,
        starter_tag=config.starter_tag,
        starter_track_block=config.starter_track_block,
        starter_cell_offset=config.starter_cell_offset,
        enable_playback_assist=config.enable_playback_assist,
        playback_player_name=config.playback_player_name,
        playback_vehicle_tag=config.playback_vehicle_tag,
        count_objective=config.count_objective,
        vehicle_spawn_x=config.vehicle_spawn_x,
        vehicle_spawn_y=config.vehicle_spawn_y,
        vehicle_spawn_z=config.vehicle_spawn_z,
        music_start_x=config.music_start_x,
        music_start_y=config.music_start_y,
        music_start_z=config.music_start_z,
        command_module_origin_x=config.command_module_origin_x,
        command_module_origin_y=config.command_module_origin_y,
        command_module_origin_z=config.command_module_origin_z,
        no_playback_buttons=not config.generate_playback_buttons,
        playback_button_block=config.playback_button_block,
        prepare_button_x=config.prepare_button_x,
        prepare_button_y=config.prepare_button_y,
        prepare_button_z=config.prepare_button_z,
        start_button_x=config.start_button_x,
        start_button_y=config.start_button_y,
        start_button_z=config.start_button_z,
        no_split_functions=not config.split_functions,
        max_commands_per_build_part=config.max_commands_per_build_part,
        schedule_delay_ticks_between_parts=config.schedule_delay_ticks_between_parts,
        build_player_name=config.build_player_name,
        player_load_radius_chunks=config.player_load_radius_chunks,
        player_tp_chunk_load_wait_ticks=config.player_tp_chunk_load_wait_ticks,
        player_tp_after_build_wait_ticks=config.player_tp_after_build_wait_ticks,
        player_tp_window_length_blocks=config.player_tp_window_length_blocks,
        player_tp_window_lateral_width_blocks=config.player_tp_window_lateral_width_blocks,
        build_tp_y=config.build_tp_y,
        build_finish_tp_x=config.build_finish_tp_x,
        build_finish_tp_y=config.build_finish_tp_y,
        build_finish_tp_z=config.build_finish_tp_z,
        function_namespace=config.function_namespace,
        build_function_dir=config.build_function_dir,
        minecraft_version=config.minecraft_version,
        tempo_control_mode=config.tempo_control_mode,
        tempo_control_backend=config.tempo_control_backend,
        tempo_rate_decimals=config.tempo_rate_decimals,
        game_ticks_per_song_tick=config.game_ticks_per_song_tick,
        no_reset_tick_rate_after_playback=not config.reset_tick_rate_after_playback,
    )
