from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from math import sqrt
from typing import Any, Iterable, Mapping

from .models import NoteEvent, Song


PAN_BIN_NAMES = ("far_left", "left", "center", "right", "far_right")
VOLUME_BIN_NAMES = ("very_low", "low", "mid", "high", "max")
ANALYSIS_DETAIL_LEVELS = frozenset({"summary", "full"})

LAYOUT_REGIME_MIN_SCORE = 0.35
LAYOUT_REGIME_MIN_TICK_GAP = 64
LAYOUT_REGIME_MAX_COUNT_PER_LAYER = 20
LAYOUT_SEGMENT_MIN_LENGTH_TICKS = 256
LAYOUT_SEGMENT_MAX_COUNT_PER_LAYER = 30

DECAY_CONTOUR_MAX_STEP_GAP_TICKS = 4
DECAY_CONTOUR_MAX_ALLOWED_UPWARD_STEP = 5
DECAY_CONTOUR_MIN_TOTAL_DROP_RATIO = 0.35
DECAY_CONTOUR_MIN_TOTAL_DROP_ABS = 15
DECAY_CONTOUR_MIN_CHAIN_LENGTH = 2
DECAY_CONTOUR_NOTE_RATIO_MIN = 0.30


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
    pan_mode: str
    pan_contour_mode: str
    volume_mode: str
    volume_contour_mode: str
    volume_contour: dict[str, float | int]


@dataclass(frozen=True)
class LayoutSpatialSegmentHint:
    layer_id: int
    start_tick: int
    end_tick: int
    duration_ticks: int
    window_count: int
    pan_mode: str
    pan_contour_mode: str
    volume_mode: str
    volume_contour_mode: str
    volume_contour: Mapping[str, float | int]
    radius_layer_hint: Mapping[str, Any]
    lateral_substream_hint: Mapping[str, Any]
    layout_intent: Mapping[str, Any]
    continuity_priority: str


@dataclass(frozen=True)
class LayoutSpatialLayerHint:
    layer_id: int
    name: str
    note_count: int
    active_tick_start: int | None
    active_tick_end: int | None
    window_count: int
    pan_summary: Mapping[str, float | None]
    volume_summary: Mapping[str, float | None]
    layout_regime_candidates: tuple[Mapping[str, Any], ...]
    segments: tuple[LayoutSpatialSegmentHint, ...]
    windows: tuple[LayoutSpatialWindow, ...]


@dataclass(frozen=True)
class LayoutSpatialAnalysis:
    layer_count: int
    non_empty_layer_count: int
    empty_layer_count: int
    total_notes: int
    window_size: int
    hop_size: int
    layers: tuple[LayoutSpatialLayerHint, ...]


class LayoutSpatialHintIndex:
    def __init__(self, analysis: LayoutSpatialAnalysis) -> None:
        self._layers = {
            layer.layer_id: layer
            for layer in analysis.layers
        }

    def get_segment(
        self,
        layer_id: int,
        tick: int,
    ) -> LayoutSpatialSegmentHint | None:
        layer = self._layers.get(layer_id)
        if layer is None:
            return None

        for index, segment in enumerate(layer.segments):
            if segment.start_tick <= tick < segment.end_tick:
                return segment
            # Note events use inclusive active end ticks. The index uses
            # half-open ranges, but accepts the final segment end for the
            # layer's last active note.
            if (
                index == len(layer.segments) - 1
                and tick == segment.end_tick
                and tick == layer.active_tick_end
            ):
                return segment

        return None


def analyze_layout_spatial(
    song: Song,
    *,
    window_size: int = 128,
    hop_size: int = 32,
    detail: str = "summary",
) -> LayoutSpatialAnalysis:
    """Analyze layer-local pan/volume patterns without touching layout output."""

    if window_size <= 0:
        raise ValueError("analysis window size must be greater than 0")
    if hop_size <= 0:
        raise ValueError("analysis hop size must be greater than 0")
    if detail not in ANALYSIS_DETAIL_LEVELS:
        raise ValueError("analysis detail must be 'summary' or 'full'")

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

    layers = tuple(
        _build_layer_hint(
            layer_id,
            layer_names.get(layer_id, f"Layer {layer_id}"),
            notes_by_layer.get(layer_id, []),
            window_size=window_size,
            hop_size=hop_size,
        )
        for layer_id in sorted(known_layers)
    )
    non_empty_layer_count = sum(1 for layer in layers if layer.note_count > 0)
    return LayoutSpatialAnalysis(
        layer_count=len(layers),
        non_empty_layer_count=non_empty_layer_count,
        empty_layer_count=len(layers) - non_empty_layer_count,
        total_notes=sum(len(notes) for notes in notes_by_layer.values()),
        window_size=window_size,
        hop_size=hop_size,
        layers=layers,
    )


def build_layout_spatial_hint_index(
    analysis: LayoutSpatialAnalysis,
) -> LayoutSpatialHintIndex:
    return LayoutSpatialHintIndex(analysis)


def analysis_to_jsonable(
    analysis: LayoutSpatialAnalysis,
    *,
    detail: str = "summary",
) -> dict[str, Any]:
    if detail not in ANALYSIS_DETAIL_LEVELS:
        raise ValueError("analysis detail must be 'summary' or 'full'")

    layers = (
        analysis.layers
        if detail == "full"
        else tuple(layer for layer in analysis.layers if layer.note_count > 0)
    )
    return {
        "analysis_type": "layout_spatial",
        "overview": {
            "layer_count": analysis.layer_count,
            "non_empty_layer_count": analysis.non_empty_layer_count,
            "empty_layer_count": analysis.empty_layer_count,
            "total_notes": analysis.total_notes,
            "window_size": analysis.window_size,
            "hop_size": analysis.hop_size,
        },
        "layers": [
            _layer_hint_to_jsonable(layer, detail=detail)
            for layer in layers
        ],
    }


def analysis_report_to_jsonable(
    report: Any,
    *,
    detail: str = "summary",
) -> Any:
    """Convert analyzer output to JSON-serializable primitive containers."""

    if isinstance(report, LayoutSpatialAnalysis):
        return analysis_to_jsonable(report, detail=detail)
    if is_dataclass(report):
        return analysis_report_to_jsonable(asdict(report), detail=detail)
    if isinstance(report, dict):
        return {
            str(key): analysis_report_to_jsonable(value, detail=detail)
            for key, value in report.items()
        }
    if isinstance(report, (list, tuple)):
        return [
            analysis_report_to_jsonable(value, detail=detail)
            for value in report
        ]
    return report


def detect_layout_regime_candidates(
    windows: list[LayoutSpatialWindow],
) -> list[dict[str, Any]]:
    raw_candidates: list[dict[str, Any]] = []
    sorted_windows = sorted(windows, key=lambda window: window.tick_start)

    for left, right in zip(sorted_windows, sorted_windows[1:]):
        if left.note_count == 0 and right.note_count == 0:
            continue

        component_scores = _candidate_component_scores(left, right)
        changed_components = [
            name
            for name, score in component_scores.items()
            if score >= LAYOUT_REGIME_MIN_SCORE
        ]
        active_change = component_scores["active_change"] > 0.0
        spatial_change = any(
            name != "active_change"
            and score >= LAYOUT_REGIME_MIN_SCORE
            for name, score in component_scores.items()
        )
        score = sum(component_scores.values())
        if score < LAYOUT_REGIME_MIN_SCORE:
            continue

        raw_candidates.append(
            {
                "tick": right.tick_start,
                "score": score,
                "candidate_type": _candidate_type(
                    active_change=active_change,
                    spatial_change=spatial_change,
                ),
                "changed_components": changed_components,
                "component_scores": component_scores,
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
    notes: list[NoteEvent] | None = None,
    layer_id: int = 0,
) -> list[LayoutSpatialSegmentHint]:
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

    preview: list[LayoutSpatialSegmentHint] = []
    available_windows = windows or []
    available_notes = sorted(notes or (), key=lambda note: (note.tick, note.key))
    for start_tick, end_tick in zip(segment_bounds, segment_bounds[1:]):
        segment_windows = [
            window
            for window in available_windows
            if start_tick <= window.tick_start < end_tick
        ]
        segment_notes = [
            note
            for note in available_notes
            if start_tick <= note.tick <= end_tick
        ]
        preview.append(
            _build_segment_hint(
                layer_id,
                start_tick,
                end_tick,
                segment_windows,
                segment_notes,
            )
        )

    return preview[:LAYOUT_SEGMENT_MAX_COUNT_PER_LAYER]


def _layer_hint_to_jsonable(
    layer: LayoutSpatialLayerHint,
    *,
    detail: str,
) -> dict[str, Any]:
    jsonable = {
        "layer_id": layer.layer_id,
        "name": layer.name,
        "note_count": layer.note_count,
        "active_tick_start": layer.active_tick_start,
        "active_tick_end": layer.active_tick_end,
        "window_count": layer.window_count,
        "pan_summary": analysis_report_to_jsonable(layer.pan_summary),
        "volume_summary": analysis_report_to_jsonable(layer.volume_summary),
        "layout_regime_candidates": analysis_report_to_jsonable(
            layer.layout_regime_candidates
        ),
        "layout_segments_preview": analysis_report_to_jsonable(layer.segments),
    }
    if detail == "full":
        jsonable["windows"] = analysis_report_to_jsonable(layer.windows)
    return jsonable


def _build_layer_hint(
    layer_id: int,
    name: str,
    notes: list[NoteEvent],
    *,
    window_size: int,
    hop_size: int,
) -> LayoutSpatialLayerHint:
    sorted_notes = sorted(notes, key=lambda note: (note.tick, note.key))
    active_tick_start = min((note.tick for note in sorted_notes), default=None)
    active_tick_end = max((note.tick for note in sorted_notes), default=None)
    windows = tuple(
        _build_windows(
            sorted_notes,
            active_tick_start=active_tick_start,
            active_tick_end=active_tick_end,
            window_size=window_size,
            hop_size=hop_size,
        )
    )
    candidates = tuple(detect_layout_regime_candidates(list(windows)))
    segments = tuple(
        build_layout_segments_preview(
            active_tick_start,
            active_tick_end,
            list(candidates),
            list(windows),
            sorted_notes,
            layer_id=layer_id,
        )
    )
    return LayoutSpatialLayerHint(
        layer_id=layer_id,
        name=name,
        note_count=len(sorted_notes),
        active_tick_start=active_tick_start,
        active_tick_end=active_tick_end,
        window_count=len(windows),
        pan_summary=_numeric_summary(
            note.final_panning for note in sorted_notes
        ),
        volume_summary=_numeric_summary(
            note.final_volume for note in sorted_notes
        ),
        layout_regime_candidates=candidates,
        segments=segments,
        windows=windows,
    )


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
            pan_mode="inactive",
            pan_contour_mode="inactive",
            volume_mode="inactive",
            volume_contour_mode="inactive",
            volume_contour=_empty_volume_contour(),
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
        pan_mode=_classify_pan_distribution(notes),
        pan_contour_mode=_classify_pan_contour(notes),
        volume_mode=_classify_volume_mode(notes),
        volume_contour_mode=_classify_volume_contour(notes),
        volume_contour=_volume_contour_metrics(notes),
    )


def _build_segment_hint(
    layer_id: int,
    start_tick: int,
    end_tick: int,
    windows: list[LayoutSpatialWindow],
    notes: list[NoteEvent],
) -> LayoutSpatialSegmentHint:
    pan_mode = _classify_pan_distribution(notes, windows)
    pan_contour_mode = _classify_pan_contour(notes, windows)
    volume_mode = _classify_volume_mode(notes, windows)
    volume_contour_mode = _classify_volume_contour(notes, windows)
    volume_contour = _volume_contour_metrics(notes)
    radius_layer_hint = _radius_layer_hint(
        notes,
        volume_contour_mode,
        volume_contour,
    )
    lateral_substream_hint = _lateral_substream_hint(
        pan_mode,
        pan_contour_mode,
    )

    return LayoutSpatialSegmentHint(
        layer_id=layer_id,
        start_tick=start_tick,
        end_tick=end_tick,
        duration_ticks=end_tick - start_tick,
        window_count=len(windows),
        pan_mode=pan_mode,
        pan_contour_mode=pan_contour_mode,
        volume_mode=volume_mode,
        volume_contour_mode=volume_contour_mode,
        volume_contour=volume_contour,
        radius_layer_hint=radius_layer_hint,
        lateral_substream_hint=lateral_substream_hint,
        layout_intent=_layout_intent(
            pan_mode,
            pan_contour_mode,
            volume_mode,
            volume_contour_mode,
            radius_layer_hint,
            lateral_substream_hint,
        ),
        continuity_priority=_legacy_continuity_priority(pan_mode, volume_mode),
    )


def _candidate_component_scores(
    left: LayoutSpatialWindow,
    right: LayoutSpatialWindow,
) -> dict[str, float]:
    left_active = left.note_count > 0
    right_active = right.note_count > 0
    active_change = left_active != right_active
    if not left_active or not right_active:
        return {
            "active_change": 0.45 if active_change else 0.0,
            "pan_mode": 0.0,
            "pan_contour_mode": 0.0,
            "volume_mode": 0.0,
            "volume_contour_mode": 0.0,
        }

    pan_mode_score = _mode_change_score(left.pan_mode, right.pan_mode, 0.60)
    pan_contour_score = _mode_change_score(
        left.pan_contour_mode,
        right.pan_contour_mode,
        0.45,
    )
    volume_mode_score = _volume_mode_change_score(left, right)
    volume_contour_score = _volume_contour_change_score(left, right)
    return {
        "active_change": 0.0,
        "pan_mode": pan_mode_score,
        "pan_contour_mode": pan_contour_score,
        "volume_mode": volume_mode_score,
        "volume_contour_mode": volume_contour_score,
    }


def _volume_mode_change_score(
    left: LayoutSpatialWindow,
    right: LayoutSpatialWindow,
) -> float:
    if left.volume_mode == right.volume_mode:
        return 0.0
    if (
        left.volume_contour_mode == "stepped_decay_contour"
        and right.volume_contour_mode == "stepped_decay_contour"
        and left.pan_mode == right.pan_mode
    ):
        return 0.10
    if left.volume_mode.endswith("_stable") or right.volume_mode.endswith("_stable"):
        return 0.35
    return 0.25


def _volume_contour_change_score(
    left: LayoutSpatialWindow,
    right: LayoutSpatialWindow,
) -> float:
    if left.volume_contour_mode == right.volume_contour_mode:
        return 0.0
    transition = {left.volume_contour_mode, right.volume_contour_mode}
    if "insufficient_data" in transition:
        return 0.0
    if "irregular_dynamic" in transition:
        return 0.55
    if "stepped_decay_contour" in transition:
        return 0.45
    if "relative_radius_layers" in transition:
        return 0.40
    return 0.30


def _mode_change_score(left: str, right: str, score: float) -> float:
    if "insufficient_data" in {left, right}:
        return 0.0
    return score if left != right else 0.0


def _candidate_type(*, active_change: bool, spatial_change: bool) -> str:
    if active_change and spatial_change:
        return "mixed"
    if active_change:
        return "activity_change"
    return "spatial_change"


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
        merged["changed_components"] = sorted(
            {
                component
                for item in cluster
                for component in item["changed_components"]
            }
        )
        merged["candidate_type"] = _merged_candidate_type(cluster)
        clustered.append(merged)

    return sorted(
        clustered,
        key=lambda item: (
            item["candidate_type"] == "activity_change",
            -item["score"],
            item["tick"],
        ),
    )[:LAYOUT_REGIME_MAX_COUNT_PER_LAYER]


def _merged_candidate_type(cluster: list[dict[str, Any]]) -> str:
    types = {item["candidate_type"] for item in cluster}
    if types == {"activity_change"}:
        return "activity_change"
    if types == {"spatial_change"}:
        return "spatial_change"
    return "mixed"


def _classify_pan_distribution(
    notes: list[NoteEvent],
    windows: list[LayoutSpatialWindow] | None = None,
) -> str:
    if not notes and windows:
        return _dominant_window_label(windows, "pan_mode", "inactive")
    if not notes:
        return "inactive"

    bins = _pan_bins(note.final_panning for note in notes)
    left_ratio = bins["far_left"] + bins["left"]
    center_ratio = bins["center"]
    right_ratio = bins["right"] + bins["far_right"]
    dominant_bin, dominant_ratio = _dominant_bin(bins)
    pan_range = _range(note.final_panning for note in notes)

    if left_ratio >= 0.30 and right_ratio >= 0.30 and center_ratio <= 0.25:
        return "bimodal_left_right"
    if center_ratio >= 0.30 and max(left_ratio, right_ratio) >= 0.25:
        return "center_plus_side"
    if dominant_ratio >= 0.65 and pan_range <= 60:
        return f"{dominant_bin}_stable"
    if pan_range >= 80 or dominant_ratio < 0.55:
        return "wide_or_split"
    if dominant_ratio >= 0.50:
        return f"{dominant_bin}_stable"
    return "unknown"


def _classify_pan_contour(
    notes: list[NoteEvent],
    windows: list[LayoutSpatialWindow] | None = None,
) -> str:
    if not notes and windows:
        return _dominant_window_label(windows, "pan_contour_mode", "inactive")
    if not notes:
        return "inactive"
    if len(notes) < 2:
        return "insufficient_data"

    values = [note.final_panning for note in sorted(notes, key=lambda item: item.tick)]
    value_range = max(values) - min(values)
    if value_range <= 2:
        return "flat"
    if value_range <= 15:
        return "small_variation"
    if _is_alternating_pan(values):
        return "alternating"
    if _is_gradual_contour(values):
        return "gradual_drift"
    if _classify_pan_distribution(notes) in {
        "bimodal_left_right",
        "center_plus_side",
        "wide_or_split",
    }:
        return "split_static"
    return "irregular_dynamic"


def _classify_volume_mode(
    notes: list[NoteEvent],
    windows: list[LayoutSpatialWindow] | None = None,
) -> str:
    if not notes and windows:
        return _dominant_window_label(windows, "volume_mode", "inactive")
    if not notes:
        return "inactive"

    bins = _volume_bins(note.final_volume for note in notes)
    dominant_bin, dominant_ratio = _dominant_bin(bins)
    volume_range = _range(note.final_volume for note in notes)
    if dominant_ratio >= 0.65 and volume_range <= 30:
        return f"{dominant_bin}_stable"
    if volume_range <= 20:
        return "narrow_dynamic"
    if dominant_ratio >= 0.55 and volume_range <= 35:
        return f"{dominant_bin}_stable"
    return "wide_or_dynamic"


def _classify_volume_contour(
    notes: list[NoteEvent],
    windows: list[LayoutSpatialWindow] | None = None,
) -> str:
    if not notes and windows:
        return _dominant_window_label(windows, "volume_contour_mode", "inactive")
    if not notes:
        return "inactive"
    if len(notes) < 2:
        return "insufficient_data"

    values = [
        note.final_volume
        for note in sorted(notes, key=lambda item: (item.tick, item.key))
    ]
    value_range = max(values) - min(values)
    if value_range <= 2:
        return "flat"

    contour = _volume_contour_metrics(notes)
    if contour["decay_note_ratio"] >= DECAY_CONTOUR_NOTE_RATIO_MIN:
        return "stepped_decay_contour"
    if value_range <= 12:
        return "small_variation"
    if _has_relative_radius_layers(values):
        return "relative_radius_layers"
    if _is_gradual_contour(values):
        return "gradual_drift"
    return "irregular_dynamic"


def _volume_contour_metrics(notes: list[NoteEvent]) -> dict[str, float | int]:
    if len(notes) < 2:
        return _empty_volume_contour()

    sorted_notes = sorted(notes, key=lambda note: (note.tick, note.key))
    decay_chains: list[list[NoteEvent]] = []
    current_chain = [sorted_notes[0]]
    for previous, current in zip(sorted_notes, sorted_notes[1:]):
        tick_gap = current.tick - previous.tick
        close_in_time = 0 < tick_gap <= DECAY_CONTOUR_MAX_STEP_GAP_TICKS
        not_upward_break = (
            current.final_volume
            <= previous.final_volume + DECAY_CONTOUR_MAX_ALLOWED_UPWARD_STEP
        )
        if close_in_time and not_upward_break:
            current_chain.append(current)
        else:
            _append_decay_chain(decay_chains, current_chain)
            current_chain = [current]
    _append_decay_chain(decay_chains, current_chain)

    participating_note_ids = {
        id(note)
        for chain in decay_chains
        for note in chain
    }
    chain_lengths = [len(chain) for chain in decay_chains]
    drop_ratios = [_chain_drop_ratio(chain) for chain in decay_chains]
    return {
        "decay_chain_count": len(decay_chains),
        "decay_note_ratio": (
            len(participating_note_ids) / len(sorted_notes)
            if sorted_notes
            else 0.0
        ),
        "mean_decay_chain_length": (
            sum(chain_lengths) / len(chain_lengths)
            if chain_lengths
            else 0.0
        ),
        "mean_decay_drop_ratio": (
            sum(drop_ratios) / len(drop_ratios)
            if drop_ratios
            else 0.0
        ),
    }


def _append_decay_chain(
    decay_chains: list[list[NoteEvent]],
    chain: list[NoteEvent],
) -> None:
    if len(chain) < DECAY_CONTOUR_MIN_CHAIN_LENGTH:
        return

    first_volume = chain[0].final_volume
    min_volume = min(note.final_volume for note in chain)
    total_drop_abs = first_volume - min_volume
    total_drop_ratio = total_drop_abs / max(first_volume, 1.0)
    if (
        total_drop_abs >= DECAY_CONTOUR_MIN_TOTAL_DROP_ABS
        and total_drop_ratio >= DECAY_CONTOUR_MIN_TOTAL_DROP_RATIO
    ):
        decay_chains.append(chain)


def _chain_drop_ratio(chain: list[NoteEvent]) -> float:
    first_volume = chain[0].final_volume
    min_volume = min(note.final_volume for note in chain)
    return (first_volume - min_volume) / max(first_volume, 1.0)


def _empty_volume_contour() -> dict[str, float | int]:
    return {
        "decay_chain_count": 0,
        "decay_note_ratio": 0.0,
        "mean_decay_chain_length": 0.0,
        "mean_decay_drop_ratio": 0.0,
    }


def _radius_layer_hint(
    notes: list[NoteEvent],
    volume_contour_mode: str,
    volume_contour: dict[str, float | int],
) -> dict[str, Any]:
    if volume_contour_mode == "stepped_decay_contour":
        estimated_layer_count = max(
            2,
            min(4, round(float(volume_contour["mean_decay_chain_length"]))),
        )
        return {
            "type": "relative_decay_layers",
            "estimated_layer_count": estimated_layer_count,
            "confidence": _clamp(float(volume_contour["decay_note_ratio"]), 0.0, 1.0),
            "roles": _radius_roles(estimated_layer_count),
        }
    if volume_contour_mode == "relative_radius_layers":
        estimated_layer_count = _estimated_relative_volume_layer_count(notes)
        return {
            "type": "relative_radius_layers",
            "estimated_layer_count": estimated_layer_count,
            "confidence": 0.65,
            "roles": _radius_roles(estimated_layer_count),
        }
    return {
        "type": "none",
        "estimated_layer_count": 0,
        "confidence": 0.0,
        "roles": [],
    }


def _radius_roles(estimated_layer_count: int) -> list[dict[str, str]]:
    roles = [
        {
            "role": "attack_or_primary",
            "relative_volume": "high",
            "layout_use": "main_radius_layer",
        },
        {
            "role": "decay_step_1",
            "relative_volume": "mid",
            "layout_use": "inner_radius_layer",
        },
        {
            "role": "decay_step_2",
            "relative_volume": "low",
            "layout_use": "near_radius_layer",
        },
        {
            "role": "decay_step_3",
            "relative_volume": "very_low",
            "layout_use": "nearest_radius_layer",
        },
    ]
    return roles[:estimated_layer_count]


def _lateral_substream_hint(
    pan_mode: str,
    pan_contour_mode: str,
) -> dict[str, float | int | str]:
    if pan_contour_mode == "alternating":
        return {
            "type": "lateral_alternating",
            "estimated_lane_count": 2,
            "confidence": 0.76,
        }
    if pan_mode == "bimodal_left_right":
        return {
            "type": "lateral_split",
            "estimated_lane_count": 2,
            "confidence": 0.78,
        }
    if pan_mode == "center_plus_side":
        return {
            "type": "center_plus_side",
            "estimated_lane_count": 2,
            "confidence": 0.70,
        }
    return {
        "type": "none",
        "estimated_lane_count": 0,
        "confidence": 0.0,
    }


def _layout_intent(
    pan_mode: str,
    pan_contour_mode: str,
    volume_mode: str,
    volume_contour_mode: str,
    radius_layer_hint: dict[str, Any],
    lateral_substream_hint: dict[str, float | int | str],
) -> dict[str, bool | str]:
    inactive = pan_mode == "inactive" or volume_mode == "inactive"
    allow_lateral_split = lateral_substream_hint["type"] != "none"
    allow_radius_layering = radius_layer_hint["type"] != "none"

    lateral_continuity = "medium"
    radius_continuity = "medium"
    if inactive:
        lateral_continuity = "low"
        radius_continuity = "low"
    elif pan_mode.endswith("_stable") or pan_contour_mode == "gradual_drift":
        lateral_continuity = "high"
    elif pan_contour_mode in {"alternating", "split_static"}:
        lateral_continuity = "medium"
    elif pan_contour_mode == "irregular_dynamic":
        lateral_continuity = "low"

    if volume_mode.endswith("_stable"):
        radius_continuity = "high"
    if volume_contour_mode in {
        "stepped_decay_contour",
        "relative_radius_layers",
    }:
        radius_continuity = "high"
    elif volume_contour_mode == "irregular_dynamic":
        radius_continuity = "low"

    return {
        "preferred_lateral_continuity": lateral_continuity,
        "preferred_radius_continuity": radius_continuity,
        "allow_radius_layering": allow_radius_layering,
        "allow_lateral_split": allow_lateral_split,
        "allow_segment_reset": inactive,
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


def _dominant_bin(bins: dict[str, float]) -> tuple[str, float]:
    return max(bins.items(), key=lambda item: (item[1], item[0]))


def _dominant_window_label(
    windows: list[LayoutSpatialWindow],
    field_name: str,
    default: str,
) -> str:
    labels = [
        getattr(window, field_name)
        for window in windows
        if window.note_count > 0
    ]
    if not labels:
        return default
    return max(set(labels), key=lambda label: (labels.count(label), label))


def _range(values: Iterable[float]) -> float:
    numbers = tuple(values)
    if not numbers:
        return 0.0
    return max(numbers) - min(numbers)


def _is_alternating_pan(values: list[float]) -> bool:
    sides = [_pan_side(value) for value in values]
    sides = [side for side in sides if side != "center"]
    if len(sides) < 4:
        return False
    side_changes = sum(
        1
        for previous, current in zip(sides, sides[1:])
        if previous != current
    )
    return side_changes / (len(sides) - 1) >= 0.65


def _pan_side(value: float) -> str:
    if value < 80:
        return "left"
    if value > 120:
        return "right"
    return "center"


def _is_gradual_contour(values: list[float]) -> bool:
    if len(values) < 3:
        return False
    deltas = [
        current - previous
        for previous, current in zip(values, values[1:])
        if current != previous
    ]
    if not deltas:
        return False
    positive = sum(1 for delta in deltas if delta > 0)
    negative = sum(1 for delta in deltas if delta < 0)
    dominant_direction_ratio = max(positive, negative) / len(deltas)
    net_change = abs(values[-1] - values[0])
    value_range = max(values) - min(values)
    return dominant_direction_ratio >= 0.75 and net_change >= value_range * 0.60


def _has_relative_radius_layers(values: list[float]) -> bool:
    if len(values) < 4:
        return False
    value_range = max(values) - min(values)
    if value_range < 20:
        return False
    return _estimated_relative_volume_layer_count_from_values(values) >= 3


def _estimated_relative_volume_layer_count(notes: list[NoteEvent]) -> int:
    values = [note.final_volume for note in notes]
    return _estimated_relative_volume_layer_count_from_values(values)


def _estimated_relative_volume_layer_count_from_values(values: list[float]) -> int:
    if not values:
        return 0
    max_value = max(values)
    if max_value <= 0:
        return 0
    buckets = {
        min(4, int((value / max_value) * 4))
        for value in values
    }
    return max(1, len(buckets))


def _legacy_continuity_priority(
    pan_mode: str,
    volume_mode: str,
) -> str:
    if pan_mode == "inactive" or volume_mode == "inactive":
        return "low"
    if pan_mode.endswith("_stable") and volume_mode.endswith("_stable"):
        return "high"
    if pan_mode == "unknown" or volume_mode == "unknown":
        return "low"
    return "medium"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
