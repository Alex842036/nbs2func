import sys
from pathlib import Path

import pytest

from nbs2func.layout_spatial_analyzer import (
    LayoutSpatialWindow,
    analysis_report_to_jsonable,
    analyze_layout_spatial,
    build_layout_segments_preview,
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
    )
    return LayoutSpatialWindow(**report["layers"][0]["windows"][0])


def test_analyzer_works_without_group_config() -> None:
    report = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0),))),
        window_size=64,
        hop_size=64,
    )

    assert report["analysis_type"] == "layout_spatial"
    assert "groups" not in report


def test_each_layer_is_analyzed_independently() -> None:
    report = analyze_layout_spatial(
        _song(
            _track(1, (_note(tick=0, layer=1, final_panning=40),), "Lead"),
            _track(2, (_note(tick=0, layer=2, final_panning=160),), "Echo"),
        ),
        window_size=64,
        hop_size=64,
    )

    layers = {layer["layer_id"]: layer for layer in report["layers"]}
    assert layers[1]["name"] == "Lead"
    assert layers[1]["pan_summary"]["mean"] == 40
    assert layers[2]["name"] == "Echo"
    assert layers[2]["pan_summary"]["mean"] == 160


def test_window_pan_volume_summary_is_computed_correctly() -> None:
    report = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0, final_panning=80, final_volume=50),
                    _note(tick=16, final_panning=120, final_volume=70),
                ),
            )
        ),
        window_size=64,
        hop_size=64,
    )

    window = report["layers"][0]["windows"][0]
    assert window["pan"] == {
        "mean": 100.0,
        "std": 20.0,
        "min": 80,
        "max": 120,
        "range": 40,
    }
    assert window["volume"] == {
        "mean": 60.0,
        "std": 10.0,
        "min": 50,
        "max": 70,
        "range": 20,
    }


def test_empty_windows_produce_null_spatial_fields() -> None:
    report = analyze_layout_spatial(
        _song(
            _track(
                1,
                (
                    _note(tick=0),
                    _note(tick=256),
                ),
            )
        ),
        window_size=32,
        hop_size=64,
    )

    empty_window = report["layers"][0]["windows"][1]
    assert empty_window["note_count"] == 0
    assert empty_window["active_tick_start"] is None
    assert empty_window["active_tick_end"] is None
    assert empty_window["pan"] is None
    assert empty_window["volume"] is None
    assert empty_window["pan_bins"] is None
    assert empty_window["volume_bins"] is None


def test_active_window_bins_sum_to_one() -> None:
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
        window_size=64,
        hop_size=64,
    )

    window = report["layers"][0]["windows"][0]
    assert sum(window["pan_bins"].values()) == pytest.approx(1.0)
    assert sum(window["volume_bins"].values()) == pytest.approx(1.0)


def test_layout_regime_candidate_detects_pan_center_shift() -> None:
    candidates = detect_layout_regime_candidates(
        [
            _window(0, pan_values=(40.0,)),
            _window(128, pan_values=(160.0,)),
        ]
    )

    assert candidates
    assert candidates[0]["components"]["pan_center_shift"] > 0


def test_layout_regime_candidate_detects_pan_distribution_shift() -> None:
    candidates = detect_layout_regime_candidates(
        [
            _window(0, pan_values=(100.0, 100.0)),
            _window(128, pan_values=(60.0, 140.0)),
        ]
    )

    assert candidates
    assert candidates[0]["components"]["pan_center_shift"] == 0
    assert candidates[0]["components"]["pan_bin_shift"] > 0


def test_layout_regime_candidate_detects_volume_radius_shift() -> None:
    candidates = detect_layout_regime_candidates(
        [
            _window(0, volume_values=(30.0,)),
            _window(128, volume_values=(90.0,)),
        ]
    )

    assert candidates
    assert candidates[0]["components"]["volume_center_shift"] > 0


def test_pitch_only_changes_do_not_create_layout_regime_candidates() -> None:
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


def test_instrument_only_changes_do_not_create_layout_regime_candidates() -> None:
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


def test_note_count_density_changes_do_not_create_layout_regime_candidates() -> None:
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


def test_layout_segment_preview_is_built_from_candidate_ticks() -> None:
    segments = build_layout_segments_preview(
        0,
        1024,
        [{"tick": 512, "score": 1.0}],
        [
            _window(0, pan_values=(60.0,), volume_values=(60.0,)),
            _window(512, pan_values=(140.0,), volume_values=(80.0,)),
        ],
    )

    assert [segment["start_tick"] for segment in segments] == [0, 512]
    assert [segment["end_tick"] for segment in segments] == [512, 1024]
    assert segments[0]["pan_mode"] == "left_stable"
    assert segments[0]["continuity_priority"] == "high"


def test_output_schema_has_layout_spatial_analysis_type() -> None:
    report = analyze_layout_spatial(
        _song(_track(1, (_note(tick=0),))),
    )

    assert analysis_report_to_jsonable(report)["analysis_type"] == "layout_spatial"


def test_old_analyzer_module_is_not_importable() -> None:
    analyzer_path = (
        Path(__file__).parents[1]
        / "src"
        / "nbs2func"
        / "note_stereo_analyzer.py"
    )

    assert not analyzer_path.exists()
    assert "nbs2func.note_stereo_analyzer" not in sys.modules
