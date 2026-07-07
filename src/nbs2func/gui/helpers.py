from __future__ import annotations

from pathlib import Path

from nbs2func.config import Nbs2FuncConfig
from nbs2func.core.minecraft_version import supported_minecraft_versions


GUI_MINECRAFT_VERSION_CHOICES = supported_minecraft_versions()

DIRECTION_DISPLAY_TO_VALUE = {
    "east (+x)": "east",
    "west (-x)": "west",
    "south (+z)": "south",
    "north (-z)": "north",
}
DIRECTION_VALUE_TO_DISPLAY = {
    value: label for label, value in DIRECTION_DISPLAY_TO_VALUE.items()
}

CENTER_SPLIT_POLICY_CHOICES = (
    "none",
    "manual",
    "auto_on_collision",
    "manual_plus_auto",
)
CENTER_SPLIT_MODE_CHOICES = ("duplicate_half_volume",)
OUTPUT_FORMAT_CHOICES = ("datapack", "schem", "both")
NOTE_PROFILE_CHOICES = ("safe", "balanced", "dense", "custom")

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


def modules_require_runtime_logic(config: Nbs2FuncConfig) -> bool:
    return config.enable_starter_module or config.enable_playback_assist


def is_output_format_selectable(config: Nbs2FuncConfig, output_format: str) -> bool:
    if output_format == "schem" and modules_require_runtime_logic(config):
        return False
    return output_format in OUTPUT_FORMAT_CHOICES


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


def parse_int(value: str, label: str, *, allow_empty: bool = False) -> int | None:
    if value == "" and allow_empty:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer.") from exc


def parse_float(value: str, label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc


def datapack_output_folder(config: Nbs2FuncConfig) -> Path:
    return Path(config.output)


def schematic_output_folder(config: Nbs2FuncConfig) -> Path:
    if config.schematic_output:
        path = Path(config.schematic_output)
        return path.parent if path.suffix.lower() == ".schem" else path
    return Path(config.output)
