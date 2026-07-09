from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nbs2func.config import (
    Nbs2FuncConfig,
    config_from_dict,
    config_to_dict,
    default_config,
)
from nbs2func.core.nbs_reader import read_nbs
from nbs2func.gui.helpers import (
    default_datapack_folder_name,
    default_schematic_name,
    modules_require_runtime_logic,
    normalize_gui_config,
    validate_module_coordinates,
)
from nbs2func.generation import function_path_errors


@dataclass
class WizardState:
    config: Nbs2FuncConfig
    input_song_summary: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)
    output_log: list[str] = field(default_factory=list)
    config_path: str | None = None
    note_based_profile: str = "balanced"
    datapack_name: str = "demo"
    starter_origin_user_modified: bool = False
    command_module_origin_user_modified: bool = False
    datapack_name_user_modified: bool = False
    schematic_name_user_modified: bool = False


def create_default_state() -> WizardState:
    config = normalize_gui_config(default_config())
    return WizardState(
        config=config,
        datapack_name=default_datapack_folder_name(config),
    )


def create_state_from_config(
    config: Nbs2FuncConfig,
    *,
    config_path: str | None = None,
) -> WizardState:
    normalized = normalize_gui_config(config)
    return WizardState(
        config=normalized,
        config_path=config_path,
        datapack_name=default_datapack_folder_name(normalized),
    )


def update_config(
    state: WizardState,
    updates: dict[str, object] | None = None,
    **kwargs: object,
) -> None:
    merged = dict(updates or {})
    merged.update(kwargs)
    if not merged:
        return

    data = config_to_dict(state.config)
    data.update(merged)
    state.config = config_from_dict(data)


def set_layout_mode(state: WizardState, layout_mode: str) -> None:
    update_config(state, layout_mode=layout_mode)


def set_output_format(state: WizardState, output_format: str) -> None:
    update_config(state, output_format=output_format)


def load_input_song(state: WizardState, path: str | Path) -> dict[str, object]:
    old_default_name = default_schematic_name(state.config)
    old_datapack_name = default_datapack_folder_name(state.config)
    song_path = Path(path).expanduser().resolve()
    song = read_nbs(song_path)
    note_count = sum(len(track.notes) for track in song.tracks)
    instruments: dict[int, int] = {}
    for track in song.tracks:
        for note in track.notes:
            instruments[note.instrument] = instruments.get(note.instrument, 0) + 1

    summary: dict[str, object] = {
        "path": str(song_path),
        "name": song.name,
        "author": song.author,
        "length": song.length,
        "tempo": song.nbs_tempo_tps,
        "layer_count": len(song.tracks),
        "note_count": note_count,
        "instrument_summary": dict(sorted(instruments.items())),
    }
    state.input_song_summary = summary
    updates: dict[str, object] = {"input_path": str(song_path)}
    if (
        not state.schematic_name_user_modified
        or state.config.schematic_name in {None, "", old_default_name}
    ):
        updates["schematic_name"] = song_path.stem or "nbs_song"
        state.schematic_name_user_modified = False
    if not state.datapack_name_user_modified or state.datapack_name in {
        "",
        old_datapack_name,
    }:
        state.datapack_name = song_path.stem or "nbs_song"
        updates["datapack_name"] = state.datapack_name
        state.datapack_name_user_modified = False
    update_config(state, updates)
    return summary


def append_log(state: WizardState, line: str) -> None:
    state.output_log.append(line)


def clear_log(state: WizardState) -> None:
    state.output_log.clear()


def validate_ready_to_generate(state: WizardState) -> list[str]:
    errors: list[str] = []
    if not Path(state.config.input_path).is_file():
        errors.append("Select a valid .nbs input file.")
    if state.config.output_format not in {"datapack", "schem", "both"}:
        errors.append("Select a valid output format.")
    if state.config.output_format == "schem" and modules_require_runtime_logic(
        state.config
    ):
        errors.append(
            "Schem-only output is not compatible with starter or playback assist."
        )
    if state.config.enable_playback_assist and not state.config.enable_starter_module:
        errors.append("Playback assist requires starter module to be enabled.")
    if (
        state.config.tempo_control_mode == "command"
        and not state.config.enable_playback_assist
    ):
        errors.append("Tempo command mode requires playback assist.")
    errors.extend(validate_module_coordinates(state.config))
    errors.extend(
        function_path_errors(
            state.config.function_namespace,
            state.config.build_function_dir,
        )
    )
    return errors


def summary_lines(state: WizardState) -> list[str]:
    config = state.config
    song = state.input_song_summary or {}
    modules = []
    modules.append("starter" if config.enable_starter_module else "starter off")
    modules.append(
        "playback assist" if config.enable_playback_assist else "playback assist off"
    )
    lines = [
        f"Input file: {config.input_path}",
        f"Song: {song.get('name', '(not loaded)')}",
        f"Length: {song.get('length', 'n/a')} ticks",
        f"Notes: {song.get('note_count', 'n/a')}",
        f"Layout mode: {config.layout_mode}",
        f"Direction: {config.direction}",
        f"Origin: {config.origin_x}, {config.origin_y}, {config.origin_z}",
        f"Minecraft version: {config.minecraft_version}",
        f"Output format: {config.output_format}",
        f"Output folder: {config.output}",
        f"Namespace: {config.function_namespace}",
        f"Schematic output: {config.schematic_output or '(default)'}",
        f"Schematic name: {config.schematic_name or '(default)'}",
        f"Modules: {', '.join(modules)}",
        (
            "Tempo control: "
            f"{config.tempo_control_mode} / {config.tempo_control_backend}"
        ),
    ]
    if state.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in state.warnings)
    return lines


def config_value(config: Nbs2FuncConfig, field_name: str) -> Any:
    return getattr(config, field_name)
