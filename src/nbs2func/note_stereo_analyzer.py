from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field, is_dataclass
from math import sqrt
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .models import NoteEvent


PERCUSSION_INSTRUMENTS = frozenset({2, 3, 4})
STANDARD_GROUPING_MODES = frozenset(
    {
        "midi_instrument",
        "instrument_mixed",
        "instrument_split",
        "pan_region",
        "percussion",
        "manual_mixed",
    }
)
STANDARD_LAYER_PARTS = frozenset(
    {
        "head",
        "main",
        "support",
        "tail",
        "left_tail",
        "right_tail",
        "inner_tail",
        "outer_tail",
        "unknown",
    }
)
STANDARD_PAN_REGIONS = frozenset(
    {
        "far_left",
        "left",
        "center",
        "right",
        "far_right",
        "wide",
        "unknown",
    }
)
TAIL_LAYER_PARTS = frozenset(
    {
        "tail",
        "left_tail",
        "right_tail",
        "inner_tail",
        "outer_tail",
    }
)
WINDOW_TEXTURE_PERCUSSION_RATIO = 0.75
WINDOW_TEXTURE_MIN_EFFECT_NOTES = 3
WINDOW_TEXTURE_MIN_EFFECT_ACTIVE_TICKS = 3
WINDOW_TEXTURE_SUSTAIN_MIN_NOTE_COUNT = 6
WINDOW_TEXTURE_SUSTAIN_MIN_DENSITY = 0.04
WINDOW_TEXTURE_STABLE_PITCH_STD_MAX = 1.5
WINDOW_TEXTURE_TAIL_ACTIVITY_RATIO = 0.5
WINDOW_TEXTURE_LAYERED_MULTI_TICK_RATIO = 0.25
WINDOW_TEXTURE_LAYERED_MEAN_NOTES_PER_ACTIVE_TICK = 1.5
WINDOW_TEXTURE_REPEATED_MIN_NOTES = 6
WINDOW_TEXTURE_REPEATED_MIN_ACTIVE_TICKS = 4
WINDOW_TEXTURE_REPEATED_REGULARITY_SCORE = 0.8
WINDOW_TEXTURE_SINGLE_LINE_MAX_MEAN_NOTES_PER_ACTIVE_TICK = 1.15
WINDOW_TEXTURE_SINGLE_LINE_MAX_MULTI_TICK_RATIO = 0.1

_INSTRUMENT_NAMES: dict[int, str] = {
    0: "harp",
    1: "bass",
    2: "basedrum",
    3: "snare",
    4: "hat",
    5: "guitar",
    6: "flute",
    7: "bell",
    8: "chime",
    9: "xylophone",
    10: "iron_xylophone",
    11: "cow_bell",
    12: "didgeridoo",
    13: "bit",
    14: "banjo",
    15: "pling",
    16: "copper",
    17: "exposed_copper",
    18: "weathered_copper",
    19: "oxidized_copper",
}


@dataclass(frozen=True)
class LayerGroupConfig:
    name: str
    layers: tuple[int, ...]
    grouping_mode: str = "manual_mixed"
    pan_region: str = "unknown"
    layer_parts: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        layers = tuple(self.layers)
        if not self.name:
            raise ValueError("Group name must not be empty")
        if not layers:
            raise ValueError("Group layers must not be empty")
        if self.grouping_mode not in STANDARD_GROUPING_MODES:
            raise ValueError(f"Unknown grouping_mode: {self.grouping_mode}")
        if self.pan_region not in STANDARD_PAN_REGIONS:
            raise ValueError(f"Unknown pan_region: {self.pan_region}")

        normalized_layer_parts = _normalize_layer_parts(self.layer_parts)
        unknown_layer_parts = [
            part
            for part in normalized_layer_parts.values()
            if part not in STANDARD_LAYER_PARTS
        ]
        if unknown_layer_parts:
            raise ValueError(f"Unknown layer part: {unknown_layer_parts[0]}")

        configured_layers = set(layers)
        unknown_layers = [
            layer
            for layer in normalized_layer_parts
            if layer not in configured_layers
        ]
        if unknown_layers:
            raise ValueError(
                "Layer part references layer outside group: "
                f"{unknown_layers[0]}"
            )

        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "layer_parts", normalized_layer_parts)


def load_group_config(path: str | Path) -> tuple[LayerGroupConfig, ...]:
    """Load user-provided layer group configuration."""

    config_path = Path(path)
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid group config JSON: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ValueError("Group config must be a JSON object")
    if "groups" not in raw_config:
        raise ValueError("Group config is missing required field: groups")

    raw_groups = raw_config["groups"]
    if not isinstance(raw_groups, list):
        raise ValueError("Group config field 'groups' must be a list")

    groups: list[LayerGroupConfig] = []
    for index, raw_group in enumerate(raw_groups):
        groups.append(_parse_group_config(raw_group, index))

    return tuple(groups)


def analyze_note_stereo(
    notes: Iterable[NoteEvent],
    group_configs: Iterable[LayerGroupConfig] | None = None,
    window_size: int = 128,
    hop_size: int = 32,
) -> dict[str, Any]:
    """Analyze note events without changing layout or generated output."""

    note_events = tuple(notes)
    groups = tuple(group_configs or ())

    notes_by_layer: dict[int, list[NoteEvent]] = {}
    for note in note_events:
        notes_by_layer.setdefault(note.layer, []).append(note)

    layer_reports = [
        _build_layer_report(layer_id, notes_by_layer[layer_id])
        for layer_id in sorted(notes_by_layer)
    ]
    group_reports = [
        _build_group_report(
            group_config,
            note_events,
            notes_by_layer,
            window_size=window_size,
            hop_size=hop_size,
        )
        for group_config in groups
    ]

    return {
        "layers": layer_reports,
        "groups": group_reports,
    }


def analysis_report_to_jsonable(report: Any) -> Any:
    """Convert analyzer output to JSON-serializable primitive containers."""

    if is_dataclass(report):
        return analysis_report_to_jsonable(asdict(report))
    if isinstance(report, dict):
        return {
            str(key): analysis_report_to_jsonable(value)
            for key, value in report.items()
        }
    if isinstance(report, (list, tuple)):
        return [analysis_report_to_jsonable(value) for value in report]
    return report


def compute_group_windows(
    notes: Iterable[NoteEvent],
    group_config: LayerGroupConfig,
    window_size: int = 128,
    hop_size: int = 32,
) -> list[dict[str, Any]]:
    """Compute fixed-window group features for future vector-based analysis."""

    if window_size <= 0:
        raise ValueError("window_size must be positive")
    if hop_size <= 0:
        raise ValueError("hop_size must be positive")

    configured_layers = set(group_config.layers)
    group_notes = tuple(
        note
        for note in notes
        if note.layer in configured_layers
    )
    if not group_notes:
        return []

    max_tick = max(note.tick for note in group_notes)
    windows: list[dict[str, Any]] = []
    tick_start = 0
    while tick_start <= max_tick:
        tick_end = tick_start + window_size
        window_notes = [
            note
            for note in group_notes
            if tick_start <= note.tick < tick_end
        ]
        windows.append(
            _build_window_report(
                group_config,
                group_config.layers,
                window_notes,
                tick_start=tick_start,
                tick_end=tick_end,
            )
        )
        tick_start += hop_size

    return windows


def _parse_group_config(raw_group: Any, index: int) -> LayerGroupConfig:
    if not isinstance(raw_group, dict):
        raise ValueError(f"Group config entry {index} must be an object")

    missing_fields = [
        field
        for field in ("name", "layers")
        if field not in raw_group
    ]
    if missing_fields:
        joined = ", ".join(missing_fields)
        raise ValueError(f"Group config entry {index} is missing: {joined}")

    name = raw_group["name"]
    layers = raw_group["layers"]
    grouping_mode = raw_group.get("grouping_mode", "manual_mixed")
    pan_region = raw_group.get("pan_region", "unknown")
    layer_parts = raw_group.get("layer_parts", {})

    if not isinstance(name, str) or not name:
        raise ValueError(f"Group config entry {index} field 'name' must be a string")
    if not isinstance(layers, list):
        raise ValueError(f"Group config entry {index} field 'layers' must be a list")
    if not layers:
        raise ValueError(f"Group config entry {index} field 'layers' must not be empty")
    if not all(isinstance(layer, int) for layer in layers):
        raise ValueError(
            f"Group config entry {index} field 'layers' must contain integers"
        )
    if "role" in raw_group:
        raise ValueError("Group config field 'role' is no longer supported")
    if "layer_roles" in raw_group:
        raise ValueError("Group config field 'layer_roles' is no longer supported")
    if not isinstance(grouping_mode, str) or not grouping_mode:
        raise ValueError(
            f"Group config entry {index} field 'grouping_mode' must be a string"
        )
    if not isinstance(pan_region, str) or not pan_region:
        raise ValueError(
            f"Group config entry {index} field 'pan_region' must be a string"
        )
    if not isinstance(layer_parts, dict):
        raise ValueError(
            f"Group config entry {index} field 'layer_parts' must be an object"
        )

    return LayerGroupConfig(
        name=name,
        layers=tuple(layers),
        grouping_mode=grouping_mode,
        pan_region=pan_region,
        layer_parts=layer_parts,
    )


def _normalize_layer_parts(layer_parts: dict[Any, str]) -> dict[int, str]:
    normalized: dict[int, str] = {}
    for raw_layer, part in layer_parts.items():
        try:
            layer = int(raw_layer)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Layer part key must be an integer: {raw_layer}") from exc
        if not isinstance(part, str) or not part:
            raise ValueError(f"Layer part for layer {layer} must be a string")
        normalized[layer] = part
    return normalized


def _build_layer_report(layer_id: int, notes: list[NoteEvent]) -> dict[str, Any]:
    note_count = len(notes)
    return {
        "layer_id": layer_id,
        "note_count": note_count,
        "tick_start": min((note.tick for note in notes), default=None),
        "tick_end": max((note.tick for note in notes), default=None),
        "instrument_counts": _instrument_counts(notes),
        "role_guess": _guess_role(notes),
        "volume": _numeric_summary(note.final_volume for note in notes),
        "pan": _numeric_summary(note.final_panning for note in notes),
        "pitch": _pitch_summary(notes),
        "rhythm": _rhythm_summary(notes),
        "density": _density_summary(notes),
    }


def _build_group_report(
    group_config: LayerGroupConfig,
    all_notes: tuple[NoteEvent, ...],
    notes_by_layer: dict[int, list[NoteEvent]],
    *,
    window_size: int,
    hop_size: int,
) -> dict[str, Any]:
    configured_layers = set(group_config.layers)
    group_notes = [
        note
        for note in all_notes
        if note.layer in configured_layers
    ]
    present_layers = set(notes_by_layer)
    missing_layers = [
        layer
        for layer in group_config.layers
        if layer not in present_layers
    ]

    return {
        "name": group_config.name,
        "layers": list(group_config.layers),
        "grouping_mode": group_config.grouping_mode,
        "pan_region": group_config.pan_region,
        "layer_parts": dict(group_config.layer_parts),
        "note_count": len(group_notes),
        "tick_start": min((note.tick for note in group_notes), default=None),
        "tick_end": max((note.tick for note in group_notes), default=None),
        "missing_layers": missing_layers,
        "instrument_counts": _instrument_counts(group_notes),
        "role_guess": _guess_role(group_notes),
        "volume": _numeric_summary(note.final_volume for note in group_notes),
        "pan": _numeric_summary(note.final_panning for note in group_notes),
        "pitch": _pitch_summary(group_notes),
        "rhythm": _rhythm_summary(group_notes),
        "density": _density_summary(group_notes),
        "layer_activity": _layer_activity(group_config.layers, group_notes),
        "windows": compute_group_windows(
            all_notes,
            group_config,
            window_size=window_size,
            hop_size=hop_size,
        ),
    }


def _build_window_report(
    group_config: LayerGroupConfig,
    layers: tuple[int, ...],
    notes: list[NoteEvent],
    *,
    tick_start: int,
    tick_end: int,
) -> dict[str, Any]:
    density = _density_summary(
        notes,
        tick_start=tick_start,
        tick_end=tick_end,
    )
    instrument_counts = _instrument_counts(notes)
    pitch = _pitch_summary(notes)
    rhythm = _rhythm_summary(notes)
    layer_activity = _layer_activity(layers, notes)
    simultaneity = _simultaneity_summary(notes)

    return {
        "tick_start": tick_start,
        "tick_end": tick_end,
        "note_count": len(notes),
        "density": density,
        "instrument_counts": instrument_counts,
        "volume": _numeric_summary(note.final_volume for note in notes),
        "pan": _numeric_summary(note.final_panning for note in notes),
        "pitch": pitch,
        "rhythm": rhythm,
        "layer_activity": layer_activity,
        "simultaneity": simultaneity,
        "window_texture_guess": _guess_window_texture(
            group_config,
            notes,
            density=density,
            instrument_counts=instrument_counts,
            pitch=pitch,
            rhythm=rhythm,
            layer_activity=layer_activity,
            simultaneity=simultaneity,
        ),
    }


def _instrument_counts(notes: Iterable[NoteEvent]) -> dict[str, int]:
    counts = Counter(_instrument_name(note.instrument) for note in notes)
    return {
        instrument: counts[instrument]
        for instrument in sorted(counts)
    }


def _instrument_name(instrument: int) -> str:
    return _INSTRUMENT_NAMES.get(instrument, str(instrument))


def _guess_role(notes: Iterable[NoteEvent]) -> str:
    note_events = tuple(notes)
    note_count = len(note_events)
    if note_count == 0:
        return "unknown"

    percussion_count = sum(
        1
        for note in note_events
        if note.instrument in PERCUSSION_INSTRUMENTS
    )
    if percussion_count == note_count:
        return "percussion"
    if percussion_count / note_count >= 0.9:
        return "mostly_percussion"
    return "unknown"


def _guess_window_texture(
    group_config: LayerGroupConfig,
    notes: list[NoteEvent],
    *,
    density: dict[str, float | int],
    instrument_counts: dict[str, int],
    pitch: dict[str, float | int | None],
    rhythm: dict[str, float | int | None],
    layer_activity: list[dict[str, float | int]],
    simultaneity: dict[str, float | int],
) -> str:
    note_count = len(notes)
    if note_count == 0:
        return "empty"

    percussion_like = _is_percussion_texture(
        group_config,
        instrument_counts,
        note_count,
    )
    layered_like = _is_layered_texture(density, simultaneity)
    repeated_like = _is_repeated_texture(note_count, density, rhythm)
    sustain_like = _is_sustain_texture(
        group_config,
        density,
        pitch,
        layer_activity,
        note_count,
    )
    single_line_like = _is_single_line_texture(density, simultaneity)

    if layered_like and repeated_like and not sustain_like:
        return "mixed_like"

    if percussion_like:
        return "percussion_like"

    if (
        note_count < WINDOW_TEXTURE_MIN_EFFECT_NOTES
        or density["active_tick_count"] < WINDOW_TEXTURE_MIN_EFFECT_ACTIVE_TICKS
    ):
        return "effect_or_transition_like"

    if sustain_like:
        return "sustain_texture_like"
    if layered_like:
        return "layered_or_chord_like"
    if repeated_like:
        return "repeated_pattern_like"
    if single_line_like:
        return "single_line_like"
    return "unknown"


def _is_percussion_texture(
    group_config: LayerGroupConfig,
    instrument_counts: dict[str, int],
    note_count: int,
) -> bool:
    if group_config.grouping_mode == "percussion":
        return True

    percussion_count = sum(
        instrument_counts.get(_instrument_name(instrument), 0)
        for instrument in PERCUSSION_INSTRUMENTS
    )
    return percussion_count / note_count >= WINDOW_TEXTURE_PERCUSSION_RATIO


def _is_layered_texture(
    density: dict[str, float | int],
    simultaneity: dict[str, float | int],
) -> bool:
    return (
        simultaneity["max_notes_per_tick"] >= 2
        and (
            simultaneity["multi_note_tick_ratio"]
            >= WINDOW_TEXTURE_LAYERED_MULTI_TICK_RATIO
            or density["mean_notes_per_active_tick"]
            >= WINDOW_TEXTURE_LAYERED_MEAN_NOTES_PER_ACTIVE_TICK
        )
    )


def _is_repeated_texture(
    note_count: int,
    density: dict[str, float | int],
    rhythm: dict[str, float | int | None],
) -> bool:
    regularity_score = rhythm["regularity_score"]
    return (
        note_count >= WINDOW_TEXTURE_REPEATED_MIN_NOTES
        and density["active_tick_count"] >= WINDOW_TEXTURE_REPEATED_MIN_ACTIVE_TICKS
        and regularity_score is not None
        and regularity_score >= WINDOW_TEXTURE_REPEATED_REGULARITY_SCORE
    )


def _is_sustain_texture(
    group_config: LayerGroupConfig,
    density: dict[str, float | int],
    pitch: dict[str, float | int | None],
    layer_activity: list[dict[str, float | int]],
    note_count: int,
) -> bool:
    if note_count < WINDOW_TEXTURE_SUSTAIN_MIN_NOTE_COUNT:
        return False

    pitch_std = pitch["std"]
    pitch_is_stable = (
        pitch_std is not None
        and pitch_std <= WINDOW_TEXTURE_STABLE_PITCH_STD_MAX
    )
    dense_enough = density["note_density"] >= WINDOW_TEXTURE_SUSTAIN_MIN_DENSITY
    tail_activity_ratio = _tail_activity_ratio(group_config, layer_activity)

    return (
        (tail_activity_ratio >= WINDOW_TEXTURE_TAIL_ACTIVITY_RATIO and dense_enough)
        or (pitch_is_stable and dense_enough)
    )


def _is_single_line_texture(
    density: dict[str, float | int],
    simultaneity: dict[str, float | int],
) -> bool:
    return (
        density["mean_notes_per_active_tick"]
        <= WINDOW_TEXTURE_SINGLE_LINE_MAX_MEAN_NOTES_PER_ACTIVE_TICK
        and simultaneity["multi_note_tick_ratio"]
        <= WINDOW_TEXTURE_SINGLE_LINE_MAX_MULTI_TICK_RATIO
    )


def _tail_activity_ratio(
    group_config: LayerGroupConfig,
    layer_activity: list[dict[str, float | int]],
) -> float:
    tail_layers = {
        layer
        for layer, part in group_config.layer_parts.items()
        if part in TAIL_LAYER_PARTS
    }
    if not tail_layers:
        return 0.0

    return sum(
        activity["ratio"]
        for activity in layer_activity
        if activity["layer_id"] in tail_layers
    )


def _numeric_summary(values: Iterable[float]) -> dict[str, float | None]:
    numbers = tuple(values)
    if not numbers:
        return {
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
        }

    mean_value = sum(numbers) / len(numbers)
    variance = sum((value - mean_value) ** 2 for value in numbers) / len(numbers)
    return {
        "mean": mean_value,
        "std": sqrt(variance),
        "min": min(numbers),
        "max": max(numbers),
    }


def _pitch_summary(notes: Iterable[NoteEvent]) -> dict[str, float | int | None]:
    note_events = tuple(notes)
    summary = _numeric_summary(note.key for note in note_events)
    pitch_counts = Counter(note.key for note in note_events)
    dominant_pitch = None
    if pitch_counts:
        dominant_pitch = min(
            pitch_counts,
            key=lambda pitch: (-pitch_counts[pitch], pitch),
        )

    return {
        **summary,
        "dominant_pitch": dominant_pitch,
    }


def _rhythm_summary(notes: Iterable[NoteEvent]) -> dict[str, float | int | None]:
    active_ticks = sorted({note.tick for note in notes})
    gaps = [
        current_tick - previous_tick
        for previous_tick, current_tick in zip(active_ticks, active_ticks[1:])
    ]
    if not gaps:
        return {
            "avg_tick_gap": None,
            "median_tick_gap": None,
            "most_common_tick_gap": None,
            "regularity_score": None,
        }

    gap_counts = Counter(gaps)
    most_common_tick_gap = min(
        gap_counts,
        key=lambda gap: (-gap_counts[gap], gap),
    )
    return {
        "avg_tick_gap": sum(gaps) / len(gaps),
        "median_tick_gap": median(gaps),
        "most_common_tick_gap": most_common_tick_gap,
        "regularity_score": gap_counts[most_common_tick_gap] / len(gaps),
    }


def _density_summary(
    notes: Iterable[NoteEvent],
    tick_start: int | None = None,
    tick_end: int | None = None,
) -> dict[str, float | int]:
    note_events = tuple(notes)
    if not note_events:
        return {
            "note_density": 0.0,
            "active_tick_count": 0,
            "mean_notes_per_active_tick": 0.0,
        }

    active_tick_count = len({note.tick for note in note_events})
    if tick_start is None or tick_end is None:
        tick_start = min(note.tick for note in note_events)
        tick_end = max(note.tick for note in note_events) + 1
    tick_span = tick_end - tick_start

    return {
        "note_density": len(note_events) / tick_span,
        "active_tick_count": active_tick_count,
        "mean_notes_per_active_tick": len(note_events) / active_tick_count,
    }


def _layer_activity(
    layers: tuple[int, ...],
    notes: Iterable[NoteEvent],
) -> list[dict[str, float | int]]:
    note_events = tuple(notes)
    total_notes = len(note_events)
    note_counts = Counter(note.layer for note in note_events)

    return [
        {
            "layer_id": layer,
            "note_count": note_counts[layer],
            "ratio": note_counts[layer] / total_notes if total_notes else 0.0,
        }
        for layer in layers
    ]


def _simultaneity_summary(notes: Iterable[NoteEvent]) -> dict[str, float | int]:
    note_events = tuple(notes)
    if not note_events:
        return {
            "max_notes_per_tick": 0,
            "multi_note_tick_ratio": 0.0,
        }

    notes_by_tick = Counter(note.tick for note in note_events)
    active_tick_count = len(notes_by_tick)
    multi_note_tick_count = sum(
        1
        for note_count in notes_by_tick.values()
        if note_count > 1
    )
    return {
        "max_notes_per_tick": max(notes_by_tick.values()),
        "multi_note_tick_ratio": multi_note_tick_count / active_tick_count,
    }
