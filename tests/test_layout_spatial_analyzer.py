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
