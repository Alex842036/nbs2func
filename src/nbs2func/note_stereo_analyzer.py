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
WINDOW_TEXTURE_GUESSES = (
    "empty",
    "percussion_like",
    "single_line_like",
    "layered_or_chord_like",
    "repeated_pattern_like",
    "sustain_texture_like",
    "effect_or_transition_like",
    "mixed_like",
    "unknown",
)
SUSTAIN_PATTERN_GUESSES = (
    "none",
    "inline_alternating_tail_like",
    "inline_decay_tail_like",
    "inline_stable_tail_like",
    "split_tail_like",
    "split_sustain_like",
    "pan_region_tail_like",
    "mixed_tail_like",
    "unknown",
)
STANDARD_GROUPING_MODES = frozenset(
    {
        "midi_instrument",
        "instrument_mixed",
        "instrument_split",
        "sustain_split",
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
WINDOW_TEXTURE_MIXED_DOMINANT_LAYER_RATIO = 0.85
WINDOW_TEXTURE_MIXED_MIN_INSTRUMENTS = 2
WINDOW_TEXTURE_MIXED_MIN_ACTIVE_LAYERS = 2
BOUNDARY_COMPONENT_WEIGHTS = {
    "activity": 2.0,
    "texture": 1.5,
    "sustain": 1.2,
    "density": 1.0,
    "pitch": 0.6,
    "volume": 0.6,
    "pan": 0.6,
    "rhythm": 0.8,
}
BOUNDARY_CANDIDATE_MAX_COUNT = 50
BOUNDARY_CANDIDATE_MIN_SCORE = 0.5
BOUNDARY_CLUSTER_MAX_TICK_GAP = 64
BOUNDARY_CLUSTER_MAX_COUNT = 50
BOUNDARY_FINAL_MAX_COUNT = 25
BOUNDARY_FINAL_MIN_SCORE = 2.5
BOUNDARY_LOW_RELIABILITY_WEIGHT = 0.9
BOUNDARY_LOW_RELIABILITY_SOLO_MIN_SCORE = 5.0
BOUNDARY_LOW_RELIABILITY_MULTI_MIN_SCORE = 4.0
BOUNDARY_GROUP_WEIGHT_MIN = 0.25
BOUNDARY_GROUP_WEIGHT_MAX = 1.25
BOUNDARY_GROUP_LOW_NOTE_COUNT = 4
BOUNDARY_GROUP_HIGH_NOTE_COUNT = 32
BOUNDARY_GROUP_FRAGMENTED_RUN_RATIO = 0.9
BOUNDARY_GROUP_STRONGLY_FRAGMENTED_RUN_RATIO = 1.25
BOUNDARY_GROUP_EFFECT_RATIO = 0.35
BOUNDARY_GROUP_STRONG_EFFECT_RATIO = 0.65
BOUNDARY_GROUP_EMPTY_RATIO = 0.5
BOUNDARY_GROUP_STRUCTURE_MODES = frozenset(
    {
        "instrument_split",
        "sustain_split",
        "percussion",
    }
)
BOUNDARY_DENSITY_SCALE = 1.0
BOUNDARY_NOTES_PER_ACTIVE_TICK_SCALE = 4.0
BOUNDARY_PITCH_SCALE = 24.0
BOUNDARY_VOLUME_SCALE = 100.0
BOUNDARY_PAN_SCALE = 100.0
SSM_FULL_STAT_MAX_FRAMES = 2000
SSM_NOVELTY_PEAK_MAX_COUNT = 50
SSM_NOVELTY_MIN_SCORE = 0.25
SSM_NOVELTY_MIN_DISTANCE_TICKS = 64
GROUP_SSM_NOVELTY_MIN_SCORE = 0.08
GROUP_SSM_NOVELTY_PEAK_MAX_COUNT = 20
GROUP_SSM_NOVELTY_MIN_DISTANCE_TICKS = 64
GROUP_SSM_MIN_ACTIVE_FRAMES = 2
GROUP_NOVELTY_GLOBAL_MAX_COUNT = 50
STRUCTURE_BOUNDARY_MATCH_TOLERANCE_TICKS = 64
STRUCTURE_BOUNDARY_MATCHED_PEAK_MAX_COUNT = 8
STRUCTURE_NOVELTY_ONLY_MIN_WEIGHTED_SCORE = 0.9
STRUCTURE_NOVELTY_ONLY_MULTI_GROUP_MIN_COUNT = 2
STRUCTURE_BOUNDARY_SCORE_SCALE = 8.0
STRUCTURE_NOVELTY_SCORE_SCALE = 1.2
STRUCTURE_BOUNDARY_EVIDENCE_WEIGHT = 0.55
STRUCTURE_NOVELTY_EVIDENCE_WEIGHT = 0.35
STRUCTURE_MULTI_GROUP_BONUS = 0.10
STRUCTURE_SOURCE_AGREEMENT_BONUS = 0.10
STRUCTURE_LOW_RELIABILITY_ONLY_PENALTY = 0.20
STRUCTURE_BOUNDARY_MIN_CONFIDENCE = 0.25
STRUCTURE_BOUNDARY_MAX_COUNT = 30
SUSTAIN_PATTERN_TAIL_ACTIVITY_RATIO = 0.1
SUSTAIN_PATTERN_INLINE_GROUPING_MODES = frozenset(
    {
        "midi_instrument",
        "instrument_mixed",
    }
)
SUSTAIN_PATTERN_MIN_INLINE_NOTES = 4
SUSTAIN_PATTERN_STABLE_PITCH_STD_MAX = 1.5
SUSTAIN_PATTERN_STABLE_VOLUME_STD_MAX = 4.0
SUSTAIN_PATTERN_DECAY_SLOPE_MAX = -0.2
SUSTAIN_PATTERN_ALTERNATING_PAN_MIN_SIDE_CHANGES = 2
SUSTAIN_PATTERN_ALTERNATING_PAN_CENTER_DEADZONE = 10
SUSTAIN_PATTERN_REGULARITY_SCORE = 0.7

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


@dataclass(frozen=True)
class WindowFeatureVector:
    group_name: str
    tick_start: int
    tick_end: int
    values: dict[str, float]


@dataclass(frozen=True)
class TrackFrameFeatureVector:
    tick_start: int
    tick_end: int
    values: dict[str, float]


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
        "summary": _build_summary_report(layer_reports, group_reports),
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


def window_report_to_feature_vector(
    group_report: dict[str, Any],
    window_report: dict[str, Any],
) -> WindowFeatureVector:
    """Convert one window report into a numeric feature vector."""

    values = {
        "note_density": _safe_float(
            window_report["density"]["note_density"]
        ),
        "mean_notes_per_active_tick": _safe_float(
            window_report["density"]["mean_notes_per_active_tick"]
        ),
        "multi_note_tick_ratio": _safe_float(
            window_report["simultaneity"]["multi_note_tick_ratio"]
        ),
        "pitch_mean": _safe_float(window_report["pitch"]["mean"]),
        "pitch_std": _safe_float(window_report["pitch"]["std"]),
        "volume_mean": _safe_float(window_report["volume"]["mean"]),
        "volume_std": _safe_float(window_report["volume"]["std"]),
        "pan_mean": _safe_float(window_report["pan"]["mean"]),
        "pan_std": _safe_float(window_report["pan"]["std"]),
        "regularity_score": _safe_float(
            window_report["rhythm"]["regularity_score"]
        ),
        "group_active": 1.0 if window_report["note_count"] > 0 else 0.0,
    }
    values.update(
        _one_hot_values(
            "texture",
            WINDOW_TEXTURE_GUESSES,
            window_report["window_texture_guess"],
        )
    )
    values.update(
        _one_hot_values(
            "sustain",
            SUSTAIN_PATTERN_GUESSES,
            window_report["sustain_pattern_guess"],
        )
    )

    return WindowFeatureVector(
        group_name=group_report["name"],
        tick_start=window_report["tick_start"],
        tick_end=window_report["tick_end"],
        values=values,
    )


def compute_window_feature_vectors(
    group_reports: list[dict[str, Any]],
) -> list[WindowFeatureVector]:
    return [
        window_report_to_feature_vector(group_report, window_report)
        for group_report in group_reports
        for window_report in group_report["windows"]
    ]


def compute_track_frame_feature_vectors(
    group_reports: list[dict[str, Any]],
) -> list[TrackFrameFeatureVector]:
    """Aggregate all group windows at the same tick into track-level frames."""

    total_group_count = len(group_reports)
    if total_group_count == 0:
        return []

    group_weights = {
        group_report["name"]: _build_group_summary(group_report)["boundary_weight"]
        for group_report in group_reports
    }
    vectors_by_tick: dict[int, list[WindowFeatureVector]] = {}
    for vector in compute_window_feature_vectors(group_reports):
        vectors_by_tick.setdefault(vector.tick_start, []).append(vector)

    frame_vectors: list[TrackFrameFeatureVector] = []
    for tick_start in sorted(vectors_by_tick):
        vectors = vectors_by_tick[tick_start]
        tick_end = max(vector.tick_end for vector in vectors)
        active_group_count = sum(
            1
            for vector in vectors
            if vector.values["group_active"] > 0.0
        )
        values = {
            "active_group_ratio": active_group_count / total_group_count,
            "active_group_count": float(active_group_count),
            "mean_note_density": _track_weighted_mean(
                vectors,
                group_weights,
                "note_density",
            ),
            "mean_multi_note_tick_ratio": _track_weighted_mean(
                vectors,
                group_weights,
                "multi_note_tick_ratio",
            ),
            "mean_pitch_mean": _track_weighted_mean(
                vectors,
                group_weights,
                "pitch_mean",
            ),
            "mean_pitch_std": _track_weighted_mean(
                vectors,
                group_weights,
                "pitch_std",
            ),
            "mean_volume_mean": _track_weighted_mean(
                vectors,
                group_weights,
                "volume_mean",
            ),
            "mean_volume_std": _track_weighted_mean(
                vectors,
                group_weights,
                "volume_std",
            ),
            "mean_pan_mean": _track_weighted_mean(
                vectors,
                group_weights,
                "pan_mean",
            ),
            "mean_pan_std": _track_weighted_mean(
                vectors,
                group_weights,
                "pan_std",
            ),
            "mean_regularity_score": _track_weighted_mean(
                vectors,
                group_weights,
                "regularity_score",
            ),
        }
        values.update(
            _track_label_ratios(
                vectors,
                total_group_count,
                "texture",
                WINDOW_TEXTURE_GUESSES,
            )
        )
        values.update(
            _track_label_ratios(
                vectors,
                total_group_count,
                "sustain",
                SUSTAIN_PATTERN_GUESSES,
            )
        )
        values["_group_count"] = float(total_group_count)
        frame_vectors.append(
            TrackFrameFeatureVector(
                tick_start=tick_start,
                tick_end=tick_end,
                values=values,
            )
        )

    return frame_vectors


def compute_self_similarity_summary(
    frame_vectors: list[TrackFrameFeatureVector | WindowFeatureVector],
    scope: str = "global_track_frame",
) -> dict[str, Any]:
    frame_count = len(frame_vectors)
    summary = {
        "scope": scope,
        "frame_count": frame_count,
        "tick_start": min(
            (frame.tick_start for frame in frame_vectors),
            default=None,
        ),
        "tick_end": max(
            (frame.tick_end for frame in frame_vectors),
            default=None,
        ),
        "similarity_method": "cosine",
        "full_matrix_output": False,
        "diagonal_mean": 1.0 if frame_count == 0 else 0.0,
        "off_diagonal_mean": 0.0,
        "off_diagonal_max": 0.0,
        "off_diagonal_min": 0.0,
        "stats_truncated": frame_count > SSM_FULL_STAT_MAX_FRAMES,
    }
    if frame_count == 0:
        return summary

    normalized_frames = [
        _normalize_feature_values(frame.values)
        for frame in frame_vectors
    ]
    diagonal_scores = [
        _cosine_similarity(values, values)
        for values in normalized_frames
    ]
    summary["diagonal_mean"] = sum(diagonal_scores) / len(diagonal_scores)

    if summary["stats_truncated"]:
        return summary

    off_diagonal_scores: list[float] = []
    for left_index, left_values in enumerate(normalized_frames):
        for right_values in normalized_frames[left_index + 1:]:
            off_diagonal_scores.append(
                _cosine_similarity(left_values, right_values)
            )

    if off_diagonal_scores:
        summary["off_diagonal_mean"] = (
            sum(off_diagonal_scores) / len(off_diagonal_scores)
        )
        summary["off_diagonal_max"] = max(off_diagonal_scores)
        summary["off_diagonal_min"] = min(off_diagonal_scores)

    return summary


def compute_novelty_curve_from_frames(
    frame_vectors: list[TrackFrameFeatureVector],
) -> list[dict[str, Any]]:
    return _compute_adjacent_novelty_curve(
        frame_vectors,
        ignore_inactive_pairs=False,
    )


def compute_group_ssm_summaries(
    group_reports: list[dict[str, Any]],
    group_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    group_summary_by_name = {
        group_summary["name"]: group_summary
        for group_summary in group_summaries
    }
    group_ssm: list[dict[str, Any]] = []
    for group_report in group_reports:
        vectors = [
            window_report_to_feature_vector(group_report, window_report)
            for window_report in group_report["windows"]
        ]
        vectors = sorted(vectors, key=lambda vector: vector.tick_start)
        group_summary = group_summary_by_name[group_report["name"]]
        ssm_summary = compute_self_similarity_summary(vectors, scope="group")
        novelty_peaks = detect_group_novelty_peaks(
            _compute_adjacent_novelty_curve(
                vectors,
                ignore_inactive_pairs=True,
            )
        )
        group_ssm.append(
            {
                "name": group_report["name"],
                "grouping_mode": group_report["grouping_mode"],
                "boundary_weight": group_summary["boundary_weight"],
                **ssm_summary,
                "novelty_peaks": novelty_peaks,
            }
        )

    return group_ssm


def flatten_group_novelty_peaks(
    group_ssm_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for group_summary in group_ssm_summaries:
        for peak in group_summary["novelty_peaks"]:
            weighted_score = peak["score"] * group_summary["boundary_weight"]
            flattened.append(
                {
                    "tick": peak["tick"],
                    "score": peak["score"],
                    "weighted_score": weighted_score,
                    "group": group_summary["name"],
                    "boundary_weight": group_summary["boundary_weight"],
                    "left_tick_start": peak["left_tick_start"],
                    "right_tick_start": peak["right_tick_start"],
                }
            )

    return sorted(
        flattened,
        key=lambda peak: (-peak["weighted_score"], peak["tick"], peak["group"]),
    )[:GROUP_NOVELTY_GLOBAL_MAX_COUNT]


def detect_group_novelty_peaks(
    novelty_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _detect_novelty_peaks(
        novelty_curve,
        min_score=GROUP_SSM_NOVELTY_MIN_SCORE,
        max_count=GROUP_SSM_NOVELTY_PEAK_MAX_COUNT,
        min_distance_ticks=GROUP_SSM_NOVELTY_MIN_DISTANCE_TICKS,
    )


def _compute_adjacent_novelty_curve(
    frame_vectors: list[TrackFrameFeatureVector | WindowFeatureVector],
    *,
    ignore_inactive_pairs: bool,
) -> list[dict[str, Any]]:
    sorted_frames = sorted(frame_vectors, key=lambda frame: frame.tick_start)
    normalized_frames = [
        _normalize_feature_values(frame.values)
        for frame in sorted_frames
    ]
    novelty_curve: list[dict[str, Any]] = []
    for index in range(1, len(sorted_frames)):
        if (
            ignore_inactive_pairs
            and sorted_frames[index - 1].values.get("group_active", 1.0) == 0.0
            and sorted_frames[index].values.get("group_active", 1.0) == 0.0
        ):
            continue
        similarity = _cosine_similarity(
            normalized_frames[index - 1],
            normalized_frames[index],
        )
        novelty_curve.append(
            {
                "tick": sorted_frames[index].tick_start,
                "score": 1.0 - similarity,
                "left_tick_start": sorted_frames[index - 1].tick_start,
                "right_tick_start": sorted_frames[index].tick_start,
            }
        )

    return novelty_curve


def detect_novelty_peaks(
    novelty_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _detect_novelty_peaks(
        novelty_curve,
        min_score=SSM_NOVELTY_MIN_SCORE,
        max_count=SSM_NOVELTY_PEAK_MAX_COUNT,
        min_distance_ticks=SSM_NOVELTY_MIN_DISTANCE_TICKS,
    )


def _detect_novelty_peaks(
    novelty_curve: list[dict[str, Any]],
    *,
    min_score: float,
    max_count: int,
    min_distance_ticks: int,
) -> list[dict[str, Any]]:
    peaks: list[dict[str, Any]] = []
    for point in sorted(
        novelty_curve,
        key=lambda item: (-item["score"], item["tick"]),
    ):
        if point["score"] < min_score:
            continue
        if any(
            abs(point["tick"] - kept["tick"]) < min_distance_ticks
            for kept in peaks
        ):
            continue
        peaks.append(point)
        if len(peaks) >= max_count:
            break

    return sorted(peaks, key=lambda item: (-item["score"], item["tick"]))


def compute_adjacent_change_scores(
    vectors: list[WindowFeatureVector],
) -> list[dict[str, Any]]:
    change_scores: list[dict[str, Any]] = []
    vectors_by_group: dict[str, list[WindowFeatureVector]] = {}
    for vector in vectors:
        vectors_by_group.setdefault(vector.group_name, []).append(vector)

    for group_name, group_vectors in sorted(vectors_by_group.items()):
        sorted_vectors = sorted(
            group_vectors,
            key=lambda vector: vector.tick_start,
        )
        for left, right in zip(sorted_vectors, sorted_vectors[1:]):
            components = _adjacent_change_components(left, right)
            score = sum(
                components[name] * BOUNDARY_COMPONENT_WEIGHTS[name]
                for name in BOUNDARY_COMPONENT_WEIGHTS
            )
            change_scores.append(
                {
                    "group": group_name,
                    "tick": right.tick_start,
                    "left_tick_start": left.tick_start,
                    "right_tick_start": right.tick_start,
                    "score": score,
                    "components": components,
                }
            )

    return change_scores


def detect_boundary_candidates(
    change_scores: list[dict[str, Any]],
    group_summaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    group_weights = {
        summary["name"]: summary["boundary_weight"]
        for summary in group_summaries or ()
    }
    raw_candidates_by_tick: dict[int, list[dict[str, Any]]] = {}
    for change_score in change_scores:
        raw_score = change_score["score"]
        group_weight = group_weights.get(change_score["group"], 1.0)
        weighted_score = raw_score * group_weight
        if weighted_score < BOUNDARY_CANDIDATE_MIN_SCORE:
            continue
        raw_candidate = {
            **change_score,
            "raw_score": raw_score,
            "score": weighted_score,
            "group_weight": group_weight,
            "component_scores": _weighted_component_scores(
                change_score["components"],
            ),
            "weighted_component_scores": _weighted_component_scores(
                change_score["components"],
                group_weight=group_weight,
            ),
        }
        raw_candidates_by_tick.setdefault(
            change_score["tick"],
            [],
        ).append(raw_candidate)

    raw_candidates: list[dict[str, Any]] = []
    for tick, tick_scores in raw_candidates_by_tick.items():
        group_scores = {
            change_score["group"]: change_score["score"]
            for change_score in sorted(
                tick_scores,
                key=lambda score: score["group"],
            )
        }
        group_raw_scores = {
            change_score["group"]: change_score["raw_score"]
            for change_score in sorted(
                tick_scores,
                key=lambda score: score["group"],
            )
        }
        group_weights_for_tick = {
            change_score["group"]: change_score["group_weight"]
            for change_score in sorted(
                tick_scores,
                key=lambda score: score["group"],
            )
        }
        component_scores = _aggregate_component_scores(tick_scores)
        weighted_component_scores = _aggregate_component_scores(
            tick_scores,
            field_name="weighted_component_scores",
        )
        top_components = dict(
            sorted(
                weighted_component_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )[:2]
        )
        raw_candidates.append(
            {
                "tick": tick,
                "tick_start": tick,
                "tick_end": tick,
                "score": max(group_scores.values()),
                "groups": list(group_scores),
                "group_scores": group_scores,
                "group_raw_scores": group_raw_scores,
                "group_weights": group_weights_for_tick,
                "top_components": top_components,
                "component_scores": component_scores,
                "weighted_component_scores": weighted_component_scores,
                "member_count": 1,
            }
        )

    return _cluster_boundary_candidates(raw_candidates)


def build_structure_boundary_candidates(
    boundary_candidates: list[dict[str, Any]],
    group_novelty_peaks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched_peak_indexes: set[int] = set()
    structure_candidates: list[dict[str, Any]] = []

    for boundary_candidate in boundary_candidates:
        matched_peaks: list[dict[str, Any]] = []
        for index, peak in enumerate(group_novelty_peaks):
            if index in matched_peak_indexes:
                continue
            if _group_novelty_peak_matches_boundary(peak, boundary_candidate):
                matched_peaks.append(peak)
                matched_peak_indexes.add(index)
        structure_candidate = _build_structure_candidate_from_boundary(
            boundary_candidate,
            matched_peaks,
        )
        if structure_candidate["confidence"] >= STRUCTURE_BOUNDARY_MIN_CONFIDENCE:
            structure_candidates.append(structure_candidate)

    unmatched_peaks = [
        peak
        for index, peak in enumerate(group_novelty_peaks)
        if index not in matched_peak_indexes
    ]
    for peak_cluster in _cluster_group_novelty_peaks(unmatched_peaks):
        max_weighted_score = max(
            peak["weighted_score"]
            for peak in peak_cluster
        )
        group_count = len({peak["group"] for peak in peak_cluster})
        if (
            max_weighted_score < STRUCTURE_NOVELTY_ONLY_MIN_WEIGHTED_SCORE
            and group_count < STRUCTURE_NOVELTY_ONLY_MULTI_GROUP_MIN_COUNT
        ):
            continue
        structure_candidate = _build_structure_candidate_from_novelty_cluster(
            peak_cluster,
        )
        if structure_candidate["confidence"] >= STRUCTURE_BOUNDARY_MIN_CONFIDENCE:
            structure_candidates.append(structure_candidate)

    return sorted(
        structure_candidates,
        key=lambda candidate: (-candidate["confidence"], candidate["tick"]),
    )[:STRUCTURE_BOUNDARY_MAX_COUNT]


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


def _build_summary_report(
    layer_reports: list[dict[str, Any]],
    group_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    all_windows = [
        window
        for group_report in group_reports
        for window in group_report["windows"]
    ]

    group_summaries = [
        _build_group_summary(group_report)
        for group_report in group_reports
    ]
    window_vectors = compute_window_feature_vectors(group_reports)
    frame_vectors = compute_track_frame_feature_vectors(group_reports)
    group_ssm = compute_group_ssm_summaries(group_reports, group_summaries)
    boundary_candidates = detect_boundary_candidates(
        compute_adjacent_change_scores(window_vectors),
        group_summaries,
    )
    group_novelty_peaks = flatten_group_novelty_peaks(group_ssm)
    structure_boundary_candidates = build_structure_boundary_candidates(
        boundary_candidates,
        group_novelty_peaks,
    )

    return {
        "overview": {
            "layer_count": len(layer_reports),
            "group_count": len(group_reports),
            "total_notes": sum(
                layer_report["note_count"]
                for layer_report in layer_reports
            ),
            "total_windows": len(all_windows),
        },
        "window_texture_counts": _count_window_field(
            all_windows,
            "window_texture_guess",
        ),
        "sustain_pattern_counts": _count_window_field(
            all_windows,
            "sustain_pattern_guess",
        ),
        "groups": group_summaries,
        "boundary_candidates": boundary_candidates,
        "ssm": compute_self_similarity_summary(frame_vectors),
        "novelty_peaks": detect_novelty_peaks(
            compute_novelty_curve_from_frames(frame_vectors)
        ),
        "group_ssm": group_ssm,
        "group_novelty_peaks": group_novelty_peaks,
        "structure_boundary_candidates": structure_boundary_candidates,
        "structure_boundary_summary": _build_structure_boundary_summary(
            structure_boundary_candidates
        ),
    }


def _build_group_summary(group_report: dict[str, Any]) -> dict[str, Any]:
    windows = group_report["windows"]
    summary = {
        "name": group_report["name"],
        "grouping_mode": group_report["grouping_mode"],
        "layers": group_report["layers"],
        "note_count": group_report["note_count"],
        "window_count": len(windows),
        "active_tick_start": group_report["tick_start"],
        "active_tick_end": group_report["tick_end"],
        "window_texture_counts": _count_window_field(
            windows,
            "window_texture_guess",
        ),
        "sustain_pattern_counts": _count_window_field(
            windows,
            "sustain_pattern_guess",
        ),
        "texture_run_count": _count_runs(
            window["window_texture_guess"]
            for window in windows
        ),
        "sustain_run_count": _count_runs(
            window["sustain_pattern_guess"]
            for window in windows
        ),
        "missing_layers": group_report["missing_layers"],
    }
    summary["boundary_weight"] = _compute_group_boundary_weight(summary)
    return summary


def _compute_group_boundary_weight(group_summary: dict[str, Any]) -> float:
    note_count = group_summary["note_count"]
    window_count = group_summary["window_count"]
    active_window_count = _active_summary_window_count(group_summary)
    if active_window_count == 0:
        return BOUNDARY_GROUP_WEIGHT_MIN

    weight = 1.0
    if note_count < BOUNDARY_GROUP_LOW_NOTE_COUNT:
        weight -= 0.35
    elif note_count >= BOUNDARY_GROUP_HIGH_NOTE_COUNT:
        weight += 0.1

    texture_run_ratio = group_summary["texture_run_count"] / active_window_count
    sustain_run_ratio = group_summary["sustain_run_count"] / active_window_count
    if texture_run_ratio >= BOUNDARY_GROUP_STRONGLY_FRAGMENTED_RUN_RATIO:
        weight -= 0.35
    elif texture_run_ratio >= BOUNDARY_GROUP_FRAGMENTED_RUN_RATIO:
        weight -= 0.2
    if sustain_run_ratio >= BOUNDARY_GROUP_STRONGLY_FRAGMENTED_RUN_RATIO:
        weight -= 0.2
    elif sustain_run_ratio >= BOUNDARY_GROUP_FRAGMENTED_RUN_RATIO:
        weight -= 0.1

    noisy_window_count = (
        group_summary["window_texture_counts"].get(
            "effect_or_transition_like",
            0,
        )
        + group_summary["window_texture_counts"].get("mixed_like", 0)
    )
    noisy_ratio = noisy_window_count / active_window_count
    if noisy_ratio >= BOUNDARY_GROUP_STRONG_EFFECT_RATIO:
        weight -= 0.35
    elif noisy_ratio >= BOUNDARY_GROUP_EFFECT_RATIO:
        weight -= 0.25

    empty_ratio = (
        group_summary["window_texture_counts"].get("empty", 0)
        / window_count
        if window_count
        else 0.0
    )
    if empty_ratio >= BOUNDARY_GROUP_EMPTY_RATIO:
        weight -= 0.15

    if _is_fragmented_boundary_group(group_summary):
        weight -= 0.2

    if group_summary["grouping_mode"] in BOUNDARY_GROUP_STRUCTURE_MODES:
        if note_count >= BOUNDARY_GROUP_LOW_NOTE_COUNT and noisy_ratio < 0.5:
            weight += 0.1

    if group_summary["missing_layers"]:
        weight -= min(0.3, 0.1 * len(group_summary["missing_layers"]))

    if group_summary["grouping_mode"] == "percussion":
        weight = max(1.0, weight)

    return _clamp(
        weight,
        BOUNDARY_GROUP_WEIGHT_MIN,
        BOUNDARY_GROUP_WEIGHT_MAX,
    )


def _active_summary_window_count(group_summary: dict[str, Any]) -> int:
    return (
        sum(group_summary["window_texture_counts"].values())
        - group_summary["window_texture_counts"].get("empty", 0)
    )


def _is_fragmented_boundary_group(group_summary: dict[str, Any]) -> bool:
    active_window_count = _active_summary_window_count(group_summary)
    if active_window_count == 0:
        return False

    texture_fragment_ratio = (
        group_summary["texture_run_count"] / active_window_count
    )
    sustain_fragment_ratio = (
        group_summary["sustain_run_count"] / active_window_count
    )
    effect_ratio = (
        group_summary["window_texture_counts"].get(
            "effect_or_transition_like",
            0,
        )
        / active_window_count
    )
    mixed_ratio = (
        group_summary["window_texture_counts"].get("mixed_like", 0)
        / active_window_count
    )

    return (
        (
            active_window_count <= 3
            and texture_fragment_ratio >= BOUNDARY_GROUP_FRAGMENTED_RUN_RATIO
        )
        or effect_ratio >= BOUNDARY_GROUP_STRONG_EFFECT_RATIO
        or (
            mixed_ratio >= BOUNDARY_GROUP_STRONG_EFFECT_RATIO
            and group_summary["grouping_mode"] not in BOUNDARY_GROUP_STRUCTURE_MODES
        )
        or (
            sustain_fragment_ratio >= BOUNDARY_GROUP_STRONGLY_FRAGMENTED_RUN_RATIO
            and active_window_count <= 4
        )
    )


def _weighted_component_scores(
    components: dict[str, float],
    group_weight: float = 1.0,
) -> dict[str, float]:
    return {
        component: (
            components[component]
            * BOUNDARY_COMPONENT_WEIGHTS[component]
            * group_weight
        )
        for component in BOUNDARY_COMPONENT_WEIGHTS
    }


def _aggregate_component_scores(
    candidates: list[dict[str, Any]],
    field_name: str = "component_scores",
) -> dict[str, float]:
    return {
        component: max(
            candidate[field_name][component]
            for candidate in candidates
        )
        for component in BOUNDARY_COMPONENT_WEIGHTS
    }


def _cluster_boundary_candidates(
    raw_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for candidate in sorted(raw_candidates, key=lambda item: item["tick"]):
        if (
            clusters
            and candidate["tick"] - clusters[-1][-1]["tick"]
            <= BOUNDARY_CLUSTER_MAX_TICK_GAP
        ):
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])

    clustered_candidates = [
        _build_boundary_cluster(cluster)
        for cluster in clusters
    ]
    return sorted(
        [
            candidate
            for candidate in clustered_candidates
            if _is_structural_boundary_candidate(candidate)
        ],
        key=lambda candidate: (-candidate["score"], candidate["tick"]),
    )[: min(
        BOUNDARY_FINAL_MAX_COUNT,
        BOUNDARY_CANDIDATE_MAX_COUNT,
        BOUNDARY_CLUSTER_MAX_COUNT,
    )]


def _build_boundary_cluster(
    cluster: list[dict[str, Any]],
) -> dict[str, Any]:
    best_member = max(cluster, key=lambda item: (item["score"], -item["tick"]))
    group_scores: dict[str, float] = {}
    group_raw_scores: dict[str, float] = {}
    group_weights: dict[str, float] = {}
    for member in cluster:
        for group, score in member["group_scores"].items():
            group_scores[group] = max(group_scores.get(group, 0.0), score)
        for group, score in member["group_raw_scores"].items():
            group_raw_scores[group] = max(group_raw_scores.get(group, 0.0), score)
        for group, weight in member["group_weights"].items():
            group_weights[group] = weight

    component_scores = _aggregate_component_scores(cluster)
    weighted_component_scores = _aggregate_component_scores(
        cluster,
        field_name="weighted_component_scores",
    )
    top_components = dict(
        sorted(
            weighted_component_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )[:2]
    )

    return {
        "tick": best_member["tick"],
        "tick_start": min(member["tick_start"] for member in cluster),
        "tick_end": max(member["tick_end"] for member in cluster),
        "score": best_member["score"],
        "groups": sorted(group_scores),
        "group_scores": {
            group: group_scores[group]
            for group in sorted(group_scores)
        },
        "group_raw_scores": {
            group: group_raw_scores[group]
            for group in sorted(group_raw_scores)
        },
        "group_weights": {
            group: group_weights[group]
            for group in sorted(group_weights)
        },
        "top_components": top_components,
        "component_scores": component_scores,
        "weighted_component_scores": weighted_component_scores,
        "member_count": len(cluster),
    }


def _is_structural_boundary_candidate(candidate: dict[str, Any]) -> bool:
    score = candidate["score"]
    group_count = len(candidate["groups"])
    has_reliable_group = any(
        weight >= BOUNDARY_LOW_RELIABILITY_WEIGHT
        for weight in candidate["group_weights"].values()
    )

    if score >= BOUNDARY_LOW_RELIABILITY_SOLO_MIN_SCORE:
        return True
    if has_reliable_group and score >= BOUNDARY_FINAL_MIN_SCORE:
        return True
    if group_count > 1 and score >= BOUNDARY_LOW_RELIABILITY_MULTI_MIN_SCORE:
        return True
    return False


def _group_novelty_peak_matches_boundary(
    peak: dict[str, Any],
    boundary_candidate: dict[str, Any],
) -> bool:
    if boundary_candidate["tick_start"] <= peak["tick"] <= boundary_candidate["tick_end"]:
        return True
    return (
        abs(peak["tick"] - boundary_candidate["tick"])
        <= STRUCTURE_BOUNDARY_MATCH_TOLERANCE_TICKS
    )


def _build_structure_candidate_from_boundary(
    boundary_candidate: dict[str, Any],
    matched_peaks: list[dict[str, Any]],
) -> dict[str, Any]:
    boundary_groups = set(boundary_candidate["groups"])
    novelty_groups = {peak["group"] for peak in matched_peaks}
    groups = sorted(boundary_groups | novelty_groups)
    group_weights = dict(boundary_candidate.get("group_weights", {}))
    for peak in matched_peaks:
        group_weights[peak["group"]] = peak["boundary_weight"]

    boundary_score = boundary_candidate["score"]
    novelty_score = max(
        (peak["weighted_score"] for peak in matched_peaks),
        default=0.0,
    )
    support = {
        "boundary": True,
        "group_novelty": bool(matched_peaks),
        "multi_group": len(groups) >= 2,
    }

    return {
        "tick": boundary_candidate["tick"],
        "tick_start": boundary_candidate["tick_start"],
        "tick_end": boundary_candidate["tick_end"],
        "confidence": _structure_boundary_confidence(
            boundary_score=boundary_score,
            novelty_score=novelty_score,
            support=support,
            group_weights=group_weights,
        ),
        "sources": _structure_candidate_sources(support),
        "groups": groups,
        "boundary_score": boundary_score,
        "novelty_score": novelty_score,
        "matched_novelty_peak_count": len(matched_peaks),
        "matched_novelty_groups": sorted(novelty_groups),
        "top_groups": _structure_top_groups(boundary_candidate, matched_peaks),
        "support": support,
        "matched_novelty_peaks": _compact_matched_novelty_peaks(matched_peaks),
    }


def _build_structure_candidate_from_novelty_cluster(
    peak_cluster: list[dict[str, Any]],
) -> dict[str, Any]:
    best_peak = max(
        peak_cluster,
        key=lambda peak: (peak["weighted_score"], -peak["tick"], peak["group"]),
    )
    groups = sorted({peak["group"] for peak in peak_cluster})
    group_weights = {
        peak["group"]: peak["boundary_weight"]
        for peak in peak_cluster
    }
    novelty_score = max(peak["weighted_score"] for peak in peak_cluster)
    support = {
        "boundary": False,
        "group_novelty": True,
        "multi_group": len(groups) >= 2,
    }

    return {
        "tick": best_peak["tick"],
        "tick_start": min(peak["left_tick_start"] for peak in peak_cluster),
        "tick_end": max(peak["right_tick_start"] for peak in peak_cluster),
        "confidence": _structure_boundary_confidence(
            boundary_score=0.0,
            novelty_score=novelty_score,
            support=support,
            group_weights=group_weights,
        ),
        "sources": _structure_candidate_sources(support),
        "groups": groups,
        "boundary_score": 0.0,
        "novelty_score": novelty_score,
        "matched_novelty_peak_count": len(peak_cluster),
        "matched_novelty_groups": groups,
        "top_groups": _structure_top_groups(None, peak_cluster),
        "support": support,
        "matched_novelty_peaks": _compact_matched_novelty_peaks(peak_cluster),
    }


def _structure_boundary_confidence(
    *,
    boundary_score: float,
    novelty_score: float,
    support: dict[str, bool],
    group_weights: dict[str, float],
) -> float:
    boundary_strength = min(
        1.0,
        boundary_score / STRUCTURE_BOUNDARY_SCORE_SCALE,
    )
    novelty_strength = min(
        1.0,
        novelty_score / STRUCTURE_NOVELTY_SCORE_SCALE,
    )
    confidence = (
        boundary_strength * STRUCTURE_BOUNDARY_EVIDENCE_WEIGHT
        + novelty_strength * STRUCTURE_NOVELTY_EVIDENCE_WEIGHT
    )
    if support["multi_group"]:
        confidence += STRUCTURE_MULTI_GROUP_BONUS
    if support["boundary"] and support["group_novelty"]:
        confidence += STRUCTURE_SOURCE_AGREEMENT_BONUS
    if group_weights and all(
        weight < BOUNDARY_LOW_RELIABILITY_WEIGHT
        for weight in group_weights.values()
    ):
        confidence -= STRUCTURE_LOW_RELIABILITY_ONLY_PENALTY

    return _clamp(confidence, 0.0, 1.0)


def _structure_candidate_sources(support: dict[str, bool]) -> list[str]:
    sources: list[str] = []
    if support["boundary"]:
        sources.append("boundary_candidate")
    if support["group_novelty"]:
        sources.append("group_novelty_peak")
    return sources


def _structure_top_groups(
    boundary_candidate: dict[str, Any] | None,
    novelty_peaks: list[dict[str, Any]],
) -> dict[str, float]:
    group_scores: dict[str, float] = {}
    if boundary_candidate is not None:
        for group, score in boundary_candidate.get("group_scores", {}).items():
            group_scores[group] = max(group_scores.get(group, 0.0), score)
    for peak in novelty_peaks:
        group_scores[peak["group"]] = max(
            group_scores.get(peak["group"], 0.0),
            peak["weighted_score"],
        )

    return {
        group: score
        for group, score in sorted(
            group_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )[:STRUCTURE_BOUNDARY_MATCHED_PEAK_MAX_COUNT]
    }


def _compact_matched_novelty_peaks(
    matched_peaks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "group": peak["group"],
            "tick": peak["tick"],
            "weighted_score": peak["weighted_score"],
        }
        for peak in sorted(
            matched_peaks,
            key=lambda peak: (-peak["weighted_score"], peak["tick"], peak["group"]),
        )[:STRUCTURE_BOUNDARY_MATCHED_PEAK_MAX_COUNT]
    ]


def _cluster_group_novelty_peaks(
    peaks: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for peak in sorted(peaks, key=lambda item: item["tick"]):
        if (
            clusters
            and peak["tick"] - clusters[-1][-1]["tick"]
            <= STRUCTURE_BOUNDARY_MATCH_TOLERANCE_TICKS
        ):
            clusters[-1].append(peak)
        else:
            clusters.append([peak])
    return clusters


def _build_structure_boundary_summary(
    structure_candidates: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "candidate_count": len(structure_candidates),
        "from_boundary_candidate_count": sum(
            1
            for candidate in structure_candidates
            if candidate["support"]["boundary"]
        ),
        "from_group_novelty_count": sum(
            1
            for candidate in structure_candidates
            if candidate["support"]["group_novelty"]
        ),
        "source_agreement_count": sum(
            1
            for candidate in structure_candidates
            if candidate["support"]["boundary"]
            and candidate["support"]["group_novelty"]
        ),
        "match_tolerance_ticks": STRUCTURE_BOUNDARY_MATCH_TOLERANCE_TICKS,
    }


def _count_window_field(
    windows: list[dict[str, Any]],
    field_name: str,
) -> dict[str, int]:
    counts = Counter(window[field_name] for window in windows)
    return {
        name: counts[name]
        for name in sorted(counts)
    }


def _count_runs(values: Iterable[str]) -> int:
    run_count = 0
    previous_value = None
    for value in values:
        if value != previous_value:
            run_count += 1
            previous_value = value
    return run_count


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _track_weighted_mean(
    vectors: list[WindowFeatureVector],
    group_weights: dict[str, float],
    field_name: str,
) -> float:
    if not vectors:
        return 0.0

    total_weight = sum(
        group_weights.get(vector.group_name, 1.0)
        for vector in vectors
    )
    if total_weight <= 0.0:
        return 0.0

    return (
        sum(
            vector.values[field_name] * group_weights.get(vector.group_name, 1.0)
            for vector in vectors
        )
        / total_weight
    )


def _track_label_ratios(
    vectors: list[WindowFeatureVector],
    total_group_count: int,
    prefix: str,
    names: tuple[str, ...],
) -> dict[str, float]:
    if total_group_count <= 0:
        return {
            f"{prefix}_{name}_ratio": 0.0
            for name in names
        }

    return {
        f"{prefix}_{name}_ratio": (
            sum(
                1
                for vector in vectors
                if vector.values[f"{prefix}_{name}"] > 0.0
            )
            / total_group_count
        )
        for name in names
    }


def _normalize_feature_values(values: dict[str, float]) -> dict[str, float]:
    group_count = max(1.0, values.get("_group_count", 1.0))
    normalized: dict[str, float] = {}
    for key, value in values.items():
        if key == "_group_count":
            continue
        safe_value = _safe_float(value)
        if key == "active_group_count":
            normalized[key] = _clamp(safe_value / group_count, 0.0, 1.0)
        elif key in {"mean_pitch_mean", "pitch_mean"}:
            normalized[key] = _clamp(safe_value / 100.0, 0.0, 1.0)
        elif key in {"mean_pitch_std", "pitch_std"}:
            normalized[key] = _clamp(safe_value / BOUNDARY_PITCH_SCALE, 0.0, 1.0)
        elif key in {"mean_volume_mean", "volume_mean"}:
            normalized[key] = _clamp(safe_value / 100.0, 0.0, 1.0)
        elif key in {"mean_volume_std", "volume_std"}:
            normalized[key] = _clamp(safe_value / BOUNDARY_VOLUME_SCALE, 0.0, 1.0)
        elif key in {"mean_pan_mean", "pan_mean"}:
            normalized[key] = _clamp(safe_value / 200.0, 0.0, 1.0)
        elif key in {"mean_pan_std", "pan_std"}:
            normalized[key] = _clamp(safe_value / BOUNDARY_PAN_SCALE, 0.0, 1.0)
        elif key in {
            "active_group_ratio",
            "mean_note_density",
            "note_density",
            "group_active",
            "mean_notes_per_active_tick",
            "mean_multi_note_tick_ratio",
            "multi_note_tick_ratio",
            "mean_regularity_score",
            "regularity_score",
        } or key.endswith("_ratio"):
            normalized[key] = _clamp(safe_value, 0.0, 1.0)
        else:
            normalized[key] = _clamp(safe_value, 0.0, 1.0)

    return normalized


def _cosine_similarity(
    left_values: dict[str, float],
    right_values: dict[str, float],
) -> float:
    keys = set(left_values) | set(right_values)
    if not keys:
        return 0.0

    dot_product = sum(
        left_values.get(key, 0.0) * right_values.get(key, 0.0)
        for key in keys
    )
    left_magnitude = sqrt(
        sum(value * value for value in left_values.values())
    )
    right_magnitude = sqrt(
        sum(value * value for value in right_values.values())
    )
    if left_magnitude == 0.0 or right_magnitude == 0.0:
        return 0.0

    return _clamp(
        dot_product / (left_magnitude * right_magnitude),
        0.0,
        1.0,
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _one_hot_values(
    prefix: str,
    names: tuple[str, ...],
    active_name: str,
) -> dict[str, float]:
    return {
        f"{prefix}_{name}": 1.0 if name == active_name else 0.0
        for name in names
    }


def _adjacent_change_components(
    left: WindowFeatureVector,
    right: WindowFeatureVector,
) -> dict[str, float]:
    return {
        "activity": _absolute_difference(left, right, "group_active"),
        "texture": _one_hot_difference(
            left,
            right,
            "texture",
            WINDOW_TEXTURE_GUESSES,
        ),
        "sustain": _one_hot_difference(
            left,
            right,
            "sustain",
            SUSTAIN_PATTERN_GUESSES,
        ),
        "density": _average_scaled_difference(
            left,
            right,
            (
                ("note_density", BOUNDARY_DENSITY_SCALE),
                (
                    "mean_notes_per_active_tick",
                    BOUNDARY_NOTES_PER_ACTIVE_TICK_SCALE,
                ),
            ),
        ),
        "pitch": _average_scaled_difference(
            left,
            right,
            (
                ("pitch_mean", BOUNDARY_PITCH_SCALE),
                ("pitch_std", BOUNDARY_PITCH_SCALE),
            ),
        ),
        "volume": _average_scaled_difference(
            left,
            right,
            (
                ("volume_mean", BOUNDARY_VOLUME_SCALE),
                ("volume_std", BOUNDARY_VOLUME_SCALE),
            ),
        ),
        "pan": _average_scaled_difference(
            left,
            right,
            (
                ("pan_mean", BOUNDARY_PAN_SCALE),
                ("pan_std", BOUNDARY_PAN_SCALE),
            ),
        ),
        "rhythm": _absolute_difference(left, right, "regularity_score"),
    }


def _absolute_difference(
    left: WindowFeatureVector,
    right: WindowFeatureVector,
    field_name: str,
) -> float:
    return abs(right.values[field_name] - left.values[field_name])


def _one_hot_difference(
    left: WindowFeatureVector,
    right: WindowFeatureVector,
    prefix: str,
    names: tuple[str, ...],
) -> float:
    return sum(
        abs(
            right.values[f"{prefix}_{name}"]
            - left.values[f"{prefix}_{name}"]
        )
        for name in names
    ) / 2


def _average_scaled_difference(
    left: WindowFeatureVector,
    right: WindowFeatureVector,
    fields: tuple[tuple[str, float], ...],
) -> float:
    return sum(
        min(
            1.0,
            _absolute_difference(left, right, field_name) / scale,
        )
        for field_name, scale in fields
    ) / len(fields)


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
    volume = _numeric_summary(note.final_volume for note in notes)
    pan = _numeric_summary(note.final_panning for note in notes)
    pitch = _pitch_summary(notes)
    rhythm = _rhythm_summary(notes)
    layer_activity = _layer_activity(layers, notes)
    simultaneity = _simultaneity_summary(notes)
    sustain_pattern_guess = _guess_sustain_pattern(
        group_config,
        notes,
        volume=volume,
        pitch=pitch,
        rhythm=rhythm,
        layer_activity=layer_activity,
    )
    window_texture_guess = _guess_window_texture(
        group_config,
        notes,
        density=density,
        instrument_counts=instrument_counts,
        rhythm=rhythm,
        layer_activity=layer_activity,
        simultaneity=simultaneity,
        sustain_pattern_guess=sustain_pattern_guess,
    )

    return {
        "tick_start": tick_start,
        "tick_end": tick_end,
        "note_count": len(notes),
        "density": density,
        "instrument_counts": instrument_counts,
        "volume": volume,
        "pan": pan,
        "pitch": pitch,
        "rhythm": rhythm,
        "layer_activity": layer_activity,
        "simultaneity": simultaneity,
        "window_texture_guess": window_texture_guess,
        "sustain_pattern_guess": sustain_pattern_guess,
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
    rhythm: dict[str, float | int | None],
    layer_activity: list[dict[str, float | int]],
    simultaneity: dict[str, float | int],
    sustain_pattern_guess: str,
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
        layer_activity,
        note_count,
        sustain_pattern_guess,
    )
    mixed_like = _is_mixed_texture(
        group_config,
        instrument_counts,
        layer_activity,
        simultaneity,
    )
    single_line_like = _is_single_line_texture(density, simultaneity)

    if percussion_like:
        return "percussion_like"

    if (
        note_count < WINDOW_TEXTURE_MIN_EFFECT_NOTES
        or density["active_tick_count"] < WINDOW_TEXTURE_MIN_EFFECT_ACTIVE_TICKS
    ):
        return "effect_or_transition_like"

    if mixed_like:
        return "mixed_like"
    if layered_like:
        return "layered_or_chord_like"
    if sustain_like:
        return "sustain_texture_like"
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
    layer_activity: list[dict[str, float | int]],
    note_count: int,
    sustain_pattern_guess: str,
) -> bool:
    if note_count < WINDOW_TEXTURE_SUSTAIN_MIN_NOTE_COUNT:
        return False

    if sustain_pattern_guess not in {"none", "unknown"}:
        return True

    dense_enough = density["note_density"] >= WINDOW_TEXTURE_SUSTAIN_MIN_DENSITY
    tail_activity_ratio = _tail_activity_ratio(group_config, layer_activity)

    return (
        tail_activity_ratio >= WINDOW_TEXTURE_TAIL_ACTIVITY_RATIO
        and dense_enough
    )


def _is_mixed_texture(
    group_config: LayerGroupConfig,
    instrument_counts: dict[str, int],
    layer_activity: list[dict[str, float | int]],
    simultaneity: dict[str, float | int],
) -> bool:
    if group_config.grouping_mode in {"instrument_split", "sustain_split"}:
        return False

    active_layer_ratios = [
        activity["ratio"]
        for activity in layer_activity
        if activity["note_count"] > 0
    ]
    if len(instrument_counts) < WINDOW_TEXTURE_MIXED_MIN_INSTRUMENTS:
        return False
    if len(active_layer_ratios) < WINDOW_TEXTURE_MIXED_MIN_ACTIVE_LAYERS:
        return False

    has_dominant_layer = (
        max(active_layer_ratios) >= WINDOW_TEXTURE_MIXED_DOMINANT_LAYER_RATIO
    )
    return (
        simultaneity["multi_note_tick_ratio"]
        >= WINDOW_TEXTURE_LAYERED_MULTI_TICK_RATIO
        or not has_dominant_layer
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


def _active_layer_count(layer_activity: list[dict[str, float | int]]) -> int:
    return sum(
        1
        for activity in layer_activity
        if activity["note_count"] > 0
    )


def _guess_sustain_pattern(
    group_config: LayerGroupConfig,
    notes: list[NoteEvent],
    *,
    volume: dict[str, float | None],
    pitch: dict[str, float | int | None],
    rhythm: dict[str, float | int | None],
    layer_activity: list[dict[str, float | int]],
) -> str:
    if not notes:
        return "none"

    tail_activity_ratio = _tail_activity_ratio(group_config, layer_activity)
    has_tail_activity = tail_activity_ratio >= SUSTAIN_PATTERN_TAIL_ACTIVITY_RATIO

    if group_config.grouping_mode == "pan_region" and has_tail_activity:
        return "pan_region_tail_like"
    if group_config.grouping_mode == "sustain_split":
        if has_tail_activity or _active_layer_count(layer_activity) >= 2:
            return "split_sustain_like"
        return "none"
    if group_config.grouping_mode == "instrument_split" and has_tail_activity:
        return "split_tail_like"

    if group_config.grouping_mode not in SUSTAIN_PATTERN_INLINE_GROUPING_MODES:
        return "none"
    if len(notes) < SUSTAIN_PATTERN_MIN_INLINE_NOTES:
        return "unknown"

    pitch_is_stable = _is_stable_pitch(pitch)
    if not pitch_is_stable:
        return "none"

    alternating_tail = _has_alternating_pan_tail(notes, rhythm)
    decay_tail = _has_volume_decay_tail(notes)
    stable_tail = _has_stable_inline_tail(volume)

    if alternating_tail and decay_tail:
        return "mixed_tail_like"
    if alternating_tail:
        return "inline_alternating_tail_like"
    if decay_tail:
        return "inline_decay_tail_like"
    if stable_tail:
        return "inline_stable_tail_like"
    return "none"


def _is_stable_pitch(pitch: dict[str, float | int | None]) -> bool:
    pitch_std = pitch["std"]
    return (
        pitch_std is not None
        and pitch_std <= SUSTAIN_PATTERN_STABLE_PITCH_STD_MAX
    )


def _has_alternating_pan_tail(
    notes: list[NoteEvent],
    rhythm: dict[str, float | int | None],
) -> bool:
    regularity_score = rhythm["regularity_score"]
    if (
        regularity_score is None
        or regularity_score < SUSTAIN_PATTERN_REGULARITY_SCORE
    ):
        return False

    pan_sides = [
        _pan_side(note.final_panning)
        for note in sorted(notes, key=lambda note: (note.tick, note.layer, note.key))
    ]
    pan_sides = [
        side
        for side in pan_sides
        if side is not None
    ]
    if len(pan_sides) < SUSTAIN_PATTERN_MIN_INLINE_NOTES:
        return False

    side_changes = sum(
        1
        for previous, current in zip(pan_sides, pan_sides[1:])
        if previous != current
    )
    return side_changes >= SUSTAIN_PATTERN_ALTERNATING_PAN_MIN_SIDE_CHANGES


def _pan_side(final_panning: float) -> str | None:
    if final_panning <= 100 - SUSTAIN_PATTERN_ALTERNATING_PAN_CENTER_DEADZONE:
        return "left"
    if final_panning >= 100 + SUSTAIN_PATTERN_ALTERNATING_PAN_CENTER_DEADZONE:
        return "right"
    return None


def _has_volume_decay_tail(notes: list[NoteEvent]) -> bool:
    return _linear_slope(
        [(note.tick, note.final_volume) for note in notes]
    ) <= SUSTAIN_PATTERN_DECAY_SLOPE_MAX


def _has_stable_inline_tail(volume: dict[str, float | None]) -> bool:
    volume_std = volume["std"]
    return (
        volume_std is not None
        and volume_std <= SUSTAIN_PATTERN_STABLE_VOLUME_STD_MAX
    )


def _linear_slope(points: list[tuple[int, float]]) -> float:
    if len(points) < 2:
        return 0.0

    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator == 0:
        return 0.0

    numerator = sum(
        (point[0] - mean_x) * (point[1] - mean_y)
        for point in points
    )
    return numerator / denominator


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
