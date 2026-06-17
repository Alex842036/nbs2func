import sys
from pathlib import Path

import pytest

from nbs2func.layout_spatial_analyzer import (
    LayoutSpatialWindow,
    analysis_report_to_jsonable,
    analyze_layout_spatial,
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


def _segment_for_notes(notes: tuple[NoteEvent, ...]) -> dict:
    report = analyze_layout_spatial(
        _song(_track(1, notes)),
        window_size=128,
        hop_size=128,
    )
    return report["layers"][0]["layout_segments_preview"][0]


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
    report = analyze_layout_spatial(
        _song(_track(1, tuple(notes))),
        window_size=128,
        hop_size=128,
        detail="full",
    )
    return LayoutSpatialWindow(**report["layers"][0]["windows"][0])


def test_overview_counts_empty_and_non_empty_layers() -> None:
    report = analyze_layout_spatial(
        _song(
            _track(1, (_note(tick=0, layer=1),)),
            _track(2, ()),
        )
    )

    assert report["overview"]["layer_count"] == 2
    assert report["overview"]["non_empty_layer_count"] == 1
    assert report["overview"]["empty_layer_count"] == 1
    assert [layer["layer_id"] for layer in report["layers"]] == [1]


def test_summary_detail_excludes_windows_by_default() -> None:
    report = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))

    assert "windows" not in report["layers"][0]


def test_full_detail_includes_windows() -> None:
    report = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0),))),
        detail="full",
    )

    assert report["layers"][0]["windows"][0]["note_count"] == 1


def test_full_detail_empty_window_has_null_spatial_fields() -> None:
    report = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0), _note(tick=256)))),
        window_size=32,
        hop_size=64,
        detail="full",
    )

    empty_window = report["layers"][0]["windows"][1]
    assert empty_window["note_count"] == 0
    assert empty_window["pan"] is None
    assert empty_window["volume"] is None
    assert empty_window["pan_bins"] is None
    assert empty_window["volume_bins"] is None


def test_active_window_bins_sum_to_one_in_full_detail() -> None:
    report = analyze_layout_spatial(
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
        ),
        detail="full",
    )

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
    report = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0), _note(tick=256)))),
        window_size=32,
        hop_size=64,
        detail="full",
    )

    candidates = report["layers"][0]["layout_regime_candidates"]
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
    assert segment["volume_distribution_mode"] != "unknown"


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
    report = analyze_layout_spatial(
        _song(_track(1, tuple(notes))),
        window_size=32,
        hop_size=128,
    )

    candidates = report["layers"][0]["layout_regime_candidates"]
    assert [
        candidate
        for candidate in candidates
        if candidate["candidate_type"] == "spatial_change"
    ] == []


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


def test_pitch_only_changes_do_not_affect_candidate_generation() -> None:
    report = analyze_layout_spatial(
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

    assert report["layers"][0]["layout_regime_candidates"] == []


def test_instrument_only_changes_do_not_affect_candidate_generation() -> None:
    report = analyze_layout_spatial(
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

    assert report["layers"][0]["layout_regime_candidates"] == []


def test_note_count_density_changes_do_not_drive_candidate_generation() -> None:
    report = analyze_layout_spatial(
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

    assert report["layers"][0]["layout_regime_candidates"] == []


def test_output_schema_has_layout_spatial_analysis_type() -> None:
    report = analyze_layout_spatial(_song(_track(1, (_note(tick=0),))))

    assert analysis_report_to_jsonable(report)["analysis_type"] == "layout_spatial"


def test_old_analyzer_module_is_not_imported() -> None:
    analyzer_path = (
        Path(__file__).parents[1]
        / "src"
        / "nbs2func"
        / "note_stereo_analyzer.py"
    )

    assert not analyzer_path.exists()
    assert "nbs2func.note_stereo_analyzer" not in sys.modules
