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
STANDARD_GROUP_ROLES = frozenset(
    {
        "percussion",
        "lead",
        "sustain_group",
        "accompaniment",
        "bass",
        "arpeggio",
        "effect",
        "unknown",
    }
)
STANDARD_LAYER_ROLES = frozenset(
    {
        "head",
        "left_tail",
        "right_tail",
        "tail",
        "main",
        "support",
        "unknown",
    }
)

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
    role: str = "unknown"
    layer_roles: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        layers = tuple(self.layers)
        if self.role not in STANDARD_GROUP_ROLES:
            raise ValueError(f"Unknown group role: {self.role}")

        normalized_layer_roles = _normalize_layer_roles(self.layer_roles)
        unknown_layer_roles = [
            role
            for role in normalized_layer_roles.values()
            if role not in STANDARD_LAYER_ROLES
        ]
        if unknown_layer_roles:
            raise ValueError(f"Unknown layer role: {unknown_layer_roles[0]}")

        configured_layers = set(layers)
        unknown_layers = [
            layer
            for layer in normalized_layer_roles
            if layer not in configured_layers
        ]
        if unknown_layers:
            raise ValueError(
                "Layer role references layer outside group: "
                f"{unknown_layers[0]}"
            )

        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "layer_roles", normalized_layer_roles)


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
        _build_group_report(group_config, note_events, notes_by_layer)
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
    role = raw_group.get("role", "unknown")
    layer_roles = raw_group.get("layer_roles", {})

    if not isinstance(name, str) or not name:
        raise ValueError(f"Group config entry {index} field 'name' must be a string")
    if not isinstance(layers, list):
        raise ValueError(f"Group config entry {index} field 'layers' must be a list")
    if not all(isinstance(layer, int) for layer in layers):
        raise ValueError(
            f"Group config entry {index} field 'layers' must contain integers"
        )
    if not isinstance(role, str) or not role:
        raise ValueError(f"Group config entry {index} field 'role' must be a string")
    if not isinstance(layer_roles, dict):
        raise ValueError(
            f"Group config entry {index} field 'layer_roles' must be an object"
        )

    return LayerGroupConfig(
        name=name,
        layers=tuple(layers),
        role=role,
        layer_roles=layer_roles,
    )


def _normalize_layer_roles(layer_roles: dict[Any, str]) -> dict[int, str]:
    normalized: dict[int, str] = {}
    for raw_layer, role in layer_roles.items():
        try:
            layer = int(raw_layer)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Layer role key must be an integer: {raw_layer}") from exc
        if not isinstance(role, str) or not role:
            raise ValueError(f"Layer role for layer {layer} must be a string")
        normalized[layer] = role
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
        "role": group_config.role,
        "layer_roles": dict(group_config.layer_roles),
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
        "windows": compute_group_windows(all_notes, group_config),
    }


def _build_window_report(
    layers: tuple[int, ...],
    notes: list[NoteEvent],
    *,
    tick_start: int,
    tick_end: int,
) -> dict[str, Any]:
    return {
        "tick_start": tick_start,
        "tick_end": tick_end,
        "note_count": len(notes),
        "density": _density_summary(
            notes,
            tick_start=tick_start,
            tick_end=tick_end,
        ),
        "instrument_counts": _instrument_counts(notes),
        "volume": _numeric_summary(note.final_volume for note in notes),
        "pan": _numeric_summary(note.final_panning for note in notes),
        "pitch": _pitch_summary(notes),
        "rhythm": _rhythm_summary(notes),
        "layer_activity": _layer_activity(layers, notes),
        "simultaneity": _simultaneity_summary(notes),
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
