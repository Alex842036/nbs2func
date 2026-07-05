from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

from .instrument_mapping import get_instrument_block, has_instrument_mapping
from .instrument_mapping import get_required_support_block
from .layout_models import (
    LayoutCell,
    LayoutResult,
    NoteBasedStereoRailLayoutPreview,
    SlotAssignment,
)
from .minecraft_version import (
    DEFAULT_MINECRAFT_VERSION_PROFILE,
    MinecraftVersionError,
    MinecraftVersionProfile,
    write_pack_mcmeta,
)
from .layout_geometry import (
    DIRECTION_VECTORS,
    BlockPosition,
    _right_hand_lateral_vector,
    _scale_vector,
    add_vector,
    add_y,
    below,
    normalize_direction,
    opposite_direction,
    repeater_position_from_note_position,
)
from .playback_assist_module import (
    PlaybackAssistModuleConfig,
    playback_assist_lines,
    total_track_length_from_layout,
)
from .tempo_control import TempoControlReport
from .starter_module import StarterModuleConfig, starter_module_lines


@dataclass(frozen=True)
class CommandWriterConfig:
    """Settings for translating resolved layout cells into commands."""

    track_block: str = "stone"
    repeater_block: str = "repeater"
    enable_starter_module: bool = False
    command_block_position: BlockPosition = BlockPosition(-10, 128, 0)
    starter_tag: str = "nbs_starter"
    starter_track_block: str | None = None
    starter_cell_offset: int = -1
    split_functions: bool = True
    function_namespace: str = "nbs"
    build_function_dir: str = "build"
    minecraft_version_profile: MinecraftVersionProfile = (
        DEFAULT_MINECRAFT_VERSION_PROFILE
    )
    max_commands_per_build_part: int = 500
    schedule_delay_ticks_between_parts: int = 10
    build_player_name: str = "Alex842036"
    player_load_radius_chunks: int = 6
    player_tp_chunk_load_wait_ticks: int = 100
    player_tp_after_build_wait_ticks: int = 20
    player_tp_window_length_blocks: int = 192
    player_tp_window_lateral_width_blocks: int = 192
    build_tp_y: int | None = None
    build_finish_tp_position: BlockPosition | None = None
    enable_playback_assist: bool = False
    playback_player_name: str = "Alex842036"
    playback_vehicle_tag: str = "playback_vehicle"
    count_objective: str = "count"
    vehicle_spawn_position: BlockPosition | None = None
    music_start_position: BlockPosition = BlockPosition(0, 128, 0)
    command_module_origin: BlockPosition | None = None
    playback_track_direction: str = "east"
    playback_total_track_length: int | None = None
    generate_playback_buttons: bool = True
    playback_button_block: str = "minecraft:stone_button"
    prepare_button_position: BlockPosition | None = None
    start_button_position: BlockPosition | None = None
    requested_origin_y: int | None = None
    tempo_control_mode: str = "report"
    tempo_control_report: TempoControlReport | None = None
    reset_tick_rate_after_playback: bool = True


@dataclass(frozen=True)
class CommandWriteResult:
    """Debug information about generated mcfunction output."""

    total_commands: int
    split_function_parts: int
    player_tp_build: PlayerTpBuildDebug | None = None


@dataclass(frozen=True)
class BuildBoundingBox:
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int


@dataclass(frozen=True)
class PlayerTpWindowDebug:
    window_index: int
    center_position: BlockPosition
    bounding_box: BuildBoundingBox
    command_count: int
    part_count: int


@dataclass(frozen=True)
class PlayerTpBuildDebug:
    build_bounding_box: BuildBoundingBox
    track_direction: str
    split_axis: str
    build_player_name: str
    player_load_radius_chunks: int
    player_tp_window_length_blocks: int
    player_tp_window_lateral_width_blocks: int
    total_windows: int
    total_commands: int
    max_commands_per_part: int
    total_parts: int
    wait_ticks_before_build: int
    wait_ticks_after_build: int
    schedule_delay_ticks_between_parts: int
    estimated_total_build_ticks: int
    windows: tuple[PlayerTpWindowDebug, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _BuildCommandPacket:
    lines: tuple[str, ...]
    command_count: int
    position: BlockPosition | None


@dataclass(frozen=True)
class _PlayerTpBuildWindow:
    index: int
    main_start: int
    main_end: int
    cross_start: int
    cross_end: int
    packets: tuple[_BuildCommandPacket, ...]


class BasicMcfunctionWriter:
    """Writes resolved layout cells using setblock commands."""

    def __init__(self, config: CommandWriterConfig | None = None) -> None:
        self.config = config or CommandWriterConfig()

    def write_file(self, layout: LayoutResult, path: str | Path) -> CommandWriteResult:
        output_path = Path(path)
        self._validate_config_capabilities()
        lines = self._lines(layout)
        _validate_build_height(lines, self.config)
        command_count = _command_count(lines)

        if not self.config.split_functions:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(_join_lines(lines), encoding="utf-8")
            return CommandWriteResult(
                total_commands=command_count,
                split_function_parts=1,
            )

        debug = self._write_player_tp_build_files(lines, output_path)
        return CommandWriteResult(
            total_commands=command_count,
            split_function_parts=debug.total_parts,
            player_tp_build=debug,
        )

    def write_text(self, layout: LayoutResult) -> str:
        self._validate_config_capabilities(player_tp_build=False)
        lines = self._lines(layout)
        _validate_build_height(lines, self.config)
        return _join_lines(lines)

    def _validate_config_capabilities(self, player_tp_build: bool | None = None) -> None:
        profile = self.config.minecraft_version_profile
        uses_player_tp_build = (
            self.config.split_functions
            if player_tp_build is None
            else player_tp_build
        )
        if uses_player_tp_build and not profile.supports_player_tp_build:
            raise MinecraftVersionError(
                "Player-tp build output is not supported for Minecraft Java "
                f"{profile.version_id} by the current version profile. Disable "
                "split functions or choose a supported target version."
            )

    def _lines(self, layout: LayoutResult) -> list[str]:
        unknown_instruments = _unknown_instruments(layout)
        lines = [
            "# Generated by nbs2func",
            f"# layout_mode={layout.mode}",
            "",
        ]

        for instrument in unknown_instruments:
            message = (
                f"Unknown instrument {instrument}; using default instrument block."
            )
            warnings.warn(message, stacklevel=2)
            lines.append(f"# WARNING: {message}")
        if unknown_instruments:
            lines.append("")

        lines.extend(
            starter_module_lines(
                layout,
                StarterModuleConfig(
                    enable_starter_module=(
                        self.config.enable_starter_module
                        or self.config.enable_playback_assist
                    ),
                    emit_command_block=not self.config.enable_playback_assist,
                    command_block_position=self.config.command_block_position,
                    starter_tag=self.config.starter_tag,
                    starter_track_block=self.config.starter_track_block,
                    starter_cell_offset=self.config.starter_cell_offset,
                    minecraft_version_profile=(
                        self.config.minecraft_version_profile
                    ),
                ),
                default_track_block=self.config.track_block,
                repeater_block=self.config.repeater_block,
            )
        )

        if layout.note_based_preview is not None:
            lines.extend(self._note_based_preview_lines(layout.note_based_preview))
        else:
            for cell in layout.cells:
                lines.extend(self._commands_for_cell(cell))

        lines.extend(
            playback_assist_lines(
                PlaybackAssistModuleConfig(
                    enable_playback_assist=self.config.enable_playback_assist,
                    player_name=self.config.playback_player_name,
                    playback_vehicle_tag=self.config.playback_vehicle_tag,
                    starter_tag=self.config.starter_tag,
                    count_objective=self.config.count_objective,
                    vehicle_spawn_position=self.config.vehicle_spawn_position,
                    music_start_position=self.config.music_start_position,
                    command_module_origin=self.config.command_module_origin,
                    track_direction=self.config.playback_track_direction,
                    total_track_length=(
                        self.config.playback_total_track_length
                        if self.config.playback_total_track_length is not None
                        else total_track_length_from_layout(
                            layout,
                            self.config.playback_track_direction,
                            self.config.music_start_position,
                        )
                    ),
                    generate_playback_buttons=self.config.generate_playback_buttons,
                    playback_button_block=self.config.playback_button_block,
                    prepare_button_position=self.config.prepare_button_position,
                    start_button_position=self.config.start_button_position,
                    minecraft_version_profile=(
                        self.config.minecraft_version_profile
                    ),
                    tempo_control_mode=self.config.tempo_control_mode,
                    tempo_control_report=self.config.tempo_control_report,
                    reset_tick_rate_after_playback=(
                        self.config.reset_tick_rate_after_playback
                    ),
                )
            )
        )

        return lines

    def _write_player_tp_build_files(
        self,
        lines: list[str],
        output_path: Path,
    ) -> PlayerTpBuildDebug:
        datapack_root = _datapack_root_from_output_path(output_path)
        write_pack_mcmeta(datapack_root, self.config.minecraft_version_profile)
        build_dir = (
            datapack_root
            / "data"
            / self.config.function_namespace
            / self.config.minecraft_version_profile.function_dir_name
            / self.config.build_function_dir
        )
        build_dir.mkdir(parents=True, exist_ok=True)

        packets = _build_command_unit_packets(lines)
        positions = tuple(
            packet.position
            for packet in packets
            if packet.position is not None
        ) or (BlockPosition(0, 0, 0),)

        direction = normalize_direction(self.config.playback_track_direction)
        split_axis = "x" if direction in {"east", "west"} else "z"
        build_box = _build_bounding_box(positions)
        windows = _build_player_tp_windows(
            packets,
            build_box,
            split_axis,
            self.config.player_tp_window_length_blocks,
            self.config.player_tp_window_lateral_width_blocks,
        )
        if not windows:
            windows = (
                _PlayerTpBuildWindow(
                    index=0,
                    main_start=0,
                    main_end=0,
                    cross_start=0,
                    cross_end=0,
                    packets=tuple(packets),
                ),
            )

        start_path = build_dir / "start.mcfunction"
        start_path.write_text(
            _join_lines(
                [
                    "# Generated by nbs2func player-tp build",
                    _schedule_function(
                        self.config.function_namespace,
                        self.config.build_function_dir,
                        "window_000/tp",
                        1,
                    ),
                ]
            ),
            encoding="utf-8",
        )

        total_parts = 0
        window_debug: list[PlayerTpWindowDebug] = []
        for index, window in enumerate(windows):
            window_dir = build_dir / f"window_{index:03d}"
            window_dir.mkdir(parents=True, exist_ok=True)
            parts = _split_packets_by_command_limit(
                list(window.packets),
                self.config.max_commands_per_build_part,
            ) or [[]]
            total_parts += len(parts)
            center = _player_tp_window_center(self.config, window, split_axis, build_box)
            window_box = _player_tp_window_box(window, split_axis, build_box)
            command_count = sum(packet.command_count for packet in window.packets)
            window_debug.append(
                PlayerTpWindowDebug(
                    window_index=index,
                    center_position=center,
                    bounding_box=window_box,
                    command_count=command_count,
                    part_count=len(parts),
                )
            )

            (window_dir / "tp.mcfunction").write_text(
                _join_lines(
                    [
                        f"# tp player for window {index:03d}",
                        (
                            f"tp {self.config.build_player_name} "
                            f"{center.x} {center.y} {center.z}"
                        ),
                        _schedule_function(
                            self.config.function_namespace,
                            self.config.build_function_dir,
                            f"window_{index:03d}/wait",
                            self.config.player_tp_chunk_load_wait_ticks,
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (window_dir / "wait.mcfunction").write_text(
                _join_lines(
                    [
                        "# Waited for player-loaded chunks",
                        _schedule_function(
                            self.config.function_namespace,
                            self.config.build_function_dir,
                            f"window_{index:03d}/part_000",
                            1,
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            for part_index, part_packets in enumerate(parts):
                part_lines = _flatten_packets(part_packets)
                if part_index < len(parts) - 1:
                    part_lines.append(
                        _schedule_function(
                            self.config.function_namespace,
                            self.config.build_function_dir,
                            f"window_{index:03d}/part_{part_index + 1:03d}",
                            self.config.schedule_delay_ticks_between_parts,
                        )
                    )
                else:
                    part_lines.append(
                        _schedule_function(
                            self.config.function_namespace,
                            self.config.build_function_dir,
                            f"window_{index:03d}/done",
                            self.config.player_tp_after_build_wait_ticks,
                        )
                    )
                (window_dir / f"part_{part_index:03d}.mcfunction").write_text(
                    _join_lines(part_lines),
                    encoding="utf-8",
                )

            next_path = (
                "done"
                if index == len(windows) - 1
                else f"window_{index + 1:03d}/tp"
            )
            (window_dir / "done.mcfunction").write_text(
                _join_lines(
                    [
                        f"# done window {index:03d}",
                        _schedule_function(
                            self.config.function_namespace,
                            self.config.build_function_dir,
                            next_path,
                            1,
                        ),
                    ]
                ),
                encoding="utf-8",
            )

        done_lines = ["# Player-tp build complete"]
        done_lines.append('tellraw @a {"text":"nbs2func build complete"}')
        finish = self.config.build_finish_tp_position
        if finish is not None:
            done_lines.append(
                f"tp {self.config.build_player_name} {finish.x} {finish.y} {finish.z}"
            )
        build_dir.joinpath("done.mcfunction").write_text(
            _join_lines(done_lines),
            encoding="utf-8",
        )

        estimated_ticks = sum(
            self.config.player_tp_chunk_load_wait_ticks
            + self.config.player_tp_after_build_wait_ticks
            + max(0, debug.part_count - 1) * self.config.schedule_delay_ticks_between_parts
            + 2
            for debug in window_debug
        )
        warnings_to_emit: list[str] = []
        if len(windows) > 64:
            warnings_to_emit.append(
                "total windows is high. If the build takes too long, raise "
                "player_tp_window_length_blocks or player_tp_window_lateral_width_blocks; "
                "if chunks fail to load, keep the safer smaller windows."
            )
        if any(
            debug.command_count > self.config.max_commands_per_build_part * 16
            for debug in window_debug
        ):
            warnings_to_emit.append(
                "one or more windows contain many commands. If TPS drops during "
                "building, lower max_commands_per_build_part."
            )

        return PlayerTpBuildDebug(
            build_bounding_box=build_box,
            track_direction=direction,
            split_axis=split_axis,
            build_player_name=self.config.build_player_name,
            player_load_radius_chunks=self.config.player_load_radius_chunks,
            player_tp_window_length_blocks=self.config.player_tp_window_length_blocks,
            player_tp_window_lateral_width_blocks=(
                self.config.player_tp_window_lateral_width_blocks
            ),
            total_windows=len(windows),
            total_commands=_command_count(lines),
            max_commands_per_part=self.config.max_commands_per_build_part,
            total_parts=total_parts,
            wait_ticks_before_build=self.config.player_tp_chunk_load_wait_ticks,
            wait_ticks_after_build=self.config.player_tp_after_build_wait_ticks,
            schedule_delay_ticks_between_parts=(
                self.config.schedule_delay_ticks_between_parts
            ),
            estimated_total_build_ticks=estimated_ticks,
            windows=tuple(window_debug),
            warnings=tuple(warnings_to_emit),
        )

    def _commands_for_cell(self, cell: LayoutCell) -> list[str]:
        commands = [
            f"# tick={cell.tick} track={cell.track_id}",
            _setblock(cell.track_block_position, self.config.track_block),
            _setblock(
                cell.repeater_position,
                f"{self.config.repeater_block}[facing={cell.repeater_facing},delay=2]",
            ),
        ]

        if cell.note is None:
            commands.extend(
                [
                    _setblock(cell.note_block_position, self.config.track_block),
                    _setblock(cell.instrument_block_position, self.config.track_block),
                    "",
                ]
            )
            return commands

        note_value = _minecraft_note_value(cell.note.key)
        instrument_block = get_instrument_block(cell.note.instrument)
        support_block = get_required_support_block(
            instrument_block,
            self.config.track_block,
        )
        if cell.gravity_support_block_position is not None and support_block is not None:
            commands.append(
                _setblock(cell.gravity_support_block_position, support_block)
            )

        commands.extend(
            [
                (
                    f"# note layer={cell.note.layer} instrument={cell.note.instrument} "
                    f"key={cell.note.key} final_volume={cell.note.final_volume:.2f} "
                    f"final_panning={cell.note.final_panning:.2f}"
                ),
                _setblock(cell.instrument_block_position, instrument_block),
                _setblock(cell.note_block_position, f"note_block[note={note_value}]"),
                "",
            ]
        )
        return commands

    def _note_based_preview_lines(
        self,
        report: NoteBasedStereoRailLayoutPreview,
    ) -> list[str]:
        lines = [
            "# Note-based stereo rail layout",
            f"# rails={report.total_activation_rails}",
            f"# emitters={len(report.assignments)}",
            "",
        ]
        assignments_by_rail_tick: dict[tuple[str, int], list[SlotAssignment]] = {}
        rails_by_id = {
            assignment.rail.rail_id: assignment.rail
            for assignment in report.assignments
        }

        for assignment in report.assignments:
            assignments_by_rail_tick.setdefault(
                (assignment.rail.rail_id, assignment.emitter.tick),
                [],
            ).append(assignment)

        for rail_id, rail in sorted(rails_by_id.items()):
            rail_ticks = [
                tick
                for assignment_rail_id, tick in assignments_by_rail_tick
                if assignment_rail_id == rail_id
            ]
            if not rail_ticks:
                continue

            lines.append(
                f"# rail={rail_id} offset_y={rail.offset_y} "
                f"offset_lateral={rail.offset_lateral}"
            )
            for tick in range(max(rail_ticks) + 1):
                cell_assignments = assignments_by_rail_tick.get((rail_id, tick), [])
                center_assignment = next(
                    (
                        assignment
                        for assignment in cell_assignments
                        if assignment.slot.slot_index == 0
                    ),
                    None,
                )
                rail_center = _note_based_position(
                    report,
                    tick,
                    rail.offset_y,
                    rail.offset_lateral,
                )
                repeater_position = repeater_position_from_note_position(
                    rail_center,
                    report.track_direction,
                )

                lines.append(f"# tick={tick} rail={rail_id}")
                if center_assignment is None:
                    lines.extend(
                        [
                            _setblock(below(repeater_position), self.config.track_block),
                            _setblock(
                                repeater_position,
                                (
                                    f"{self.config.repeater_block}"
                                    f"[facing={_repeater_facing(report)},delay=2]"
                                ),
                            ),
                            _setblock(rail_center, self.config.track_block),
                            _setblock(below(rail_center), self.config.track_block),
                        ]
                    )
                else:
                    lines.extend(
                        [
                            _setblock(
                                below(repeater_position),
                                self.config.track_block,
                            ),
                            _setblock(
                                repeater_position,
                                (
                                    f"{self.config.repeater_block}"
                                    f"[facing={_repeater_facing(report)},delay=2]"
                                ),
                            ),
                        ]
                    )
                    lines.extend(
                        self._note_based_emitter_commands(center_assignment)
                    )

                for assignment in cell_assignments:
                    if assignment.slot.slot_index == 0:
                        continue
                    lines.extend(self._note_based_emitter_commands(assignment))

                lines.append("")

        return lines

    def _note_based_emitter_commands(
        self,
        assignment: SlotAssignment,
    ) -> list[str]:
        emitter = assignment.emitter
        note_value = _minecraft_note_value(emitter.key)
        instrument_block = get_instrument_block(emitter.instrument)
        instrument_position = below(assignment.slot.position)
        support_block = get_required_support_block(
            instrument_block,
            self.config.track_block,
        )
        commands = [
            (
                f"# emitter={emitter.emitter_id} rail={assignment.rail.rail_id} "
                f"slot={assignment.slot.slot_index} layer={emitter.layer} "
                f"instrument={emitter.instrument} key={emitter.key} "
                f"final_volume={emitter.final_volume:.2f} "
                f"final_panning={emitter.final_panning:.2f}"
            )
        ]
        if support_block is not None:
            commands.append(_setblock(below(instrument_position), support_block))
        commands.extend(
            [
                _setblock(instrument_position, instrument_block),
                _setblock(assignment.slot.position, f"note_block[note={note_value}]"),
            ]
        )
        return commands


def write_mcfunction(
    layout: LayoutResult,
    path: str | Path,
    config: CommandWriterConfig | None = None,
) -> CommandWriteResult:
    """Write a layout to a .mcfunction file using the default writer."""

    return BasicMcfunctionWriter(config).write_file(layout, path)


def _setblock(position: BlockPosition, block: str) -> str:
    return f"setblock {position.x} {position.y} {position.z} {_block_id(block)}"


def _block_id(block: str) -> str:
    if block.startswith("minecraft:"):
        return block
    return f"minecraft:{block}"


def _minecraft_note_value(key: int) -> int:
    return min(24, max(0, key - 33))


def _note_based_position(
    report: NoteBasedStereoRailLayoutPreview,
    tick: int,
    offset_y: int,
    offset_lateral: int,
) -> BlockPosition:
    track_direction = normalize_direction(report.track_direction)
    track_vector = DIRECTION_VECTORS[track_direction]
    lateral_vector = _right_hand_lateral_vector(track_direction)
    cell_origin = add_vector(
        report.origin,
        _scale_vector(track_vector, tick * report.tick_spacing),
    )
    return add_vector(
        add_y(cell_origin, offset_y),
        _scale_vector(lateral_vector, offset_lateral),
    )


def _repeater_facing(report: NoteBasedStereoRailLayoutPreview) -> str:
    return opposite_direction(report.track_direction)


def _join_lines(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _is_command(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _command_count(lines: list[str]) -> int:
    return sum(1 for line in lines if _is_command(line))


def _build_command_unit_packets(lines: list[str]) -> list[_BuildCommandPacket]:
    packets: list[_BuildCommandPacket] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        position = next(
            (
                _line_primary_position(line)
                for line in current
                if _line_primary_position(line) is not None
            ),
            None,
        )
        packets.append(
            _BuildCommandPacket(
                lines=tuple(current),
                command_count=_command_count(current),
                position=position,
            )
        )
        current = []

    for line in lines:
        current.append(line)
        if not line.strip():
            flush()
    flush()
    return packets


def _line_primary_position(line: str) -> BlockPosition | None:
    parts = line.strip().split()
    if len(parts) >= 4 and parts[0] == "setblock":
        return _parse_position(parts[1:4])
    if len(parts) >= 5 and parts[0] == "summon":
        return _parse_position(parts[2:5])
    return None


def _parse_position(values: list[str]) -> BlockPosition | None:
    try:
        return BlockPosition(
            _parse_coordinate(values[0]),
            _parse_coordinate(values[1]),
            _parse_coordinate(values[2]),
        )
    except ValueError:
        return None


def _parse_coordinate(value: str) -> int:
    if value.startswith("~") or value.startswith("^"):
        raise ValueError(value)
    return int(float(value))


def _validate_build_height(lines: list[str], config: CommandWriterConfig) -> None:
    positions = tuple(
        position
        for line in lines
        if (position := _line_primary_position(line)) is not None
    )
    if not positions:
        return

    min_y = min(position.y for position in positions)
    max_y = max(position.y for position in positions)
    profile = config.minecraft_version_profile
    if profile.min_build_y <= min_y and max_y <= profile.max_build_y:
        return

    requested_origin_y = (
        str(config.requested_origin_y)
        if config.requested_origin_y is not None
        else "unknown"
    )
    raise MinecraftVersionError(
        "Generated structure exceeds Minecraft Java "
        f"{profile.version_id} build height. Allowed Y range: "
        f"{profile.min_build_y}..{profile.max_build_y}; "
        f"requested origin_y={requested_origin_y}; generated min_y={min_y}; "
        f"generated max_y={max_y}."
    )


def _build_bounding_box(positions: tuple[BlockPosition, ...]) -> BuildBoundingBox:
    return BuildBoundingBox(
        min_x=min(position.x for position in positions),
        min_y=min(position.y for position in positions),
        min_z=min(position.z for position in positions),
        max_x=max(position.x for position in positions),
        max_y=max(position.y for position in positions),
        max_z=max(position.z for position in positions),
    )


def _build_player_tp_windows(
    packets: list[_BuildCommandPacket],
    build_box: BuildBoundingBox,
    split_axis: str,
    window_length_blocks: int,
    lateral_width_blocks: int,
) -> tuple[_PlayerTpBuildWindow, ...]:
    window_length_blocks = max(1, window_length_blocks)
    lateral_width_blocks = max(1, lateral_width_blocks)
    if split_axis == "x":
        main_min, main_max = build_box.min_x, build_box.max_x
        cross_min, cross_max = build_box.min_z, build_box.max_z
    else:
        main_min, main_max = build_box.min_z, build_box.max_z
        cross_min, cross_max = build_box.min_x, build_box.max_x

    windows: list[_PlayerTpBuildWindow] = []
    main_start = main_min
    while main_start <= main_max:
        main_end = min(main_max, main_start + window_length_blocks - 1)
        cross_start = cross_min
        while cross_start <= cross_max:
            cross_end = min(cross_max, cross_start + lateral_width_blocks - 1)
            windows.append(
                _PlayerTpBuildWindow(
                    index=len(windows),
                    main_start=main_start,
                    main_end=main_end,
                    cross_start=cross_start,
                    cross_end=cross_end,
                    packets=(),
                )
            )
            cross_start = cross_end + 1
        main_start = main_end + 1

    packet_groups: list[list[_BuildCommandPacket]] = [[] for _ in windows]
    for packet in packets:
        window_index = 0
        if packet.position is not None:
            main_value = packet.position.x if split_axis == "x" else packet.position.z
            cross_value = packet.position.z if split_axis == "x" else packet.position.x
            for index, window in enumerate(windows):
                if (
                    window.main_start <= main_value <= window.main_end
                    and window.cross_start <= cross_value <= window.cross_end
                ):
                    window_index = index
                    break
        packet_groups[window_index].append(packet)

    return tuple(
        _PlayerTpBuildWindow(
            index=window.index,
            main_start=window.main_start,
            main_end=window.main_end,
            cross_start=window.cross_start,
            cross_end=window.cross_end,
            packets=tuple(packet_groups[index]),
        )
        for index, window in enumerate(windows)
    )


def _player_tp_window_center(
    config: CommandWriterConfig,
    window: _PlayerTpBuildWindow,
    split_axis: str,
    build_box: BuildBoundingBox,
) -> BlockPosition:
    main = (window.main_start + window.main_end) // 2
    cross = (window.cross_start + window.cross_end) // 2
    y = _build_tp_y(config)
    if split_axis == "x":
        return BlockPosition(main, y, cross)
    return BlockPosition(cross, y, main)


def _build_tp_y(config: CommandWriterConfig) -> int:
    if config.build_tp_y is not None:
        return config.build_tp_y
    if config.command_module_origin is not None:
        return config.command_module_origin.y
    return config.music_start_position.y


def _player_tp_window_box(
    window: _PlayerTpBuildWindow,
    split_axis: str,
    build_box: BuildBoundingBox,
) -> BuildBoundingBox:
    if split_axis == "x":
        return BuildBoundingBox(
            min_x=window.main_start,
            max_x=window.main_end,
            min_z=window.cross_start,
            max_z=window.cross_end,
            min_y=build_box.min_y,
            max_y=build_box.max_y,
        )
    return BuildBoundingBox(
        min_x=window.cross_start,
        max_x=window.cross_end,
        min_z=window.main_start,
        max_z=window.main_end,
        min_y=build_box.min_y,
        max_y=build_box.max_y,
    )


def _split_packets_by_command_limit(
    packets: list[_BuildCommandPacket],
    max_commands: int,
) -> list[list[_BuildCommandPacket]]:
    max_commands = max(2, max_commands)
    parts: list[list[_BuildCommandPacket]] = []
    current: list[_BuildCommandPacket] = []
    current_commands = 0

    for packet in packets:
        # Every player-tp part schedules either the next part or the window done
        # function, so reserve one command in every part.
        limit_for_current_part = max_commands - 1

        if (
            packet.command_count
            and current_commands + packet.command_count > limit_for_current_part
            and current
        ):
            parts.append(current)
            current = []
            current_commands = 0

        current.append(packet)
        current_commands += packet.command_count

    if current:
        parts.append(current)

    return parts


def _flatten_packets(packets: list[_BuildCommandPacket]) -> list[str]:
    return [
        line
        for packet in packets
        for line in packet.lines
    ]


def _schedule_function(
    namespace: str,
    build_function_dir: str,
    function_path: str,
    delay_ticks: int,
) -> str:
    return f"schedule function {namespace}:{build_function_dir}/{function_path} {delay_ticks}t"


def _datapack_root_from_output_path(output_path: Path) -> Path:
    if output_path.suffix == ".mcfunction":
        return output_path.parent
    return output_path


def _unknown_instruments(layout: LayoutResult) -> tuple[int, ...]:
    instruments = {
        note.instrument
        for note in layout.notes
        if not has_instrument_mapping(note.instrument)
    }
    if layout.note_based_preview is not None:
        instruments.update(
            assignment.emitter.instrument
            for assignment in layout.note_based_preview.assignments
            if not has_instrument_mapping(assignment.emitter.instrument)
        )

    return tuple(sorted(instruments))
