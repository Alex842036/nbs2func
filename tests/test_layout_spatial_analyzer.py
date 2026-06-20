import sys
from pathlib import Path

import pytest

import nbs2func.layout_spatial_analyzer as analyzer
from nbs2func.layout_spatial_analyzer import (
    BOUNDARY_MIN_SCORE_IMPROVEMENT,
    MIN_INACTIVE_GAP_TICKS,
    MIN_NOTES_FOR_SMALL_WINDOW_REFINEMENT,
    MIN_REFINED_SEGMENT_LENGTH_TICKS,
    SMALL_HOP_SIZE_TICKS,
    SMALL_WINDOW_SIZE_TICKS,
    LayoutSpatialAnalysis,
    LayoutSpatialWindow,
    analysis_report_to_jsonable,
    analyze_layout_spatial,
    build_layout_spatial_hint_index,
    detect_layout_regime_candidates,
)
from nbs2func.models import NoteEvent, Song, Track


def _note(
    *,
    tick: int,
    layer: int = 1,
    instrument: int = 0,
    key: int = 45,
    final_volume: float = 60.0,
    final_panning: float = 100.0,
) -> NoteEvent:
    return NoteEvent(
        tick=tick,
        layer=layer,
        instrument=instrument,
        key=key,
        final_volume=final_volume,
        final_panning=final_panning,
    )


def _song(*tracks: Track) -> Song:
    return Song(
        name="Spatial",
        author="Tester",
        length=1024,
        tracks=tracks,
    )


def _track(layer: int, notes: tuple[NoteEvent, ...], name: str | None = None) -> Track:
    return Track(
        id=layer,
        name=name or f"Layer {layer}",
        source_layer=layer,
        notes=notes,
    )


def _json_report(analysis: LayoutSpatialAnalysis, detail: str = "summary") -> dict:
    return analysis_report_to_jsonable(analysis, detail=detail)


def _segment_for_notes(notes: tuple[NoteEvent, ...]) -> dict:
    analysis = analyze_layout_spatial(
        _song(_track(1, notes)),
        window_size=128,
        hop_size=128,
    )
    return _json_report(analysis)["layers"][0]["layout_segments_preview"][0]


def _window(
    tick_start: int,
    *,
    pan_values: tuple[float, ...] = (100.0,),
    volume_values: tuple[float, ...] = (60.0,),
) -> LayoutSpatialWindow:
    notes = [
        _note(
            tick=tick_start + index,
            final_panning=pan,
            final_volume=volume_values[index % len(volume_values)],
        )
        for index, pan in enumerate(pan_values)
    ]
    analysis = analyze_layout_spatial(
        _song(_track(1, tuple(notes))),
        window_size=128,
        hop_size=128,
    )
    return analysis.layers[0].windows[0]


def _hint(
    start_tick: int,
    end_tick: int,
    notes: tuple[NoteEvent, ...],
):
    return analyzer._build_segment_hint(1, start_tick, end_tick, [], list(notes))


def test_overview_counts_empty_and_non_empty_layers() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(1, (_note(tick=0, layer=1),)),
            _track(2, ()),
        )
    )
    report = _json_report(analysis)

    assert analysis.layer_count == 2
    assert report["overview"]["non_empty_layer_count"] == 1
    assert report["overview"]["empty_layer_count"] == 1
    assert [layer["layer_id"] for layer in report["layers"]] == [1]


def test_small_window_refinement_constants() -> None:
    assert SMALL_WINDOW_SIZE_TICKS == 32
    assert SMALL_HOP_SIZE_TICKS == 8
    assert MIN_NOTES_FOR_SMALL_WINDOW_REFINEMENT == 4
    assert MIN_REFINED_SEGMENT_LENGTH_TICKS == 64
    assert MIN_INACTIVE_GAP_TICKS == 48
    assert BOUNDARY_MIN_SCORE_IMPROVEMENT == 0.15


def test_summary_detail_excludes_windows_by_default() -> None:
    analysis = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))
    report = _json_report(analysis)

    assert "windows" not in report["layers"][0]


def test_full_detail_includes_windows() -> None:
    analysis = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))
    report = _json_report(analysis, detail="full")

    assert report["layers"][0]["windows"][0]["note_count"] == 1


def test_json_output_uses_canonical_volume_fields() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, final_volume=100),
                    _note(tick=4, final_volume=50),
                ),
            )
        )
    )
    report = _json_report(analysis, detail="full")
    segment = report["layers"][0]["layout_segments_preview"][0]
    window = report["layers"][0]["windows"][0]

    assert "volume_distribution_mode" not in str(report)
    assert segment["volume_mode"] == "wide_or_dynamic"
    assert segment["volume_contour_mode"] == "stepped_decay_contour"
    assert window["volume_mode"] == "wide_or_dynamic"
    assert window["volume_contour_mode"] == "stepped_decay_contour"


def test_full_detail_empty_window_has_null_spatial_fields() -> None:
    analysis = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0), _note(tick=256)))),
        window_size=32,
        hop_size=64,
    )
    report = _json_report(analysis, detail="full")

    empty_window = report["layers"][0]["windows"][1]
    assert empty_window["note_count"] == 0
    assert empty_window["pan"] is None
    assert empty_window["volume"] is None
    assert empty_window["pan_bins"] is None
    assert empty_window["volume_bins"] is None


def test_active_window_bins_sum_to_one_in_full_detail() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, final_panning=20, final_volume=10),
                    _note(tick=1, final_panning=60, final_volume=30),
                    _note(tick=2, final_panning=100, final_volume=60),
                    _note(tick=3, final_panning=140, final_volume=80),
                    _note(tick=4, final_panning=180, final_volume=100),
                ),
            )
        )
    )
    report = _json_report(analysis, detail="full")

    window = report["layers"][0]["windows"][0]
    assert sum(window["pan_bins"].values()) == pytest.approx(1.0)
    assert sum(window["volume_bins"].values()) == pytest.approx(1.0)


def test_candidate_type_is_emitted_for_pan_spatial_change() -> None:
    candidates = detect_layout_regime_candidates(
        [
            _window(0, pan_values=(40.0,)),
            _window(128, pan_values=(160.0,)),
        ]
    )

    assert candidates[0]["candidate_type"] == "spatial_change"
    assert "pan_mode" in candidates[0]["changed_components"]
    assert "component_scores" in candidates[0]


def test_active_inactive_transition_becomes_activity_change() -> None:
    analysis = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0), _note(tick=256)))),
        window_size=32,
        hop_size=64,
    )

    candidates = analysis.layers[0].layout_regime_candidates
    assert candidates
    assert candidates[0]["candidate_type"] == "activity_change"


def test_stable_pan_with_stepped_decay_volume_is_classified() -> None:
    segment = _segment_for_notes(
        (
            _note(tick=0, final_volume=100),
            _note(tick=4, final_volume=50),
        )
    )

    assert segment["pan_mode"] == "center_stable"
    assert segment["pan_contour_mode"] == "flat"
    assert segment["volume_contour_mode"] == "stepped_decay_contour"
    assert segment["volume_mode"] != "unknown"


@pytest.mark.parametrize(
    "volumes",
    [
        (100, 50),
        (100, 50, 25),
        (100, 60, 40, 20),
        (50, 25),
        (40, 30, 20),
    ],
)
def test_relative_volume_drops_detect_stepped_decay_contour(
    volumes: tuple[int, ...],
) -> None:
    segment = _segment_for_notes(
        tuple(
            _note(tick=index * 4, final_volume=volume)
            for index, volume in enumerate(volumes)
        )
    )

    assert segment["volume_contour_mode"] == "stepped_decay_contour"
    assert segment["volume_contour"]["decay_chain_count"] >= 1
    assert segment["volume_contour"]["decay_note_ratio"] >= 0.30


def test_midi_style_attack_decay_produces_radius_layer_hint() -> None:
    segment = _segment_for_notes(
        (
            _note(tick=0, final_volume=100),
            _note(tick=4, final_volume=50),
            _note(tick=8, final_volume=25),
            _note(tick=128, final_volume=100),
            _note(tick=132, final_volume=60),
            _note(tick=136, final_volume=40),
            _note(tick=140, final_volume=20),
        )
    )

    assert segment["radius_layer_hint"]["type"] in {
        "relative_decay_layers",
        "relative_radius_layers",
    }
    assert segment["layout_intent"]["allow_radius_layering"] is True


def test_repeated_stepped_decay_bin_fluctuation_does_not_over_split() -> None:
    notes = []
    for base_tick in (0, 128, 256, 384):
        notes.extend(
            [
                _note(tick=base_tick, final_volume=100),
                _note(tick=base_tick + 4, final_volume=50),
                _note(tick=base_tick + 8, final_volume=25),
            ]
        )
    analysis = analyze_layout_spatial(
        _song(_track(1, tuple(notes))),
        window_size=32,
        hop_size=128,
    )

    candidates = analysis.layers[0].layout_regime_candidates
    assert [
        candidate
        for candidate in candidates
        if candidate["candidate_type"] == "spatial_change"
    ] == []


def test_irregular_dynamic_segment_triggers_small_window_refinement() -> None:
    notes = [
        *[_note(tick=tick, final_volume=60) for tick in range(0, 96, 16)],
        _note(tick=96, final_volume=80),
        _note(tick=112, final_volume=60),
        _note(tick=128, final_volume=80),
        _note(tick=144, final_volume=60),
        _note(tick=160, final_volume=80),
        _note(tick=176, final_volume=60),
    ]

    analysis = analyze_layout_spatial(_song(_track(1, tuple(notes))))
    segments = analysis.layers[0].segments

    assert len(segments) == 2
    assert segments[0].volume_contour_mode == "flat"
    assert segments[1].volume_contour_mode == "irregular_dynamic"


def test_wide_or_dynamic_without_radius_hint_triggers_refinement() -> None:
    notes = [
        *[_note(tick=tick, final_volume=60) for tick in range(0, 96, 16)],
        *[_note(tick=tick, final_volume=20) for tick in range(96, 192, 16)],
    ]

    analysis = analyze_layout_spatial(_song(_track(1, tuple(notes))))
    segments = analysis.layers[0].segments

    assert len(segments) == 2
    assert [segment.volume_mode for segment in segments] == [
        "mid_stable",
        "low_stable",
    ]


def test_stepped_decay_radius_hint_protects_against_refinement() -> None:
    notes = []
    for base_tick in (0, 16, 32, 48):
        notes.extend(
            [
                _note(tick=base_tick, final_volume=100),
                _note(tick=base_tick + 4, final_volume=50),
                _note(tick=base_tick + 8, final_volume=25),
            ]
        )

    analysis = analyze_layout_spatial(_song(_track(1, tuple(notes))))
    segments = analysis.layers[0].segments

    assert len(segments) == 1
    assert segments[0].volume_contour_mode == "stepped_decay_contour"
    assert segments[0].radius_layer_hint["type"] == "relative_decay_layers"


def test_relative_radius_layers_hint_protects_against_refinement() -> None:
    notes = [
        _note(tick=0, final_volume=60),
        _note(tick=16, final_volume=60),
        _note(tick=32, final_volume=60),
        _note(tick=48, final_volume=60),
        _note(tick=64, final_volume=20),
        _note(tick=80, final_volume=95),
        _note(tick=96, final_volume=35),
        _note(tick=112, final_volume=85),
        _note(tick=128, final_volume=25),
        _note(tick=144, final_volume=90),
    ]

    analysis = analyze_layout_spatial(_song(_track(1, tuple(notes))))
    segments = analysis.layers[0].segments

    assert len(segments) == 1
    assert segments[0].volume_contour_mode == "relative_radius_layers"
    assert segments[0].radius_layer_hint["type"] == "relative_radius_layers"


def test_pan_wide_or_split_without_lateral_hint_triggers_refinement() -> None:
    notes = tuple(_note(tick=tick) for tick in range(0, 96, 16))
    segment = analyzer._build_segment_hint(1, 0, 96, [], list(notes))
    segment = analyzer.LayoutSpatialSegmentHint(
        **{
            **segment.__dict__,
            "pan_mode": "wide_or_split",
            "lateral_substream_hint": {
                "type": "none",
                "estimated_lane_count": 0,
                "confidence": 0.0,
            },
        }
    )

    assert analyzer._should_refine_segment(segment, list(notes)) is True


def test_segment_with_inactive_gap_splits_active_inactive_active() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0),
                    _note(tick=16),
                    _note(tick=96),
                    _note(tick=112),
                ),
            )
        )
    )

    segments = analysis.layers[0].segments
    assert [segment.pan_mode for segment in segments] == [
        "center_stable",
        "inactive",
        "center_stable",
    ]
    assert segments[1].layout_intent["allow_segment_reset"] is True


def test_stable_flat_segment_is_not_refined() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                tuple(_note(tick=tick) for tick in range(0, 192, 16)),
            )
        )
    )

    assert len(analysis.layers[0].segments) == 1
    assert analysis.layers[0].segments[0].volume_contour_mode == "flat"


def test_short_refined_subsegments_are_rejected() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, final_volume=60),
                    _note(tick=16, final_volume=60),
                    _note(tick=32, final_volume=60),
                    _note(tick=48, final_volume=60),
                    _note(tick=64, final_volume=80),
                    _note(tick=80, final_volume=80),
                ),
            )
        )
    )

    assert len(analysis.layers[0].segments) == 1


def test_bimodal_left_right_pan_produces_lateral_substream_hint() -> None:
    segment = _segment_for_notes(
        (
            _note(tick=0, final_panning=40),
            _note(tick=16, final_panning=160),
            _note(tick=32, final_panning=45),
            _note(tick=48, final_panning=155),
        )
    )

    assert segment["pan_mode"] == "bimodal_left_right"
    assert segment["lateral_substream_hint"]["type"] in {
        "lateral_split",
        "lateral_alternating",
    }
    assert segment["layout_intent"]["allow_lateral_split"] is True


def test_center_plus_side_pan_produces_hint() -> None:
    segment = _segment_for_notes(
        (
            _note(tick=0, final_panning=100),
            _note(tick=16, final_panning=105),
            _note(tick=32, final_panning=150),
            _note(tick=48, final_panning=155),
        )
    )

    assert segment["pan_mode"] == "center_plus_side"
    assert segment["lateral_substream_hint"]["type"] == "center_plus_side"


def test_layout_spatial_analysis_and_hint_index_are_structured() -> None:
    analysis = analyze_layout_spatial(
        _song(_track(7, (_note(tick=0, layer=7), _note(tick=256, layer=7))))
    )
    index = build_layout_spatial_hint_index(analysis)
    segment = index.get_segment(7, 0)

    assert isinstance(analysis, LayoutSpatialAnalysis)
    assert segment is analysis.layers[0].segments[0]
    assert _json_report(analysis)["layers"][0]["layer_id"] == segment.layer_id


def test_hint_index_returns_none_for_missing_layer_and_outside_tick() -> None:
    analysis = analyze_layout_spatial(
        _song(_track(7, (_note(tick=100, layer=7), _note(tick=300, layer=7))))
    )
    index = build_layout_spatial_hint_index(analysis)

    assert index.get_segment(99, 100) is None
    assert index.get_segment(7, 99) is None
    assert index.get_segment(7, 301) is None


def test_hint_index_boundary_matching_is_half_open_except_final_active_end() -> None:
    left_notes = tuple(
        _note(tick=tick, layer=7, final_panning=40)
        for tick in range(0, 256, 16)
    )
    right_notes = tuple(
        _note(tick=tick, layer=7, final_panning=160)
        for tick in range(256, 513, 16)
    )
    analysis = analyze_layout_spatial(
        _song(
            _track(
                7,
                left_notes + right_notes,
            )
        ),
        window_size=128,
        hop_size=128,
    )
    index = build_layout_spatial_hint_index(analysis)
    first, second = analysis.layers[0].segments

    assert index.get_segment(7, first.start_tick) is first
    assert index.get_segment(7, first.end_tick) is second
    assert index.get_segment(7, second.end_tick) is second


def test_adjacent_equivalent_active_segments_are_merged() -> None:
    first_notes = tuple(_note(tick=tick) for tick in range(0, 64, 16))
    second_notes = tuple(_note(tick=tick) for tick in range(64, 128, 16))
    notes = list(first_notes + second_notes)
    merged = analyzer._merge_adjacent_equivalent_segments(
        1,
        [
            _hint(0, 64, first_notes),
            _hint(64, 128, second_notes),
        ],
        notes,
    )

    assert len(merged) == 1
    assert merged[0].start_tick == 0
    assert merged[0].end_tick == 128
    assert merged[0].duration_ticks == 128
    assert merged[0].segment_note_count == 0
    assert merged[0].layout_hint_weight == 0.0

    finalized = analyzer._finalize_segment_hints(1, merged, notes)
    assert finalized[0].segment_note_count == 8
    assert finalized[0].layout_hint_weight == pytest.approx(0.85)
    assert finalized[0].hint_strength == "strong"


def test_adjacent_equivalent_inactive_segments_are_merged() -> None:
    merged = analyzer._merge_adjacent_equivalent_segments(
        1,
        [
            _hint(0, 48, ()),
            _hint(48, 96, ()),
        ],
        [],
    )

    assert len(merged) == 1
    assert merged[0].pan_mode == "inactive"
    assert merged[0].layout_hint_weight == 0.0

    finalized = analyzer._finalize_segment_hints(1, merged, [])
    assert finalized[0].layout_hint_weight > 0


def test_active_segment_is_not_merged_with_inactive_segment() -> None:
    segments = analyzer._merge_adjacent_equivalent_segments(
        1,
        [
            _hint(0, 64, tuple(_note(tick=tick) for tick in range(0, 64, 16))),
            _hint(64, 96, ()),
        ],
        [],
    )

    assert len(segments) == 2


def test_segments_with_different_pan_or_volume_mode_are_not_merged() -> None:
    pan_segments = analyzer._merge_adjacent_equivalent_segments(
        1,
        [
            _hint(
                0,
                64,
                tuple(_note(tick=tick, final_panning=40) for tick in range(0, 64, 16)),
            ),
            _hint(
                64,
                128,
                tuple(_note(tick=tick, final_panning=160) for tick in range(64, 128, 16)),
            ),
        ],
        [],
    )
    volume_segments = analyzer._merge_adjacent_equivalent_segments(
        1,
        [
            _hint(0, 64, tuple(_note(tick=tick, final_volume=60) for tick in range(0, 64, 16))),
            _hint(64, 128, tuple(_note(tick=tick, final_volume=20) for tick in range(64, 128, 16))),
        ],
        [],
    )

    assert len(pan_segments) == 2
    assert len(volume_segments) == 2


def test_segments_with_different_hint_types_are_not_merged() -> None:
    notes = tuple(_note(tick=tick) for tick in range(0, 64, 16))
    base = _hint(0, 64, notes)
    radius_variant = analyzer.LayoutSpatialSegmentHint(
        **{
            **base.__dict__,
            "start_tick": 64,
            "end_tick": 128,
            "duration_ticks": 64,
            "radius_layer_hint": {
                "type": "relative_radius_layers",
                "estimated_layer_count": 2,
                "confidence": 0.8,
                "roles": [],
            },
        }
    )
    lateral_variant = analyzer.LayoutSpatialSegmentHint(
        **{
            **base.__dict__,
            "start_tick": 64,
            "end_tick": 128,
            "lateral_substream_hint": {
                "type": "lateral_split",
                "estimated_lane_count": 2,
                "confidence": 0.8,
            },
        }
    )

    assert len(analyzer._merge_adjacent_equivalent_segments(1, [base, radius_variant], [])) == 2
    assert len(analyzer._merge_adjacent_equivalent_segments(1, [base, lateral_variant], [])) == 2


def test_segment_equivalence_ignores_derived_hint_fields() -> None:
    notes = tuple(_note(tick=tick) for tick in range(0, 128, 16))
    first = _hint(0, 64, notes[:4])
    second = analyzer.LayoutSpatialSegmentHint(
        **{
            **_hint(64, 128, notes[4:]).__dict__,
            "window_count": 99,
            "segment_note_count": 123,
            "layout_hint_weight": 0.12,
            "hint_strength": "weak",
        }
    )

    assert analyzer._segments_are_layout_equivalent(first, second)


def test_final_output_includes_layout_hint_weight_and_strength() -> None:
    analysis = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))
    report = _json_report(analysis)
    segment = report["layers"][0]["layout_segments_preview"][0]

    assert 0.0 <= segment["layout_hint_weight"] <= 1.0
    assert segment["hint_strength"] in {"weak", "medium", "strong"}
    assert segment["segment_note_count"] == 1


def test_short_active_segment_gets_lower_weight_than_long_stable_segment() -> None:
    short = _hint(0, 16, (_note(tick=0),))
    long = _hint(
        0,
        256,
        tuple(_note(tick=tick) for tick in range(0, 256, 32)),
    )

    assert short.layout_hint_weight < long.layout_hint_weight
    assert short.hint_strength == "weak"


def test_active_duration_factor_reaches_cap_at_128_ticks() -> None:
    weight = analyzer._layout_hint_weight(
        duration_ticks=128,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="flat",
        radius_layer_hint={"type": "none"},
        lateral_substream_hint={"type": "none"},
    )

    assert weight == pytest.approx(0.85)
    assert analyzer._hint_strength(weight) == "strong"


def test_no_special_hint_uses_085_default_factor() -> None:
    weight = analyzer._layout_hint_weight(
        duration_ticks=192,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="flat",
        radius_layer_hint={"type": "none", "confidence": 1.0},
        lateral_substream_hint={"type": "none", "confidence": 1.0},
    )

    assert weight == pytest.approx(0.85)


def test_explicit_special_hint_confidence_blends_to_one() -> None:
    medium_hint_weight = analyzer._layout_hint_weight(
        duration_ticks=128,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="flat",
        radius_layer_hint={"type": "relative_radius_layers", "confidence": 0.65},
        lateral_substream_hint={"type": "none"},
    )
    max_hint_weight = analyzer._layout_hint_weight(
        duration_ticks=128,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="flat",
        radius_layer_hint={"type": "relative_radius_layers", "confidence": 2.0},
        lateral_substream_hint={"type": "none"},
    )

    assert medium_hint_weight == pytest.approx(0.9475)
    assert max_hint_weight == pytest.approx(1.0)


def test_mode_quality_affects_layout_hint_weight() -> None:
    flat_weight = analyzer._layout_hint_weight(
        duration_ticks=256,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="flat",
        radius_layer_hint={"type": "none"},
        lateral_substream_hint={"type": "none"},
    )
    irregular_weight = analyzer._layout_hint_weight(
        duration_ticks=256,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="irregular_dynamic",
        radius_layer_hint={"type": "none"},
        lateral_substream_hint={"type": "none"},
    )
    insufficient = analyzer._layout_hint_weight(
        duration_ticks=256,
        segment_note_count=8,
        pan_mode="center_stable",
        volume_contour_mode="insufficient_data",
        radius_layer_hint={"type": "none"},
        lateral_substream_hint={"type": "none"},
    )

    assert irregular_weight < flat_weight
    assert insufficient < 0.35


def test_radius_layer_segments_keep_medium_or_high_weight_when_supported() -> None:
    stepped = _hint(
        0,
        256,
        tuple(
            _note(tick=tick, final_volume=volume)
            for tick, volume in (
                (0, 100),
                (4, 50),
                (8, 25),
                (64, 100),
                (68, 50),
                (72, 25),
                (128, 100),
                (132, 50),
            )
        ),
    )

    assert stepped.volume_contour_mode == "stepped_decay_contour"
    assert stepped.layout_hint_weight >= 0.35


def test_inactive_segment_weight_is_nonzero_and_duration_sensitive() -> None:
    short = _hint(0, 32, ())
    long = _hint(0, 256, ())

    assert short.layout_hint_weight > 0
    assert short.layout_hint_weight < long.layout_hint_weight


def test_hint_strength_thresholds_match_weight() -> None:
    assert analyzer._hint_strength(0.10) == "weak"
    assert analyzer._hint_strength(0.35) == "medium"
    assert analyzer._hint_strength(0.70) == "strong"


def test_hint_index_returns_segment_weight() -> None:
    analysis = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))
    index = build_layout_spatial_hint_index(analysis)
    segment = index.get_segment(1, 0)

    assert segment is not None
    assert 0.0 <= segment.layout_hint_weight <= 1.0


def test_spatial_change_candidate_boundary_is_available_for_snapping() -> None:
    notes = (
        tuple(_note(tick=tick, final_volume=60) for tick in range(0, 96, 16))
        + tuple(_note(tick=tick, final_volume=20) for tick in range(96, 192, 16))
    )

    analysis = analyze_layout_spatial(_song(_track(1, notes)))

    assert analysis.layers[0].layout_regime_candidates
    assert analysis.layers[0].layout_regime_candidates[0]["candidate_type"] in {
        "spatial_change",
        "mixed",
    }
    assert analysis.layers[0].segments[1].start_tick in {88, 96}


def test_activity_change_candidate_can_snap_to_note_gap_boundary() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0),
                    _note(tick=16),
                    _note(tick=96),
                    _note(tick=112),
                ),
            )
        ),
        window_size=32,
        hop_size=32,
    )

    assert any(
        candidate["candidate_type"] == "activity_change"
        for candidate in analysis.layers[0].layout_regime_candidates
    )
    assert [(segment.start_tick, segment.end_tick) for segment in analysis.layers[0].segments] == [
        (0, 17),
        (17, 96),
        (96, 112),
    ]


def test_pitch_only_changes_do_not_affect_candidate_generation() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, key=30),
                    _note(tick=128, key=70),
                ),
            )
        ),
        window_size=64,
        hop_size=128,
    )

    assert analysis.layers[0].layout_regime_candidates == ()


def test_instrument_only_changes_do_not_affect_candidate_generation() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, instrument=0),
                    _note(tick=128, instrument=9),
                ),
            )
        ),
        window_size=64,
        hop_size=128,
    )

    assert analysis.layers[0].layout_regime_candidates == ()


def test_note_count_density_changes_do_not_drive_candidate_generation() -> None:
    analysis = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0),
                    _note(tick=4),
                    _note(tick=8),
                    _note(tick=128),
                ),
            )
        ),
        window_size=64,
        hop_size=128,
    )

    assert analysis.layers[0].layout_regime_candidates == ()


def test_output_schema_has_layout_spatial_analysis_type() -> None:
    analysis = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))

    assert _json_report(analysis)["analysis_type"] == "layout_spatial"


def test_old_analyzer_module_is_not_imported() -> None:
    analyzer_path = (
        Path(__file__).parents[1]
        / "src"
        / "nbs2func"
        / "note_stereo_analyzer.py"
    )

    assert not analyzer_path.exists()
    assert "nbs2func.note_stereo_analyzer" not in sys.modules
