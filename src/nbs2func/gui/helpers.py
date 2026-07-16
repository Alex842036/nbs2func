from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from nbs2func.config import Nbs2FuncConfig, config_from_dict, config_to_dict
from nbs2func.core.minecraft_version import (
    MinecraftVersionError,
    get_minecraft_version_profile,
    supported_minecraft_versions,
)


GUI_MINECRAFT_VERSION_CHOICES = supported_minecraft_versions()
Translate = Callable[..., str]

DIRECTION_DISPLAY_TO_VALUE = {
    "east (+x)": "east",
    "west (-x)": "west",
    "south (+z)": "south",
    "north (-z)": "north",
}
DIRECTION_VALUE_TO_DISPLAY = {
    value: label for label, value in DIRECTION_DISPLAY_TO_VALUE.items()
}

OUTPUT_FORMAT_CHOICES = ("datapack", "schem", "both")
NOTE_PROFILE_CHOICES = ("safe", "balanced", "dense", "custom")
TRACK_BASED_GUI_FIELDS = (
    "min_distance",
)

NOTE_PRESETS = {
    "safe": {
        "max_candidates_per_emitter": 128,
        "retry_max_candidates_per_emitter": 384,
        "max_candidate_y_layers": 10,
        "max_candidate_lateral_positions": 24,
        "radius_search_tolerance": 6.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.0,
    },
    "balanced": {
        "max_candidates_per_emitter": 64,
        "retry_max_candidates_per_emitter": 256,
        "max_candidate_y_layers": 8,
        "max_candidate_lateral_positions": 16,
        "radius_search_tolerance": 4.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.0,
    },
    "dense": {
        "max_candidates_per_emitter": 48,
        "retry_max_candidates_per_emitter": 192,
        "max_candidate_y_layers": 6,
        "max_candidate_lateral_positions": 12,
        "radius_search_tolerance": 3.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.25,
    },
}


def direction_display_to_value(display: str) -> str:
    return DIRECTION_DISPLAY_TO_VALUE.get(display, display)


def direction_value_to_display(value: str) -> str:
    return DIRECTION_VALUE_TO_DISPLAY.get(value, "east (+x)")


def localized_direction_choices(translate: Translate) -> dict[str, str]:
    return {
        translate(f"step.layout_options.direction.{value}"): value
        for value in ("east", "west", "south", "north")
    }


def localized_direction_value_to_display(value: str, translate: Translate) -> str:
    choices = localized_direction_choices(translate)
    return next((label for label, canonical in choices.items() if canonical == value), value)


def modules_require_runtime_logic(config: Nbs2FuncConfig) -> bool:
    return config.enable_starter_module or config.enable_playback_assist


def is_output_format_selectable(config: Nbs2FuncConfig, output_format: str) -> bool:
    if output_format == "schem" and modules_require_runtime_logic(config):
        return False
    return output_format in OUTPUT_FORMAT_CHOICES


def datapack_group_enabled(output_format: str) -> bool:
    return output_format in {"datapack", "both"}


def fallback_output_format(config: Nbs2FuncConfig) -> str:
    if is_output_format_selectable(config, config.output_format):
        return config.output_format
    return "both"


def preset_matches_config(config: Nbs2FuncConfig, profile: str) -> bool:
    preset = NOTE_PRESETS.get(profile)
    if preset is None:
        return False
    for field, expected in preset.items():
        if getattr(config, field) != expected:
            return False
    return True


def infer_note_profile(config: Nbs2FuncConfig, current_profile: str) -> str:
    if current_profile == "custom":
        return "custom"
    if preset_matches_config(config, current_profile):
        return current_profile
    for profile in ("safe", "balanced", "dense"):
        if preset_matches_config(config, profile):
            return profile
    return "custom"


def parse_int(
    value: str,
    label: str,
    *,
    allow_empty: bool = False,
    min_value: int | None = None,
    max_value: int | None = None,
    translate: Translate | None = None,
) -> int | None:
    if value == "" and allow_empty:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        message = (
            translate("validation.integer_required", field=label)
            if translate is not None
            else f"{label} must be an integer."
        )
        raise ValueError(message) from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(
            translate("validation.minimum", field=label, minimum=min_value)
            if translate is not None
            else f"{label} must be at least {min_value}."
        )
    if max_value is not None and parsed > max_value:
        raise ValueError(
            translate("validation.maximum", field=label, maximum=max_value)
            if translate is not None
            else f"{label} must be at most {max_value}."
        )
    return parsed


def parse_float(
    value: str,
    label: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    translate: Translate | None = None,
) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        message = (
            translate("validation.number_required", field=label)
            if translate is not None
            else f"{label} must be a number."
        )
        raise ValueError(message) from exc
    if not math.isfinite(parsed):
        raise ValueError(
            translate("validation.finite_required", field=label)
            if translate is not None
            else f"{label} must be a finite number."
        )
    if min_value is not None and parsed < min_value:
        raise ValueError(
            translate("validation.minimum", field=label, minimum=min_value)
            if translate is not None
            else f"{label} must be at least {min_value}."
        )
    if max_value is not None and parsed > max_value:
        raise ValueError(
            translate("validation.maximum", field=label, maximum=max_value)
            if translate is not None
            else f"{label} must be at most {max_value}."
        )
    return parsed


def origin_y_range_error(
    config: Nbs2FuncConfig,
    translate: Translate | None = None,
) -> str | None:
    try:
        profile = get_minecraft_version_profile(config.minecraft_version)
    except MinecraftVersionError as exc:
        return str(exc)
    sound_range = 48
    min_origin_y = profile.min_build_y + sound_range
    max_origin_y = profile.max_build_y - sound_range
    if min_origin_y <= config.origin_y <= max_origin_y:
        return None
    english = (
        f"For Minecraft {profile.version_id}, origin Y must be chosen so that "
        f"[origin_y - 48, origin_y + 48] stays within "
        f"{profile.min_build_y}..{profile.max_build_y}."
    )
    if translate is None:
        return english
    return translate(
        "validation.origin_y_range",
        version=profile.version_id,
        minimum=profile.min_build_y,
        maximum=profile.max_build_y,
    )


def validate_layout_options(
    config: Nbs2FuncConfig,
    translate: Translate | None = None,
) -> list[str]:
    errors: list[str] = []
    origin_error = origin_y_range_error(config, translate)
    if origin_error is not None:
        errors.append(origin_error)
    return errors


def absolute_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def absolute_path_text(value: str | Path) -> str:
    return str(absolute_path(value))


def input_stem(config: Nbs2FuncConfig) -> str:
    stem = Path(config.input_path).stem
    return stem or "nbs_song"


def default_schematic_name(config: Nbs2FuncConfig) -> str:
    return input_stem(config)


def default_datapack_folder_name(config: Nbs2FuncConfig) -> str:
    if config.datapack_name:
        return config.datapack_name
    return input_stem(config)


def normalize_gui_config(config: Nbs2FuncConfig) -> Nbs2FuncConfig:
    data = config_to_dict(config)
    data["input_path"] = absolute_path_text(config.input_path)
    data["output"] = absolute_path_text(config.output)
    if config.schematic_output is None:
        data["schematic_output"] = data["output"]
    else:
        data["schematic_output"] = absolute_path_text(config.schematic_output)
    if not config.schematic_name:
        data["schematic_name"] = default_schematic_name(config)
    return config_from_dict(data)


def apply_track_based_gui_defaults(config: Nbs2FuncConfig) -> Nbs2FuncConfig:
    if config.layout_mode != "track_based_stereo":
        return config
    data = config_to_dict(config)
    data.update(
        {
            "max_hearing_distance": 48,
            "max_stereo_angle_degrees": 90,
            "center_split_policy": "auto_on_collision",
            "center_split_mode": "duplicate_half_volume",
            "enable_collision_resolver": True,
        }
    )
    return config_from_dict(data)


def direction_vector(direction: str) -> tuple[int, int]:
    canonical = direction_display_to_value(direction)
    vectors = {
        "east": (1, 0),
        "west": (-1, 0),
        "south": (0, 1),
        "north": (0, -1),
    }
    return vectors[canonical]


def layout_origin(config: Nbs2FuncConfig) -> tuple[int, int, int]:
    return config.origin_x, config.origin_y, config.origin_z


def starter_origin(config: Nbs2FuncConfig) -> tuple[int, int, int]:
    return config.command_block_x, config.command_block_y, config.command_block_z


def resolved_starter_origin(config: Nbs2FuncConfig) -> tuple[int, int, int]:
    return offset_behind(layout_origin(config), config.direction, 10)


def offset_behind(
    reference: tuple[int, int, int],
    direction: str,
    distance: int,
) -> tuple[int, int, int]:
    dx, dz = direction_vector(direction)
    x, y, z = reference
    return x - dx * distance, y, z - dz * distance


def is_behind(
    candidate: tuple[int, int, int],
    reference: tuple[int, int, int],
    direction: str,
) -> bool:
    dx, dz = direction_vector(direction)
    return (candidate[0] - reference[0]) * dx + (
        candidate[2] - reference[2]
    ) * dz < 0


def starter_origin_error(
    config: Nbs2FuncConfig,
    translate: Translate | None = None,
) -> str | None:
    if not config.enable_starter_module:
        return None
    if is_behind(starter_origin(config), layout_origin(config), config.direction):
        return None
    display = direction_value_to_display(config.direction)
    if translate is not None and config.direction in {"east", "west", "south", "north"}:
        return translate(f"validation.starter.{config.direction}")
    if config.direction == "east":
        return (
            "For east (+x), starter origin X must be smaller than layout origin X "
            "so the starter is placed before the track."
        )
    if config.direction == "west":
        return (
            "For west (-x), starter origin X must be greater than layout origin X "
            "so the starter is placed before the track."
        )
    if config.direction == "south":
        return (
            "For south (+z), starter origin Z must be smaller than layout origin Z "
            "so the starter is placed before the track."
        )
    if config.direction == "north":
        return (
            "For north (-z), starter origin Z must be greater than layout origin Z "
            "so the starter is placed before the track."
        )
    if translate is not None:
        return translate("validation.starter.generic", direction=display)
    return f"For {display}, starter origin must be behind the layout origin."


def resolved_command_module_origin(
    config: Nbs2FuncConfig,
    *,
    use_existing: bool = True,
) -> tuple[int, int, int]:
    if use_existing and (
        config.command_module_origin_x is not None
        and config.command_module_origin_y is not None
        and config.command_module_origin_z is not None
    ):
        return (
            config.command_module_origin_x,
            config.command_module_origin_y,
            config.command_module_origin_z,
        )
    return offset_behind(starter_origin(config), config.direction, 5)


def command_module_origin_error(
    config: Nbs2FuncConfig,
    translate: Translate | None = None,
) -> str | None:
    if not config.enable_playback_assist:
        return None
    command_origin = resolved_command_module_origin(config)
    reference = starter_origin(config)
    if is_behind(command_origin, reference, config.direction):
        return None
    if translate is not None and config.direction in {"east", "west", "south", "north"}:
        return translate(f"validation.command.{config.direction}")
    if config.direction == "east":
        return (
            "For east (+x), command module origin X must be smaller than starter "
            "origin X."
        )
    if config.direction == "west":
        return (
            "For west (-x), command module origin X must be greater than starter "
            "origin X."
        )
    if config.direction == "south":
        return (
            "For south (+z), command module origin Z must be smaller than starter "
            "origin Z."
        )
    if config.direction == "north":
        return (
            "For north (-z), command module origin Z must be greater than starter "
            "origin Z."
        )
    if translate is not None:
        return translate("validation.command.generic")
    return "Command module origin must be behind starter origin."


def resolved_vehicle_spawn_position(config: Nbs2FuncConfig) -> tuple[int, int, int]:
    if config.enable_playback_assist:
        return offset_behind(starter_origin(config), config.direction, 1)
    if (
        config.vehicle_spawn_x is not None
        and config.vehicle_spawn_y is not None
        and config.vehicle_spawn_z is not None
    ):
        return config.vehicle_spawn_x, config.vehicle_spawn_y, config.vehicle_spawn_z
    return offset_behind(layout_origin(config), config.direction, 10)


def resolve_gui_generation_config(config: Nbs2FuncConfig) -> Nbs2FuncConfig:
    resolved = apply_track_based_gui_defaults(normalize_gui_config(config))
    data = config_to_dict(resolved)
    data["music_start_x"] = resolved.origin_x
    data["music_start_y"] = resolved.origin_y
    data["music_start_z"] = resolved.origin_z
    data["game_ticks_per_song_tick"] = 4
    if resolved.enable_playback_assist:
        command_origin = resolved_command_module_origin(resolved)
        vehicle_spawn = resolved_vehicle_spawn_position(resolved)
        data["command_module_origin_x"] = command_origin[0]
        data["command_module_origin_y"] = command_origin[1]
        data["command_module_origin_z"] = command_origin[2]
        data["vehicle_spawn_x"] = vehicle_spawn[0]
        data["vehicle_spawn_y"] = vehicle_spawn[1]
        data["vehicle_spawn_z"] = vehicle_spawn[2]
    return config_from_dict(data)


def validate_module_coordinates(
    config: Nbs2FuncConfig,
    translate: Translate | None = None,
) -> list[str]:
    errors: list[str] = []
    starter_error = starter_origin_error(config, translate)
    if starter_error is not None:
        errors.append(starter_error)
    command_error = command_module_origin_error(config, translate)
    if command_error is not None:
        errors.append(command_error)
    return errors


def datapack_output_folder(config: Nbs2FuncConfig) -> Path:
    return absolute_path(config.output)


def schematic_output_folder(config: Nbs2FuncConfig) -> Path:
    if config.schematic_output:
        path = Path(config.schematic_output)
        return absolute_path(path.parent if path.suffix.lower() == ".schem" else path)
    return absolute_path(config.output)
