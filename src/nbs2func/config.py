from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
from pathlib import Path
from typing import Any, get_args, get_origin

from .core.minecraft_version import DEFAULT_MINECRAFT_VERSION


@dataclass(frozen=True)
class Nbs2FuncConfig:
    """User-editable generation configuration."""

    # TODO(config): The CLI generation path now uses this as its default source.
    # Module-level config dataclass defaults are still retained for direct API
    # compatibility and should be collapsed to shared constants in a later,
    # output-preserving cleanup.
    input_path: str = "examples/demo.nbs"
    output: str = "output"
    output_format: str = "datapack"
    schematic_origin_mode: str = "generation_origin"
    schematic_output: str | None = None
    schematic_name: str | None = None
    minecraft_version: str = DEFAULT_MINECRAFT_VERSION
    layout_mode: str = "note_based_stereo"
    direction: str = "east"
    origin_x: int = 0
    origin_y: int = 128
    origin_z: int = 0

    analyze_stereo: bool = False
    analyze_layout_spatial: bool = False
    group_config: str | None = None
    analysis_output: str | None = None
    analysis_window_size: int = 128
    analysis_hop_size: int = 32
    analysis_detail: str = "summary"

    track_id: int | None = None
    max_hearing_distance: float = 48
    min_distance: float = 4
    max_stereo_angle_degrees: float = 90
    center_threshold: float = 10
    center_split_policy: str = "auto_on_collision"
    center_split_mode: str = "duplicate_half_volume"
    center_split_overrides: dict[int, str] | None = None
    center_split_pan: float = 50
    max_auto_center_splits: int = 20
    enable_collision_resolver: bool = True
    enable_depth_mirror_fallback: bool = True
    enable_radius_relax_fallback: bool = True
    max_angle_deviation_degrees: float = 30
    angle_search_step_degrees: float = 5
    radius_relax_step: float = 1
    max_radius_relax: float = 3
    min_world_y: int | None = None
    max_world_y: int | None = None
    enable_pan_zone_layout: bool = True
    allow_adjacent_pan_zone_fallback: bool = False
    pan_zone_search_radius_limit: int = 8
    max_candidates_per_emitter: int = 64
    max_candidate_y_layers: int = 8
    max_candidate_lateral_positions: int = 16
    radius_search_tolerance: float = 4
    max_lateral_distance: int = 48
    pan_zone_reference_radius: float = 48
    enable_depth_mirror_candidates: bool = True
    preferred_depth_sign: int = 1
    allow_negative_depth_offsets: bool = True
    depth_mirror_penalty: float = 0.0
    lateral_step_penalty: float = 0.5
    allow_adjacent_pan_zone_fallback_for_failed: bool = True
    retry_max_candidates_per_emitter: int = 256
    enable_same_side_zone_split_fallback: bool = False
    same_side_split_volume_factor: float = 0.5
    min_rail_center_y_gap: int = 4
    activation_slot_radius: int = 1
    max_collision_records: int = 5000
    max_collision_examples_per_group: int = 20
    preview_time_limit_seconds: float = 1200
    fail_fast_on_too_many_collisions: bool = True
    max_collision_records_before_abort: int = 50000
    profile: bool = False
    enable_note_level_center_split: bool = True
    center_split_left_pan: float = 75
    center_split_right_pan: float = 125
    center_split_volume_factor: float = 0.5
    max_note_level_center_splits: int = 100

    enable_starter_module: bool = False
    command_block_x: int = -10
    command_block_y: int = 128
    command_block_z: int = 0
    starter_tag: str = "nbs_starter"
    starter_track_block: str | None = None
    starter_cell_offset: int = -1

    enable_playback_assist: bool = False
    playback_player_name: str = "Alex842036"
    playback_vehicle_tag: str = "playback_vehicle"
    count_objective: str = "count"
    vehicle_spawn_x: int | None = None
    vehicle_spawn_y: int | None = None
    vehicle_spawn_z: int | None = None
    music_start_x: int = 0
    music_start_y: int = 128
    music_start_z: int = 0
    command_module_origin_x: int | None = None
    command_module_origin_y: int | None = None
    command_module_origin_z: int | None = None
    generate_playback_buttons: bool = True
    playback_button_block: str = "minecraft:stone_button"
    prepare_button_x: int | None = None
    prepare_button_y: int | None = None
    prepare_button_z: int | None = None
    start_button_x: int | None = None
    start_button_y: int | None = None
    start_button_z: int | None = None

    split_functions: bool = True
    max_commands_per_build_part: int = 500
    schedule_delay_ticks_between_parts: int = 4
    build_player_name: str = "Alex842036"
    player_load_radius_chunks: int = 6
    player_tp_chunk_load_wait_ticks: int = 20
    player_tp_after_build_wait_ticks: int = 20
    player_tp_window_length_blocks: int = 192
    player_tp_window_lateral_width_blocks: int = 192
    build_tp_y: int | None = None
    build_finish_tp_x: int | None = None
    build_finish_tp_y: int | None = None
    build_finish_tp_z: int | None = None
    function_namespace: str = "nbs"
    build_function_dir: str = "build"

    tempo_control_mode: str = "report"
    tempo_control_backend: str = "auto"
    tempo_rate_decimals: int = 2
    game_ticks_per_song_tick: int = 4
    reset_tick_rate_after_playback: bool = True


def default_config() -> Nbs2FuncConfig:
    """Return a fresh config instance with CLI-equivalent defaults."""

    return Nbs2FuncConfig(center_split_overrides={})


def load_config(path: str | Path) -> Nbs2FuncConfig:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON config {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Config JSON root must be an object.")
    return config_from_dict(data)


def save_config(config: Nbs2FuncConfig, path: str | Path) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config_to_dict(config), indent=2) + "\n",
        encoding="utf-8",
    )


def config_to_dict(config: Nbs2FuncConfig) -> dict[str, Any]:
    data = asdict(config)
    overrides = data.get("center_split_overrides")
    if overrides is not None:
        data["center_split_overrides"] = {
            str(track_id): action
            for track_id, action in sorted(overrides.items())
        }
    return data


def config_from_dict(data: dict[str, Any]) -> Nbs2FuncConfig:
    if not isinstance(data, dict):
        raise ValueError("Config data must be a dict.")

    defaults = default_config()
    known_fields = {field.name: field for field in fields(Nbs2FuncConfig)}
    unknown = sorted(set(data) - set(known_fields))
    if unknown:
        raise ValueError(f"Unknown config field(s): {', '.join(unknown)}")

    values: dict[str, Any] = {}
    for field in fields(Nbs2FuncConfig):
        if field.name not in data:
            continue
        value = data[field.name]
        if field.name == "center_split_overrides":
            values[field.name] = _validate_center_split_overrides(value)
            continue
        if not _matches_type(value, field.type):
            expected = _type_label(field.type)
            raise ValueError(
                f"Invalid type for config field {field.name!r}: "
                f"expected {expected}, got {type(value).__name__}."
            )
        _validate_choice(field.name, value)
        values[field.name] = value

    return replace(defaults, **values)


def _validate_center_split_overrides(value: Any) -> dict[int, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(
            "Invalid type for config field 'center_split_overrides': "
            "expected object, got "
            f"{type(value).__name__}."
        )
    overrides: dict[int, str] = {}
    for raw_track_id, action in value.items():
        try:
            track_id = int(raw_track_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "center_split_overrides keys must be integer track ids."
            ) from exc
        if action not in {"split", "none"}:
            raise ValueError(
                "center_split_overrides values must be 'split' or 'none'."
            )
        overrides[track_id] = action
    return overrides


def _validate_choice(field_name: str, value: Any) -> None:
    choices_by_field = {
        "tempo_control_mode": {"none", "report", "command"},
        "tempo_control_backend": {"auto", "carpet", "vanilla"},
        "output_format": {"datapack", "schem", "both"},
        "schematic_origin_mode": {"generation_origin", "min_corner"},
    }
    choices = choices_by_field.get(field_name)
    if choices is not None and value not in choices:
        raise ValueError(
            f"Invalid value for config field {field_name!r}: {value!r}. "
            f"Expected one of: {', '.join(sorted(choices))}."
        )


def _matches_type(value: Any, annotation: Any) -> bool:
    if isinstance(annotation, str):
        annotation = _STRING_TYPE_ALIASES.get(annotation, annotation)
    origin = get_origin(annotation)
    if origin is None:
        return _matches_simple_type(value, annotation)
    if origin is dict:
        return isinstance(value, dict)
    if origin is None:
        return True
    if origin is type(None):
        return value is None
    if origin is not None and str(origin) == "types.UnionType":
        return any(_matches_type(value, arg) for arg in get_args(annotation))
    if origin is not None and origin is getattr(__import__("typing"), "Union"):
        return any(_matches_type(value, arg) for arg in get_args(annotation))
    return True


def _matches_simple_type(value: Any, expected: Any) -> bool:
    if expected is Any:
        return True
    if expected is None or expected is type(None):
        return value is None
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
    if expected is str:
        return isinstance(value, str)
    return isinstance(value, expected)


def _type_label(annotation: Any) -> str:
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", str(annotation))


_STRING_TYPE_ALIASES = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "str | None": str | None,
    "int | None": int | None,
    "dict[int, str] | None": dict[int, str] | None,
}
