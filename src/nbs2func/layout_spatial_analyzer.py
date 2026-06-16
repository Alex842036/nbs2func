from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from math import sqrt
from typing import Any, Iterable

from .models import NoteEvent, Song


PAN_BIN_NAMES = ("far_left", "left", "center", "right", "far_right")
VOLUME_BIN_NAMES = ("very_low", "low", "mid", "high", "max")

LAYOUT_SPATIAL_COMPONENT_WEIGHTS = {
    "pan_center_shift": 2.0,
    "pan_spread_shift": 1.0,
    "pan_bin_shift": 2.0,
    "volume_center_shift": 1.5,
    "volume_spread_shift": 0.8,
    "volume_bin_shift": 1.5,
    "active_change": 1.0,
}
LAYOUT_REGIME_MIN_SCORE = 0.35
LAYOUT_REGIME_MIN_TICK_GAP = 64
LAYOUT_REGIME_MAX_COUNT_PER_LAYER = 20
LAYOUT_SEGMENT_MIN_LENGTH_TICKS = 256
LAYOUT_SEGMENT_MAX_COUNT_PER_LAYER = 30


@dataclass(frozen=True)
class LayoutSpatialWindow:
    tick_start: int
    tick_end: int
    note_count: int
    active_tick_start: int | None
    active_tick_end: int | None
    pan: dict[str, float | None] | None
    volume: dict[str, float | None] | None
    pan_bins: dict[str, float] | None
    volume_bins: dict[str, float] | None


def analyze_layout_spatial(
    song: Song,
    *,
    window_size: int = 128,
    hop_size: int = 32,
) -> dict[str, Any]:
    """Analyze layer-local pan/volume patterns without touching layout output."""

    if window_size <= 0:
        raise ValueError("analysis window size must be greater than 0")
    if hop_size <= 0:
        raise ValueError("analysis hop size must be greater than 0")

    notes_by_layer: dict[int, list[NoteEvent]] = {}
    layer_names: dict[int, str] = {}
    known_layers: set[int] = set()

    for track in song.tracks:
        layer_id = track.source_layer if track.source_layer is not None else track.id
        known_layers.add(layer_id)
        layer_names.setdefault(layer_id, track.name)
        for note in track.notes:
            known_layers.add(note.layer)
            layer_names.setdefault(note.layer, track.name)
            notes_by_layer.setdefault(note.layer, []).append(note)

    layer_reports = [
        _build_layer_report(
            layer_id,
            layer_names.get(layer_id, f"Layer {layer_id}"),
            notes_by_layer.get(layer_id, []),
            window_size=window_size,
            hop_size=hop_size,
        )
        for layer_id in sorted(known_layers)
    ]

    return {
        "analysis_type": "layout_spatial",
        "overview": {
            "layer_count": len(layer_reports),
            "total_notes": sum(len(notes) for notes in notes_by_layer.values()),
            "window_size": window_size,
            "hop_size": hop_size,
        },
        "layers": layer_reports,
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


def detect_layout_regime_candidates(
    windows: list[LayoutSpatialWindow],
) -> list[dict[str, Any]]:
    raw_candidates: list[dict[str, Any]] = []
    sorted_windows = sorted(windows, key=lambda window: window.tick_start)

    for left, right in zip(sorted_windows, sorted_windows[1:]):
        if left.note_count == 0 and right.note_count == 0:
            continue

        components = _layout_change_components(left, right)
        weighted_components = {
            name: components[name] * LAYOUT_SPATIAL_COMPONENT_WEIGHTS[name]
            for name in LAYOUT_SPATIAL_COMPONENT_WEIGHTS
        }
        score = sum(weighted_components.values())
        if score < LAYOUT_REGIME_MIN_SCORE:
            continue

        raw_candidates.append(
            {
                "tick": right.tick_start,
                "score": score,
                "components": components,
                "weighted_components": weighted_components,
                "top_components": _top_components(weighted_components),
                "left_window_tick_start": left.tick_start,
                "right_window_tick_start": right.tick_start,
                "member_count": 1,
            }
        )

    return _cluster_layout_regime_candidates(raw_candidates)


def build_layout_segments_preview(
    layer_active_tick_start: int | None,
    layer_active_tick_end: int | None,
    candidates: list[dict[str, Any]],
    windows: list[LayoutSpatialWindow] | None = None,
) -> list[dict[str, Any]]:
    if layer_active_tick_start is None or layer_active_tick_end is None:
        return []

    segment_bounds = [layer_active_tick_start]
    for candidate in sorted(candidates, key=lambda item: item["tick"]):
        tick = int(candidate["tick"])
        if tick - segment_bounds[-1] < LAYOUT_SEGMENT_MIN_LENGTH_TICKS:
            continue
        if layer_active_tick_end - tick < LAYOUT_SEGMENT_MIN_LENGTH_TICKS:
            continue
        segment_bounds.append(tick)
        if len(segment_bounds) >= LAYOUT_SEGMENT_MAX_COUNT_PER_LAYER:
            break
    segment_bounds.append(layer_active_tick_end)

    preview: list[dict[str, Any]] = []
    available_windows = windows or []
    for start_tick, end_tick in zip(segment_bounds, segment_bounds[1:]):
        segment_windows = [
            window
            for window in available_windows
            if window.tick_start >= start_tick and window.tick_start < end_tick
        ]
        pan_mode = _guess_pan_mode(segment_windows)
        volume_mode = _guess_volume_mode(segment_windows)
        preview.append(
            {
                "start_tick": start_tick,
                "end_tick": end_tick,
                "duration_ticks": end_tick - start_tick,
                "window_count": len(segment_windows),
                "pan_mode": pan_mode,
                "volume_mode": volume_mode,
                "continuity_priority": _continuity_priority(
                    pan_mode,
                    volume_mode,
                ),
            }
        )

    return preview[:LAYOUT_SEGMENT_MAX_COUNT_PER_LAYER]


def _build_layer_report(
    layer_id: int,
    name: str,
    notes: list[NoteEvent],
    *,
    window_size: int,
    hop_size: int,
) -> dict[str, Any]:
    sorted_notes = sorted(notes, key=lambda note: (note.tick, note.key))
    active_tick_start = min((note.tick for note in sorted_notes), default=None)
    active_tick_end = max((note.tick for note in sorted_notes), default=None)
    windows = _build_windows(
        sorted_notes,
        active_tick_start=active_tick_start,
        active_tick_end=active_tick_end,
        window_size=window_size,
        hop_size=hop_size,
    )
    candidates = detect_layout_regime_candidates(windows)

    return {
        "layer_id": layer_id,
        "name": name,
        "note_count": len(sorted_notes),
        "active_tick_start": active_tick_start,
        "active_tick_end": active_tick_end,
        "window_count": len(windows),
        "pan_summary": _numeric_summary(
            note.final_panning for note in sorted_notes
        ),
        "volume_summary": _numeric_summary(
            note.final_volume for note in sorted_notes
        ),
        "windows": [analysis_report_to_jsonable(window) for window in windows],
        "layout_regime_candidates": candidates,
        "layout_segments_preview": build_layout_segments_preview(
            active_tick_start,
            active_tick_end,
            candidates,
            windows,
        ),
    }


def _build_windows(
    notes: list[NoteEvent],
    *,
    active_tick_start: int | None,
    active_tick_end: int | None,
    window_size: int,
    hop_size: int,
) -> list[LayoutSpatialWindow]:
    if active_tick_start is None or active_tick_end is None:
        return []

    windows: list[LayoutSpatialWindow] = []
    tick_start = active_tick_start
    while tick_start <= active_tick_end:
        tick_end = tick_start + window_size
        window_notes = [
            note
            for note in notes
            if tick_start <= note.tick < tick_end
        ]
        windows.append(
            _build_window(
                window_notes,
                tick_start=tick_start,
                tick_end=tick_end,
            )
        )
        tick_start += hop_size

    return windows


def _build_window(
    notes: list[NoteEvent],
    *,
    tick_start: int,
    tick_end: int,
) -> LayoutSpatialWindow:
    if not notes:
        return LayoutSpatialWindow(
            tick_start=tick_start,
            tick_end=tick_end,
            note_count=0,
            active_tick_start=None,
            active_tick_end=None,
            pan=None,
            volume=None,
            pan_bins=None,
            volume_bins=None,
        )

    return LayoutSpatialWindow(
        tick_start=tick_start,
        tick_end=tick_end,
        note_count=len(notes),
        active_tick_start=min(note.tick for note in notes),
        active_tick_end=max(note.tick for note in notes),
        pan=_numeric_summary(note.final_panning for note in notes),
        volume=_numeric_summary(note.final_volume for note in notes),
        # The project model stores NBS stereo panning on the 0..200 scale.
        pan_bins=_pan_bins(note.final_panning for note in notes),
        volume_bins=_volume_bins(note.final_volume for note in notes),
    )


def _layout_change_components(
    left: LayoutSpatialWindow,
    right: LayoutSpatialWindow,
) -> dict[str, float]:
    left_active = left.note_count > 0
    right_active = right.note_count > 0
    if not left_active or not right_active:
        return {
            "pan_center_shift": 0.0,
            "pan_spread_shift": 0.0,
            "pan_bin_shift": 0.0,
            "volume_center_shift": 0.0,
            "volume_spread_shift": 0.0,
            "volume_bin_shift": 0.0,
            "active_change": 1.0 if left_active != right_active else 0.0,
        }

    return {
        "pan_center_shift": abs(
            _summary_value(right.pan, "mean") - _summary_value(left.pan, "mean")
        )
        / 200.0,
        "pan_spread_shift": abs(
            _summary_value(right.pan, "std") - _summary_value(left.pan, "std")
        )
        / 100.0,
        "pan_bin_shift": _bin_l1_distance(left.pan_bins, right.pan_bins) / 2.0,
        "volume_center_shift": abs(
            _summary_value(right.volume, "mean")
            - _summary_value(left.volume, "mean")
        )
        / 100.0,
        "volume_spread_shift": abs(
            _summary_value(right.volume, "std")
            - _summary_value(left.volume, "std")
        )
        / 100.0,
        "volume_bin_shift": _bin_l1_distance(
            left.volume_bins,
            right.volume_bins,
        )
        / 2.0,
        "active_change": 0.0,
    }


def _cluster_layout_regime_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    clusters: list[list[dict[str, Any]]] = []
    for candidate in sorted(candidates, key=lambda item: item["tick"]):
        if (
            clusters
            and candidate["tick"] - clusters[-1][-1]["tick"]
            <= LAYOUT_REGIME_MIN_TICK_GAP
        ):
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])

    clustered: list[dict[str, Any]] = []
    for cluster in clusters:
        strongest = max(cluster, key=lambda item: (item["score"], -item["tick"]))
        merged = dict(strongest)
        merged["tick_start"] = min(item["tick"] for item in cluster)
        merged["tick_end"] = max(item["tick"] for item in cluster)
        merged["member_count"] = len(cluster)
        clustered.append(merged)

    return sorted(
        clustered,
        key=lambda item: (-item["score"], item["tick"]),
    )[:LAYOUT_REGIME_MAX_COUNT_PER_LAYER]


def _top_components(weighted_components: dict[str, float]) -> dict[str, float]:
    return {
        name: value
        for name, value in sorted(
            weighted_components.items(),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        if value > 0.0
    }


def _numeric_summary(values: Iterable[float]) -> dict[str, float | None]:
    numbers = tuple(values)
    if not numbers:
        return {
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "range": None,
        }

    mean_value = sum(numbers) / len(numbers)
    variance = sum((value - mean_value) ** 2 for value in numbers) / len(numbers)
    min_value = min(numbers)
    max_value = max(numbers)
    return {
        "mean": mean_value,
        "std": sqrt(variance),
        "min": min_value,
        "max": max_value,
        "range": max_value - min_value,
    }


def _pan_bins(values: Iterable[float]) -> dict[str, float]:
    return _ratio_bins(values, _pan_bin_name, PAN_BIN_NAMES)


def _volume_bins(values: Iterable[float]) -> dict[str, float]:
    return _ratio_bins(values, _volume_bin_name, VOLUME_BIN_NAMES)


def _ratio_bins(
    values: Iterable[float],
    classifier,
    names: tuple[str, ...],
) -> dict[str, float]:
    numbers = tuple(values)
    counts = {name: 0 for name in names}
    if not numbers:
        return {name: 0.0 for name in names}

    for value in numbers:
        counts[classifier(value)] += 1
    return {
        name: counts[name] / len(numbers)
        for name in names
    }


def _pan_bin_name(value: float) -> str:
    if value < 40:
        return "far_left"
    if value < 80:
        return "left"
    if value <= 120:
        return "center"
    if value <= 160:
        return "right"
    return "far_right"


def _volume_bin_name(value: float) -> str:
    if value < 20:
        return "very_low"
    if value < 45:
        return "low"
    if value < 70:
        return "mid"
    if value < 95:
        return "high"
    return "max"


def _summary_value(
    summary: dict[str, float | None] | None,
    field_name: str,
) -> float:
    if summary is None:
        return 0.0
    value = summary.get(field_name)
    return float(value) if value is not None else 0.0


def _bin_l1_distance(
    left: dict[str, float] | None,
    right: dict[str, float] | None,
) -> float:
    keys = set(left or {}) | set(right or {})
    return sum(
        abs((right or {}).get(key, 0.0) - (left or {}).get(key, 0.0))
        for key in keys
    )


def _guess_pan_mode(windows: list[LayoutSpatialWindow]) -> str:
    active_windows = [window for window in windows if window.note_count > 0]
    if not windows:
        return "unknown"
    if not active_windows:
        return "inactive"

    mean_values = [_summary_value(window.pan, "mean") for window in active_windows]
    pan_range = max(mean_values) - min(mean_values)
    average_bins = _average_bins(
        [window.pan_bins for window in active_windows],
        PAN_BIN_NAMES,
    )
    dominant_bin, dominant_ratio = _dominant_bin(average_bins)
    max_window_range = max(
        _summary_value(window.pan, "range")
        for window in active_windows
    )
    if max_window_range >= 80 or dominant_ratio < 0.5:
        return "wide_or_split"
    if pan_range >= 40:
        return "drifting"
    if dominant_ratio >= 0.6:
        return f"{dominant_bin}_stable"
    return "unknown"


def _guess_volume_mode(windows: list[LayoutSpatialWindow]) -> str:
    active_windows = [window for window in windows if window.note_count > 0]
    if not windows:
        return "unknown"
    if not active_windows:
        return "inactive"

    average_bins = _average_bins(
        [window.volume_bins for window in active_windows],
        VOLUME_BIN_NAMES,
    )
    dominant_bin, dominant_ratio = _dominant_bin(average_bins)
    max_window_range = max(
        _summary_value(window.volume, "range")
        for window in active_windows
    )
    if max_window_range >= 35 or dominant_ratio < 0.5:
        return "wide_or_dynamic"
    if dominant_ratio >= 0.6:
        return f"{dominant_bin}_stable"
    return "unknown"


def _average_bins(
    bins: list[dict[str, float] | None],
    names: tuple[str, ...],
) -> dict[str, float]:
    active_bins = [item for item in bins if item is not None]
    if not active_bins:
        return {name: 0.0 for name in names}
    return {
        name: sum(item.get(name, 0.0) for item in active_bins) / len(active_bins)
        for name in names
    }


def _dominant_bin(bins: dict[str, float]) -> tuple[str, float]:
    return max(bins.items(), key=lambda item: (item[1], item[0]))


def _continuity_priority(pan_mode: str, volume_mode: str) -> str:
    if pan_mode == "inactive" or volume_mode == "inactive":
        return "low"
    if pan_mode.endswith("_stable") and volume_mode.endswith("_stable"):
        return "high"
    if pan_mode == "unknown" or volume_mode == "unknown":
        return "low"
    return "medium"
