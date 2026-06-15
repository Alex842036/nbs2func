import json
from pathlib import Path

import pytest

from nbs2func.models import NoteEvent
from nbs2func.note_stereo_analyzer import (
    LayerGroupConfig,
    analysis_report_to_jsonable,
    analyze_note_stereo,
    load_group_config,
)


def _note(
    *,
    tick: int,
    layer: int,
    instrument: int = 0,
    key: int = 45,
    final_volume: float = 100.0,
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


def test_load_group_config_reads_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "percussion",
                        "layers": [8, 9, 10],
                        "role": "percussion",
                    },
                    {
                        "name": "harp_sustain",
                        "layers": [1, 2, 3],
                        "role": "sustain_group",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    groups = load_group_config(config_path)

    assert groups == (
        LayerGroupConfig(
            name="percussion",
            layers=(8, 9, 10),
            role="percussion",
        ),
        LayerGroupConfig(
            name="harp_sustain",
            layers=(1, 2, 3),
            role="sustain_group",
        ),
    )


def test_load_group_config_raises_value_error_when_required_field_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps({"groups": [{"name": "missing_role", "layers": [1]}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing: role"):
        load_group_config(config_path)


def test_role_guess_identifies_percussion_mostly_percussion_and_unknown() -> None:
    report = analyze_note_stereo(
        [
            _note(tick=0, layer=0, instrument=2),
            _note(tick=4, layer=0, instrument=3),
            _note(tick=8, layer=1, instrument=4),
            _note(tick=12, layer=1, instrument=2),
            _note(tick=16, layer=1, instrument=3),
            _note(tick=20, layer=1, instrument=4),
            _note(tick=24, layer=1, instrument=2),
            _note(tick=28, layer=1, instrument=3),
            _note(tick=32, layer=1, instrument=4),
            _note(tick=36, layer=1, instrument=2),
            _note(tick=40, layer=1, instrument=3),
            _note(tick=44, layer=1, instrument=0),
            _note(tick=0, layer=2, instrument=0),
            _note(tick=8, layer=2, instrument=5),
        ]
    )

    layer_by_id = {
        layer_report["layer_id"]: layer_report
        for layer_report in report["layers"]
    }

    assert layer_by_id[0]["role_guess"] == "percussion"
    assert layer_by_id[1]["role_guess"] == "mostly_percussion"
    assert layer_by_id[2]["role_guess"] == "unknown"


def test_layer_report_contains_basic_statistics() -> None:
    report = analyze_note_stereo(
        [
            _note(
                tick=0,
                layer=3,
                instrument=0,
                key=45,
                final_volume=80.0,
                final_panning=90.0,
            ),
            _note(
                tick=4,
                layer=3,
                instrument=2,
                key=47,
                final_volume=100.0,
                final_panning=110.0,
            ),
            _note(
                tick=8,
                layer=3,
                instrument=2,
                key=47,
                final_volume=120.0,
                final_panning=130.0,
            ),
            _note(
                tick=8,
                layer=3,
                instrument=2,
                key=49,
                final_volume=100.0,
                final_panning=110.0,
            ),
        ]
    )

    layer_report = report["layers"][0]

    assert layer_report["layer_id"] == 3
    assert layer_report["note_count"] == 4
    assert layer_report["tick_start"] == 0
    assert layer_report["tick_end"] == 8
    assert layer_report["instrument_counts"] == {"basedrum": 3, "harp": 1}
    assert layer_report["volume"] == {
        "mean": 100.0,
        "std": pytest.approx(14.1421356237),
        "min": 80.0,
        "max": 120.0,
    }
    assert layer_report["pan"] == {
        "mean": 110.0,
        "std": pytest.approx(14.1421356237),
        "min": 90.0,
        "max": 130.0,
    }
    assert layer_report["pitch"] == {
        "mean": 47.0,
        "std": pytest.approx(1.41421356237),
        "min": 45,
        "max": 49,
        "dominant_pitch": 47,
    }
    assert layer_report["rhythm"] == {
        "avg_tick_gap": 4.0,
        "median_tick_gap": 4.0,
        "most_common_tick_gap": 4,
        "regularity_score": 1.0,
    }
    assert layer_report["density"] == {
        "note_density": pytest.approx(4 / 9),
        "active_tick_count": 3,
        "mean_notes_per_active_tick": pytest.approx(4 / 3),
    }


def test_group_report_contains_aggregate_statistics() -> None:
    report = analyze_note_stereo(
        [
            _note(tick=0, layer=1, instrument=2, key=40, final_volume=80),
            _note(tick=4, layer=1, instrument=3, key=42, final_volume=100),
            _note(tick=8, layer=2, instrument=4, key=44, final_volume=120),
            _note(tick=12, layer=9, instrument=0, key=60, final_volume=60),
        ],
        group_configs=[
            LayerGroupConfig(
                name="drums",
                layers=(1, 2),
                role="percussion",
            )
        ],
    )

    group_report = report["groups"][0]

    assert group_report["name"] == "drums"
    assert group_report["layers"] == [1, 2]
    assert group_report["role"] == "percussion"
    assert group_report["note_count"] == 3
    assert group_report["tick_start"] == 0
    assert group_report["tick_end"] == 8
    assert group_report["missing_layers"] == []
    assert group_report["instrument_counts"] == {
        "basedrum": 1,
        "hat": 1,
        "snare": 1,
    }
    assert group_report["role_guess"] == "percussion"
    assert group_report["pitch"]["dominant_pitch"] == 40
    assert group_report["density"]["active_tick_count"] == 3
    assert group_report["layer_activity"] == [
        {"layer_id": 1, "note_count": 2, "ratio": pytest.approx(2 / 3)},
        {"layer_id": 2, "note_count": 1, "ratio": pytest.approx(1 / 3)},
    ]


def test_group_report_lists_missing_layers() -> None:
    report = analyze_note_stereo(
        [_note(tick=0, layer=1)],
        group_configs=[
            LayerGroupConfig(
                name="partial",
                layers=(1, 2, 3),
                role="sustain_group",
            )
        ],
    )

    assert report["groups"][0]["missing_layers"] == [2, 3]


def test_empty_notes_report_has_no_layers_and_empty_group_statistics() -> None:
    report = analyze_note_stereo(
        [],
        group_configs=[
            LayerGroupConfig(
                name="empty",
                layers=(1, 2),
                role="percussion",
            )
        ],
    )

    assert report["layers"] == []
    assert report["groups"][0]["note_count"] == 0
    assert report["groups"][0]["tick_start"] is None
    assert report["groups"][0]["tick_end"] is None
    assert report["groups"][0]["missing_layers"] == [1, 2]
    assert report["groups"][0]["role_guess"] == "unknown"
    assert report["groups"][0]["volume"] == {
        "mean": None,
        "std": None,
        "min": None,
        "max": None,
    }
    assert report["groups"][0]["density"] == {
        "note_density": 0.0,
        "active_tick_count": 0,
        "mean_notes_per_active_tick": 0.0,
    }
    assert report["groups"][0]["layer_activity"] == [
        {"layer_id": 1, "note_count": 0, "ratio": 0.0},
        {"layer_id": 2, "note_count": 0, "ratio": 0.0},
    ]


def test_analyzer_does_not_modify_input_notes() -> None:
    notes = [
        _note(tick=0, layer=0, instrument=2),
        _note(tick=4, layer=0, instrument=3),
    ]
    before = tuple(notes)

    analyze_note_stereo(notes)

    assert tuple(notes) == before


def test_analysis_report_to_jsonable_converts_dataclasses_and_tuples() -> None:
    jsonable = analysis_report_to_jsonable(
        {
            "group": LayerGroupConfig(
                name="percussion",
                layers=(1, 2),
                role="percussion",
            )
        }
    )

    assert jsonable == {
        "group": {
            "name": "percussion",
            "layers": [1, 2],
            "role": "percussion",
        }
    }
