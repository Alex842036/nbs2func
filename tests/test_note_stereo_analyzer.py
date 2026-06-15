import json
from pathlib import Path

import pytest

from nbs2func.models import NoteEvent
from nbs2func.note_stereo_analyzer import (
    LayerGroupConfig,
    analysis_report_to_jsonable,
    analyze_note_stereo,
    compute_group_windows,
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


def test_load_group_config_reads_valid_new_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "midi_flute",
                        "layers": [1],
                        "grouping_mode": "midi_instrument",
                    },
                    {
                        "name": "manual_strings",
                        "layers": [2, 3, 4],
                        "grouping_mode": "instrument_split",
                        "layer_parts": {
                            "2": "head",
                            "3": "left_tail",
                            "4": "right_tail",
                        },
                    },
                    {
                        "name": "left_accompaniment",
                        "layers": [7, 8, 9, 10],
                        "grouping_mode": "pan_region",
                        "pan_region": "left",
                        "layer_parts": {
                            "7": "main",
                            "8": "main",
                            "9": "outer_tail",
                            "10": "inner_tail",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    groups = load_group_config(config_path)

    assert groups == (
        LayerGroupConfig(
            name="midi_flute",
            layers=(1,),
            grouping_mode="midi_instrument",
        ),
        LayerGroupConfig(
            name="manual_strings",
            layers=(2, 3, 4),
            grouping_mode="instrument_split",
            layer_parts={
                2: "head",
                3: "left_tail",
                4: "right_tail",
            },
        ),
        LayerGroupConfig(
            name="left_accompaniment",
            layers=(7, 8, 9, 10),
            grouping_mode="pan_region",
            pan_region="left",
            layer_parts={
                7: "main",
                8: "main",
                9: "outer_tail",
                10: "inner_tail",
            },
        ),
    )


def test_load_group_config_defaults_grouping_mode_to_manual_mixed(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps({"groups": [{"name": "default_mode", "layers": [1]}]}),
        encoding="utf-8",
    )

    groups = load_group_config(config_path)

    assert groups == (
        LayerGroupConfig(
            name="default_mode",
            layers=(1,),
            grouping_mode="manual_mixed",
        ),
    )


def test_load_group_config_rejects_invalid_grouping_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "bad",
                        "layers": [1],
                        "grouping_mode": "melodyish",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown grouping_mode"):
        load_group_config(config_path)


def test_load_group_config_defaults_pan_region_to_unknown(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "centerless",
                        "layers": [1],
                        "grouping_mode": "midi_instrument",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    groups = load_group_config(config_path)

    assert groups[0].pan_region == "unknown"


def test_load_group_config_rejects_invalid_pan_region(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "bad_pan",
                        "layers": [1],
                        "grouping_mode": "pan_region",
                        "pan_region": "slightly_leftish",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown pan_region"):
        load_group_config(config_path)


def test_load_group_config_converts_layer_parts_keys_to_int(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "parts",
                        "layers": [1, 2],
                        "grouping_mode": "instrument_split",
                        "layer_parts": {
                            "1": "head",
                            "2": "support",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    groups = load_group_config(config_path)

    assert groups[0].layer_parts == {
        1: "head",
        2: "support",
    }


def test_load_group_config_rejects_invalid_layer_part(tmp_path: Path) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "bad_part",
                        "layers": [1],
                        "layer_parts": {"1": "shadow"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown layer part"):
        load_group_config(config_path)


def test_load_group_config_rejects_layer_part_outside_group_layers(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "bad_layer",
                        "layers": [1],
                        "layer_parts": {"2": "support"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside group"):
        load_group_config(config_path)


def test_load_group_config_rejects_empty_name_and_layers(tmp_path: Path) -> None:
    name_path = tmp_path / "empty_name.json"
    name_path.write_text(
        json.dumps({"groups": [{"name": "", "layers": [1]}]}),
        encoding="utf-8",
    )
    layers_path = tmp_path / "empty_layers.json"
    layers_path.write_text(
        json.dumps({"groups": [{"name": "empty_layers", "layers": []}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="name"):
        load_group_config(name_path)
    with pytest.raises(ValueError, match="layers"):
        load_group_config(layers_path)


def test_load_group_config_rejects_old_schema_fields(tmp_path: Path) -> None:
    role_path = tmp_path / "old_role.json"
    role_path.write_text(
        json.dumps({"groups": [{"name": "old", "layers": [1], "role": "lead"}]}),
        encoding="utf-8",
    )
    layer_roles_path = tmp_path / "old_layer_roles.json"
    layer_roles_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "old",
                        "layers": [1],
                        "layer_roles": {"1": "head"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="role"):
        load_group_config(role_path)
    with pytest.raises(ValueError, match="layer_roles"):
        load_group_config(layer_roles_path)


def test_load_group_config_raises_value_error_when_required_field_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "groups.json"
    config_path.write_text(
        json.dumps({"groups": [{"name": "missing_layers"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing: layers"):
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
                grouping_mode="percussion",
            )
        ],
    )

    group_report = report["groups"][0]

    assert group_report["name"] == "drums"
    assert group_report["layers"] == [1, 2]
    assert group_report["grouping_mode"] == "percussion"
    assert group_report["pan_region"] == "unknown"
    assert group_report["layer_parts"] == {}
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


def test_group_report_outputs_grouping_mode_pan_region_and_layer_parts() -> None:
    report = analyze_note_stereo(
        [_note(tick=0, layer=7, instrument=0)],
        group_configs=[
            LayerGroupConfig(
                name="left_accompaniment",
                layers=(7, 8),
                grouping_mode="pan_region",
                pan_region="left",
                layer_parts={
                    7: "main",
                    8: "outer_tail",
                },
            )
        ],
    )

    group_report = report["groups"][0]

    assert group_report["grouping_mode"] == "pan_region"
    assert group_report["pan_region"] == "left"
    assert group_report["layer_parts"] == {
        7: "main",
        8: "outer_tail",
    }


def test_group_report_lists_missing_layers() -> None:
    report = analyze_note_stereo(
        [_note(tick=0, layer=1)],
        group_configs=[
            LayerGroupConfig(
                name="partial",
                layers=(1, 2, 3),
                grouping_mode="instrument_split",
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
                grouping_mode="percussion",
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
    assert report["groups"][0]["windows"] == []


def test_compute_group_windows_uses_expected_tick_ranges() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1),
            _note(tick=32, layer=1),
            _note(tick=160, layer=1),
            _note(tick=999, layer=9),
        ],
        LayerGroupConfig(name="group", layers=(1,)),
        window_size=64,
        hop_size=32,
    )

    assert [
        (window["tick_start"], window["tick_end"])
        for window in windows
    ] == [
        (0, 64),
        (32, 96),
        (64, 128),
        (96, 160),
        (128, 192),
        (160, 224),
    ]


def test_compute_group_windows_reports_window_features() -> None:
    windows = compute_group_windows(
        [
            _note(
                tick=0,
                layer=1,
                instrument=2,
                key=40,
                final_volume=80,
                final_panning=90,
            ),
            _note(
                tick=0,
                layer=2,
                instrument=3,
                key=42,
                final_volume=100,
                final_panning=110,
            ),
            _note(
                tick=64,
                layer=2,
                instrument=0,
                key=42,
                final_volume=120,
                final_panning=130,
            ),
            _note(tick=128, layer=1, instrument=4, key=44),
        ],
        LayerGroupConfig(name="features", layers=(1, 2)),
        window_size=128,
        hop_size=128,
    )

    first_window = windows[0]

    assert first_window["tick_start"] == 0
    assert first_window["tick_end"] == 128
    assert first_window["note_count"] == 3
    assert first_window["density"] == {
        "note_density": pytest.approx(3 / 128),
        "active_tick_count": 2,
        "mean_notes_per_active_tick": pytest.approx(1.5),
    }
    assert first_window["instrument_counts"] == {
        "basedrum": 1,
        "harp": 1,
        "snare": 1,
    }
    assert first_window["volume"] == {
        "mean": 100.0,
        "std": pytest.approx(16.3299316185),
        "min": 80,
        "max": 120,
    }
    assert first_window["pan"] == {
        "mean": 110.0,
        "std": pytest.approx(16.3299316185),
        "min": 90,
        "max": 130,
    }
    assert first_window["pitch"] == {
        "mean": pytest.approx(41.3333333333),
        "std": pytest.approx(0.94280904158),
        "min": 40,
        "max": 42,
        "dominant_pitch": 42,
    }
    assert first_window["rhythm"] == {
        "avg_tick_gap": 64.0,
        "median_tick_gap": 64,
        "most_common_tick_gap": 64,
        "regularity_score": 1.0,
    }
    assert first_window["layer_activity"] == [
        {"layer_id": 1, "note_count": 1, "ratio": pytest.approx(1 / 3)},
        {"layer_id": 2, "note_count": 2, "ratio": pytest.approx(2 / 3)},
    ]
    assert first_window["simultaneity"] == {
        "max_notes_per_tick": 2,
        "multi_note_tick_ratio": pytest.approx(0.5),
    }


def test_compute_group_windows_handles_empty_windows_stably() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1),
            _note(tick=256, layer=1),
        ],
        LayerGroupConfig(name="sparse", layers=(1, 2)),
        window_size=128,
        hop_size=128,
    )

    empty_window = windows[1]

    assert empty_window["tick_start"] == 128
    assert empty_window["tick_end"] == 256
    assert empty_window["note_count"] == 0
    assert empty_window["density"] == {
        "note_density": 0.0,
        "active_tick_count": 0,
        "mean_notes_per_active_tick": 0.0,
    }
    assert empty_window["instrument_counts"] == {}
    assert empty_window["volume"] == {
        "mean": None,
        "std": None,
        "min": None,
        "max": None,
    }
    assert empty_window["pitch"]["dominant_pitch"] is None
    assert empty_window["rhythm"] == {
        "avg_tick_gap": None,
        "median_tick_gap": None,
        "most_common_tick_gap": None,
        "regularity_score": None,
    }
    assert empty_window["layer_activity"] == [
        {"layer_id": 1, "note_count": 0, "ratio": 0.0},
        {"layer_id": 2, "note_count": 0, "ratio": 0.0},
    ]
    assert empty_window["simultaneity"] == {
        "max_notes_per_tick": 0,
        "multi_note_tick_ratio": 0.0,
    }
    assert empty_window["window_texture_guess"] == "empty"


def test_window_texture_guess_identifies_percussion_like() -> None:
    group_windows = compute_group_windows(
        [
            _note(tick=0, layer=1, instrument=0),
            _note(tick=16, layer=1, instrument=0),
        ],
        LayerGroupConfig(
            name="declared_drums",
            layers=(1,),
            grouping_mode="percussion",
        ),
        window_size=128,
        hop_size=128,
    )
    instrument_windows = compute_group_windows(
        [
            _note(tick=0, layer=1, instrument=2),
            _note(tick=16, layer=1, instrument=3),
            _note(tick=32, layer=1, instrument=4),
            _note(tick=48, layer=1, instrument=2),
            _note(tick=64, layer=1, instrument=0),
        ],
        LayerGroupConfig(name="mostly_drums", layers=(1,)),
        window_size=128,
        hop_size=128,
    )

    assert group_windows[0]["window_texture_guess"] == "percussion_like"
    assert instrument_windows[0]["window_texture_guess"] == "percussion_like"


def test_window_texture_guess_identifies_single_line_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=40),
            _note(tick=17, layer=1, key=43),
            _note(tick=39, layer=1, key=47),
            _note(tick=73, layer=1, key=52),
        ],
        LayerGroupConfig(name="lead", layers=(1,)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "single_line_like"


def test_window_texture_guess_identifies_layered_or_chord_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=40),
            _note(tick=0, layer=2, key=44),
            _note(tick=0, layer=3, key=47),
            _note(tick=17, layer=1, key=41),
            _note(tick=29, layer=2, key=45),
        ],
        LayerGroupConfig(name="chords", layers=(1, 2, 3)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "layered_or_chord_like"


def test_window_texture_guess_identifies_repeated_pattern_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=40),
            _note(tick=16, layer=1, key=44),
            _note(tick=32, layer=1, key=47),
            _note(tick=48, layer=1, key=52),
            _note(tick=64, layer=1, key=55),
            _note(tick=80, layer=1, key=59),
        ],
        LayerGroupConfig(name="arp", layers=(1,)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "repeated_pattern_like"


def test_window_texture_guess_identifies_effect_or_transition_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=64, layer=1, key=40),
            _note(tick=65, layer=1, key=52),
        ],
        LayerGroupConfig(name="effect", layers=(1,)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "effect_or_transition_like"


def test_window_texture_guess_identifies_sustain_texture_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45),
            _note(tick=16, layer=2, key=45),
            _note(tick=32, layer=2, key=46),
            _note(tick=48, layer=2, key=45),
            _note(tick=64, layer=2, key=46),
            _note(tick=80, layer=2, key=45),
        ],
        LayerGroupConfig(
            name="sustain",
            layers=(1, 2),
            grouping_mode="instrument_split",
            layer_parts={
                1: "head",
                2: "tail",
            },
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "sustain_texture_like"


def test_window_texture_guess_identifies_mixed_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=40),
            _note(tick=0, layer=2, key=52),
            _note(tick=16, layer=1, key=43),
            _note(tick=16, layer=2, key=55),
            _note(tick=32, layer=1, key=47),
            _note(tick=32, layer=2, key=59),
            _note(tick=48, layer=1, key=50),
            _note(tick=48, layer=2, key=62),
        ],
        LayerGroupConfig(name="mixed", layers=(1, 2)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "mixed_like"


def test_analyze_note_stereo_outputs_group_windows() -> None:
    report = analyze_note_stereo(
        [
            _note(tick=0, layer=1),
            _note(tick=128, layer=1),
        ],
        group_configs=[LayerGroupConfig(name="group", layers=(1,))],
    )

    windows = report["groups"][0]["windows"]

    assert [window["tick_start"] for window in windows] == [
        0,
        32,
        64,
        96,
        128,
    ]
    assert windows[0]["note_count"] == 1
    assert windows[-1]["note_count"] == 1


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
                grouping_mode="percussion",
            )
        }
    )

    assert jsonable == {
        "group": {
            "name": "percussion",
            "layers": [1, 2],
            "grouping_mode": "percussion",
            "pan_region": "unknown",
            "layer_parts": {},
        }
    }


def test_analysis_json_contains_window_texture_guess_only() -> None:
    report = analyze_note_stereo(
        [_note(tick=0, layer=1)],
        group_configs=[LayerGroupConfig(name="group", layers=(1,))],
    )

    jsonable = analysis_report_to_jsonable(report)
    first_window = jsonable["groups"][0]["windows"][0]

    assert first_window["window_texture_guess"] == "effect_or_transition_like"
    assert "musical_role_guess" not in first_window
    assert "sustain_pattern_guess" not in first_window
