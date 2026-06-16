import json
from pathlib import Path

import pytest

from nbs2func.models import NoteEvent
from nbs2func.note_stereo_analyzer import (
    BOUNDARY_CANDIDATE_MAX_COUNT,
    BOUNDARY_CLUSTER_MAX_TICK_GAP,
    BOUNDARY_FINAL_MAX_COUNT,
    BOUNDARY_LOW_RELIABILITY_SOLO_MIN_SCORE,
    GROUP_NOVELTY_GLOBAL_MAX_COUNT,
    GROUP_SSM_NOVELTY_PEAK_MAX_COUNT,
    SSM_NOVELTY_PEAK_MAX_COUNT,
    STRUCTURE_BOUNDARY_MAX_COUNT,
    LayerGroupConfig,
    TrackFrameFeatureVector,
    analysis_report_to_jsonable,
    analyze_note_stereo,
    build_structure_boundary_candidates,
    compute_adjacent_change_scores,
    compute_group_windows,
    compute_novelty_curve_from_frames,
    compute_self_similarity_summary,
    compute_group_ssm_summaries,
    compute_track_frame_feature_vectors,
    detect_group_novelty_peaks,
    compute_window_feature_vectors,
    detect_novelty_peaks,
    detect_boundary_candidates,
    flatten_group_novelty_peaks,
    load_group_config,
    window_report_to_feature_vector,
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


def _window_report(
    *,
    tick_start: int,
    note_count: int,
    texture: str = "single_line_like",
    sustain: str = "none",
    note_density: float = 0.1,
    mean_notes_per_active_tick: float = 1.0,
    multi_note_tick_ratio: float = 0.0,
    pitch_mean: float | None = 45.0,
    pitch_std: float | None = 0.0,
    volume_mean: float | None = 100.0,
    volume_std: float | None = 0.0,
    pan_mean: float | None = 100.0,
    pan_std: float | None = 0.0,
    regularity_score: float | None = 1.0,
) -> dict:
    return {
        "tick_start": tick_start,
        "tick_end": tick_start + 64,
        "note_count": note_count,
        "density": {
            "note_density": note_density,
            "active_tick_count": note_count,
            "mean_notes_per_active_tick": mean_notes_per_active_tick,
        },
        "instrument_counts": {},
        "volume": {
            "mean": volume_mean,
            "std": volume_std,
            "min": volume_mean,
            "max": volume_mean,
        },
        "pan": {
            "mean": pan_mean,
            "std": pan_std,
            "min": pan_mean,
            "max": pan_mean,
        },
        "pitch": {
            "mean": pitch_mean,
            "std": pitch_std,
            "min": pitch_mean,
            "max": pitch_mean,
            "dominant_pitch": pitch_mean,
        },
        "rhythm": {
            "avg_tick_gap": None,
            "median_tick_gap": None,
            "most_common_tick_gap": None,
            "regularity_score": regularity_score,
        },
        "layer_activity": [],
        "simultaneity": {
            "max_notes_per_tick": note_count,
            "multi_note_tick_ratio": multi_note_tick_ratio,
        },
        "window_texture_guess": texture,
        "sustain_pattern_guess": sustain,
    }


def _group_report(
    *,
    name: str,
    windows: list[dict],
    grouping_mode: str = "manual_mixed",
    layers: list[int] | None = None,
) -> dict:
    return {
        "name": name,
        "grouping_mode": grouping_mode,
        "layers": layers or [1],
        "note_count": sum(window["note_count"] for window in windows),
        "tick_start": min((window["tick_start"] for window in windows), default=None),
        "tick_end": max((window["tick_end"] for window in windows), default=None),
        "missing_layers": [],
        "windows": windows,
    }


def _boundary_candidate(
    *,
    tick: int = 128,
    score: float = 4.0,
    groups: list[str] | None = None,
    group_weights: dict[str, float] | None = None,
) -> dict:
    candidate_groups = groups or ["lead"]
    weights = group_weights or {group: 1.0 for group in candidate_groups}
    return {
        "tick": tick,
        "tick_start": tick - 32,
        "tick_end": tick + 32,
        "score": score,
        "groups": candidate_groups,
        "group_scores": {
            group: score
            for group in candidate_groups
        },
        "group_raw_scores": {
            group: score
            for group in candidate_groups
        },
        "group_weights": weights,
        "top_components": {"activity": 2.0},
        "component_scores": {"activity": 2.0},
        "weighted_component_scores": {"activity": 2.0},
        "member_count": 1,
    }


def _group_novelty_peak(
    *,
    group: str = "lead",
    tick: int = 128,
    score: float = 0.6,
    boundary_weight: float = 1.0,
) -> dict:
    return {
        "tick": tick,
        "score": score,
        "weighted_score": score * boundary_weight,
        "group": group,
        "boundary_weight": boundary_weight,
        "left_tick_start": tick - 32,
        "right_tick_start": tick,
    }


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
                        "name": "flute_1",
                        "layers": [19, 20],
                        "grouping_mode": "sustain_split",
                        "layer_parts": {
                            "19": "left_tail",
                            "20": "right_tail",
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
            name="flute_1",
            layers=(19, 20),
            grouping_mode="sustain_split",
            layer_parts={
                19: "left_tail",
                20: "right_tail",
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
    assert empty_window["sustain_pattern_guess"] == "none"


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


def test_window_texture_guess_keeps_stable_repeated_layers_as_layered() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, instrument=0, key=40),
            _note(tick=0, layer=2, instrument=0, key=52),
            _note(tick=16, layer=1, instrument=0, key=43),
            _note(tick=16, layer=2, instrument=0, key=55),
            _note(tick=32, layer=1, instrument=0, key=47),
            _note(tick=32, layer=2, instrument=0, key=59),
            _note(tick=48, layer=1, instrument=0, key=50),
            _note(tick=48, layer=2, instrument=0, key=62),
        ],
        LayerGroupConfig(name="stable_layers", layers=(1, 2)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "layered_or_chord_like"


def test_window_texture_guess_identifies_complex_mixed_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, instrument=0, key=40),
            _note(tick=0, layer=2, instrument=5, key=52),
            _note(tick=16, layer=1, instrument=0, key=43),
            _note(tick=16, layer=2, instrument=5, key=55),
            _note(tick=32, layer=1, instrument=6, key=47),
            _note(tick=32, layer=2, instrument=5, key=59),
            _note(tick=48, layer=1, instrument=0, key=50),
            _note(tick=48, layer=2, instrument=6, key=62),
        ],
        LayerGroupConfig(name="mixed", layers=(1, 2)),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "mixed_like"


def test_window_texture_guess_does_not_treat_stable_pitch_as_sustain_alone() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45),
            _note(tick=16, layer=1, key=45),
            _note(tick=32, layer=1, key=46),
            _note(tick=48, layer=1, key=45),
            _note(tick=64, layer=1, key=46),
            _note(tick=80, layer=1, key=45),
        ],
        LayerGroupConfig(
            name="stable_manual",
            layers=(1,),
            grouping_mode="manual_mixed",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "none"
    assert windows[0]["window_texture_guess"] != "sustain_texture_like"


def test_sustain_pattern_guess_identifies_inline_alternating_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45, final_panning=80),
            _note(tick=16, layer=1, key=45, final_panning=120),
            _note(tick=32, layer=1, key=45, final_panning=80),
            _note(tick=48, layer=1, key=45, final_panning=120),
        ],
        LayerGroupConfig(
            name="inline_alternating",
            layers=(1,),
            grouping_mode="midi_instrument",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "inline_alternating_tail_like"


def test_sustain_pattern_guess_identifies_inline_decay_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45, final_volume=120),
            _note(tick=16, layer=1, key=45, final_volume=105),
            _note(tick=32, layer=1, key=45, final_volume=90),
            _note(tick=48, layer=1, key=45, final_volume=75),
        ],
        LayerGroupConfig(
            name="inline_decay",
            layers=(1,),
            grouping_mode="midi_instrument",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "inline_decay_tail_like"


def test_sustain_pattern_guess_identifies_inline_stable_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45, final_volume=100),
            _note(tick=17, layer=1, key=46, final_volume=102),
            _note(tick=35, layer=1, key=45, final_volume=99),
            _note(tick=70, layer=1, key=46, final_volume=101),
        ],
        LayerGroupConfig(
            name="inline_stable",
            layers=(1,),
            grouping_mode="instrument_mixed",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "inline_stable_tail_like"


def test_sustain_pattern_guess_identifies_split_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45),
            _note(tick=16, layer=2, key=45),
            _note(tick=32, layer=2, key=45),
            _note(tick=48, layer=2, key=45),
        ],
        LayerGroupConfig(
            name="split_tail",
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

    assert windows[0]["sustain_pattern_guess"] == "split_tail_like"


def test_sustain_pattern_guess_identifies_split_sustain_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=19, key=45),
            _note(tick=16, layer=20, key=45),
            _note(tick=32, layer=19, key=45),
            _note(tick=48, layer=20, key=45),
            _note(tick=64, layer=19, key=45),
            _note(tick=80, layer=20, key=45),
        ],
        LayerGroupConfig(
            name="flute_1",
            layers=(19, 20),
            grouping_mode="sustain_split",
            layer_parts={
                19: "left_tail",
                20: "right_tail",
            },
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "split_sustain_like"
    assert windows[0]["window_texture_guess"] == "sustain_texture_like"


def test_sustain_pattern_guess_identifies_pan_region_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=7, key=45),
            _note(tick=16, layer=8, key=45),
            _note(tick=32, layer=9, key=45),
        ],
        LayerGroupConfig(
            name="left_tail",
            layers=(7, 8, 9),
            grouping_mode="pan_region",
            pan_region="left",
            layer_parts={
                7: "main",
                8: "inner_tail",
                9: "outer_tail",
            },
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "pan_region_tail_like"


def test_sustain_pattern_guess_identifies_mixed_tail_like() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=45, final_volume=120, final_panning=80),
            _note(tick=16, layer=1, key=45, final_volume=105, final_panning=120),
            _note(tick=32, layer=1, key=45, final_volume=90, final_panning=80),
            _note(tick=48, layer=1, key=45, final_volume=75, final_panning=120),
        ],
        LayerGroupConfig(
            name="mixed_tail",
            layers=(1,),
            grouping_mode="midi_instrument",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "mixed_tail_like"


def test_sustain_pattern_guess_returns_none_without_obvious_sustain() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, key=40, final_volume=100),
            _note(tick=9, layer=1, key=48, final_volume=80),
            _note(tick=31, layer=1, key=55, final_volume=130),
            _note(tick=72, layer=1, key=63, final_volume=90),
        ],
        LayerGroupConfig(
            name="plain_line",
            layers=(1,),
            grouping_mode="midi_instrument",
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["sustain_pattern_guess"] == "none"


def test_mixed_texture_does_not_trigger_for_instrument_split_stable_structure() -> None:
    windows = compute_group_windows(
        [
            _note(tick=0, layer=1, instrument=0, key=45),
            _note(tick=0, layer=2, instrument=5, key=57),
            _note(tick=16, layer=1, instrument=0, key=45),
            _note(tick=16, layer=2, instrument=5, key=57),
            _note(tick=32, layer=1, instrument=0, key=45),
            _note(tick=32, layer=2, instrument=5, key=57),
        ],
        LayerGroupConfig(
            name="split_colors",
            layers=(1, 2),
            grouping_mode="instrument_split",
            layer_parts={
                1: "head",
                2: "support",
            },
        ),
        window_size=128,
        hop_size=128,
    )

    assert windows[0]["window_texture_guess"] == "layered_or_chord_like"


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


def test_analyze_note_stereo_outputs_summary() -> None:
    report = analyze_note_stereo(
        [
            _note(tick=0, layer=1, instrument=2),
            _note(tick=32, layer=1, instrument=3),
            _note(tick=0, layer=2, instrument=0),
        ],
        group_configs=[
            LayerGroupConfig(
                name="drums",
                layers=(1,),
                grouping_mode="percussion",
            ),
            LayerGroupConfig(
                name="missing_tail",
                layers=(2, 3),
                grouping_mode="instrument_split",
                layer_parts={
                    3: "tail",
                },
            ),
        ],
        window_size=64,
        hop_size=64,
    )

    assert list(report) == ["layers", "groups", "summary"]
    summary = report["summary"]

    assert summary["overview"] == {
        "layer_count": 2,
        "group_count": 2,
        "total_notes": 3,
        "total_windows": 2,
    }
    assert summary["window_texture_counts"] == {
        "effect_or_transition_like": 1,
        "percussion_like": 1,
    }
    assert summary["sustain_pattern_counts"] == {
        "none": 2,
    }
    assert summary["groups"] == [
        {
            "name": "drums",
            "grouping_mode": "percussion",
            "layers": [1],
            "note_count": 2,
            "window_count": 1,
            "active_tick_start": 0,
            "active_tick_end": 32,
            "window_texture_counts": {
                "percussion_like": 1,
            },
            "sustain_pattern_counts": {
                "none": 1,
            },
            "texture_run_count": 1,
            "sustain_run_count": 1,
            "missing_layers": [],
            "boundary_weight": 1.0,
        },
        {
            "name": "missing_tail",
            "grouping_mode": "instrument_split",
            "layers": [2, 3],
            "note_count": 1,
            "window_count": 1,
            "active_tick_start": 0,
            "active_tick_end": 0,
            "window_texture_counts": {
                "effect_or_transition_like": 1,
            },
            "sustain_pattern_counts": {
                "none": 1,
            },
            "texture_run_count": 1,
            "sustain_run_count": 1,
            "missing_layers": [3],
            "boundary_weight": 0.25,
        },
    ]
    assert summary["boundary_candidates"] == []
    assert summary["ssm"] | {
        "diagonal_mean": 1.0,
    } == {
        "scope": "global_track_frame",
        "frame_count": 1,
        "tick_start": 0,
        "tick_end": 64,
        "similarity_method": "cosine",
        "full_matrix_output": False,
        "diagonal_mean": 1.0,
        "off_diagonal_mean": 0.0,
        "off_diagonal_max": 0.0,
        "off_diagonal_min": 0.0,
        "stats_truncated": False,
    }
    assert summary["ssm"]["diagonal_mean"] == pytest.approx(1.0)
    assert summary["novelty_peaks"] == []
    assert [group["name"] for group in summary["group_ssm"]] == [
        "drums",
        "missing_tail",
    ]
    assert summary["group_novelty_peaks"] == []
    assert summary["structure_boundary_candidates"] == []
    assert summary["structure_boundary_summary"] == {
        "candidate_count": 0,
        "from_boundary_candidate_count": 0,
        "from_group_novelty_count": 0,
        "source_agreement_count": 0,
        "match_tolerance_ticks": 64,
    }
    assert "windows" not in summary["groups"][0]


def test_window_report_to_feature_vector_sets_one_hot_and_activity() -> None:
    group_report = {"name": "lead"}
    active_vector = window_report_to_feature_vector(
        group_report,
        _window_report(
            tick_start=0,
            note_count=1,
            texture="single_line_like",
            sustain="none",
        ),
    )
    empty_vector = window_report_to_feature_vector(
        group_report,
        _window_report(
            tick_start=64,
            note_count=0,
            texture="empty",
            sustain="none",
            pitch_mean=None,
            pitch_std=None,
            volume_mean=None,
            volume_std=None,
            pan_mean=None,
            pan_std=None,
            regularity_score=None,
        ),
    )

    assert active_vector.group_name == "lead"
    assert active_vector.values["texture_single_line_like"] == 1.0
    assert active_vector.values["texture_empty"] == 0.0
    assert active_vector.values["sustain_none"] == 1.0
    assert active_vector.values["group_active"] == 1.0
    assert empty_vector.values["group_active"] == 0.0
    assert empty_vector.values["pitch_mean"] == 0.0


def test_compute_window_feature_vectors_flattens_group_windows() -> None:
    group_reports = [
        {
            "name": "lead",
            "windows": [
                _window_report(tick_start=0, note_count=1),
                _window_report(tick_start=64, note_count=0, texture="empty"),
            ],
        }
    ]

    vectors = compute_window_feature_vectors(group_reports)

    assert [vector.tick_start for vector in vectors] == [0, 64]
    assert [vector.group_name for vector in vectors] == ["lead", "lead"]


def test_track_frame_vectors_aggregate_groups_at_same_tick() -> None:
    group_reports = [
        _group_report(
            name="lead",
            windows=[
                _window_report(tick_start=0, note_count=4, note_density=0.2),
            ],
        ),
        _group_report(
            name="bass",
            windows=[
                _window_report(tick_start=0, note_count=4, note_density=0.6),
            ],
        ),
    ]

    frames = compute_track_frame_feature_vectors(group_reports)

    assert len(frames) == 1
    assert frames[0].tick_start == 0
    assert frames[0].values["active_group_count"] == 2.0
    assert frames[0].values["active_group_ratio"] == 1.0
    assert frames[0].values["mean_note_density"] == 0.4
    assert frames[0].values["texture_single_line_like_ratio"] == 1.0


def test_track_frame_vectors_are_sorted_by_tick() -> None:
    group_reports = [
        _group_report(
            name="lead",
            windows=[
                _window_report(tick_start=64, note_count=1),
                _window_report(tick_start=0, note_count=1),
            ],
        ),
    ]

    frames = compute_track_frame_feature_vectors(group_reports)

    assert [frame.tick_start for frame in frames] == [0, 64]


def test_track_frame_vectors_count_inactive_windows() -> None:
    group_reports = [
        _group_report(
            name="lead",
            windows=[
                _window_report(tick_start=0, note_count=0, texture="empty"),
            ],
        ),
        _group_report(
            name="bass",
            windows=[
                _window_report(tick_start=0, note_count=3),
            ],
        ),
    ]

    frames = compute_track_frame_feature_vectors(group_reports)

    assert frames[0].values["active_group_count"] == 1.0
    assert frames[0].values["active_group_ratio"] == 0.5
    assert frames[0].values["texture_empty_ratio"] == 0.5
    assert frames[0].values["texture_single_line_like_ratio"] == 0.5


def test_self_similarity_summary_identical_nonzero_frames() -> None:
    frames = [
        TrackFrameFeatureVector(
            tick_start=0,
            tick_end=64,
            values={
                "active_group_ratio": 1.0,
                "mean_note_density": 0.5,
                "_group_count": 1.0,
            },
        ),
        TrackFrameFeatureVector(
            tick_start=64,
            tick_end=128,
            values={
                "active_group_ratio": 1.0,
                "mean_note_density": 0.5,
                "_group_count": 1.0,
            },
        ),
    ]

    summary = compute_self_similarity_summary(frames)

    assert summary["similarity_method"] == "cosine"
    assert summary["full_matrix_output"] is False
    assert summary["diagonal_mean"] == pytest.approx(1.0)
    assert summary["off_diagonal_mean"] == pytest.approx(1.0)


def test_self_similarity_summary_handles_zero_vectors() -> None:
    frames = [
        TrackFrameFeatureVector(
            tick_start=0,
            tick_end=64,
            values={
                "active_group_ratio": 0.0,
                "mean_note_density": 0.0,
                "_group_count": 1.0,
            },
        ),
        TrackFrameFeatureVector(
            tick_start=64,
            tick_end=128,
            values={
                "active_group_ratio": 0.0,
                "mean_note_density": 0.0,
                "_group_count": 1.0,
            },
        ),
    ]

    summary = compute_self_similarity_summary(frames)

    assert summary["off_diagonal_mean"] == 0.0
    assert summary["off_diagonal_max"] == 0.0


def test_novelty_score_is_low_for_identical_adjacent_frames() -> None:
    frames = [
        TrackFrameFeatureVector(
            tick_start=0,
            tick_end=64,
            values={
                "active_group_ratio": 1.0,
                "mean_note_density": 0.5,
                "_group_count": 1.0,
            },
        ),
        TrackFrameFeatureVector(
            tick_start=64,
            tick_end=128,
            values={
                "active_group_ratio": 1.0,
                "mean_note_density": 0.5,
                "_group_count": 1.0,
            },
        ),
    ]

    novelty_curve = compute_novelty_curve_from_frames(frames)

    assert novelty_curve[0]["score"] == pytest.approx(0.0)


def test_novelty_score_is_high_for_changed_adjacent_frames() -> None:
    frames = [
        TrackFrameFeatureVector(
            tick_start=0,
            tick_end=64,
            values={
                "texture_empty_ratio": 1.0,
                "_group_count": 1.0,
            },
        ),
        TrackFrameFeatureVector(
            tick_start=64,
            tick_end=128,
            values={
                "texture_percussion_like_ratio": 1.0,
                "_group_count": 1.0,
            },
        ),
    ]

    novelty_curve = compute_novelty_curve_from_frames(frames)

    assert novelty_curve[0] == {
        "tick": 64,
        "score": 1.0,
        "left_tick_start": 0,
        "right_tick_start": 64,
    }


def test_novelty_peaks_are_capped() -> None:
    novelty_curve = [
        {
            "tick": index * 64,
            "score": 1.0 - index / 1000,
            "left_tick_start": index * 64 - 64,
            "right_tick_start": index * 64,
        }
        for index in range(SSM_NOVELTY_PEAK_MAX_COUNT + 5)
    ]

    peaks = detect_novelty_peaks(novelty_curve)

    assert len(peaks) == SSM_NOVELTY_PEAK_MAX_COUNT
    assert peaks[0]["score"] >= peaks[-1]["score"]


def test_group_ssm_summary_contains_group_stats_and_peaks() -> None:
    group_reports = [
        _group_report(
            name="lead",
            windows=[
                _window_report(
                    tick_start=0,
                    note_count=4,
                    texture="single_line_like",
                ),
                _window_report(
                    tick_start=64,
                    note_count=4,
                    texture="percussion_like",
                ),
            ],
        ),
    ]
    group_summaries = [{"name": "lead", "boundary_weight": 1.1}]

    group_ssm = compute_group_ssm_summaries(group_reports, group_summaries)

    assert len(group_ssm) == 1
    assert group_ssm[0]["name"] == "lead"
    assert group_ssm[0]["scope"] == "group"
    assert group_ssm[0]["frame_count"] == 2
    assert group_ssm[0]["similarity_method"] == "cosine"
    assert group_ssm[0]["full_matrix_output"] is False
    assert group_ssm[0]["boundary_weight"] == 1.1
    assert group_ssm[0]["novelty_peaks"]


def test_group_novelty_detects_changed_group_when_other_group_is_unchanged() -> None:
    group_reports = [
        _group_report(
            name="changed",
            windows=[
                _window_report(
                    tick_start=0,
                    note_count=4,
                    texture="single_line_like",
                ),
                _window_report(
                    tick_start=64,
                    note_count=4,
                    texture="percussion_like",
                ),
            ],
        ),
        _group_report(
            name="unchanged",
            windows=[
                _window_report(
                    tick_start=0,
                    note_count=4,
                    texture="single_line_like",
                ),
                _window_report(
                    tick_start=64,
                    note_count=4,
                    texture="single_line_like",
                ),
            ],
        ),
    ]
    group_summaries = [
        {"name": "changed", "boundary_weight": 1.0},
        {"name": "unchanged", "boundary_weight": 1.0},
    ]

    group_ssm = compute_group_ssm_summaries(group_reports, group_summaries)
    peaks_by_group = {
        group_summary["name"]: group_summary["novelty_peaks"]
        for group_summary in group_ssm
    }

    assert peaks_by_group["changed"]
    assert peaks_by_group["unchanged"] == []


def test_group_novelty_ignores_empty_to_empty_transitions() -> None:
    group_reports = [
        _group_report(
            name="silent",
            windows=[
                _window_report(tick_start=0, note_count=0, texture="empty"),
                _window_report(tick_start=64, note_count=0, texture="empty"),
            ],
        )
    ]
    group_summaries = [{"name": "silent", "boundary_weight": 1.0}]

    group_ssm = compute_group_ssm_summaries(group_reports, group_summaries)

    assert group_ssm[0]["novelty_peaks"] == []


def test_group_novelty_allows_empty_to_active_transition() -> None:
    group_reports = [
        _group_report(
            name="entry",
            windows=[
                _window_report(tick_start=0, note_count=0, texture="empty"),
                _window_report(
                    tick_start=64,
                    note_count=4,
                    texture="single_line_like",
                ),
            ],
        )
    ]
    group_summaries = [{"name": "entry", "boundary_weight": 1.0}]

    group_ssm = compute_group_ssm_summaries(group_reports, group_summaries)

    assert group_ssm[0]["novelty_peaks"][0]["tick"] == 64


def test_flattened_group_novelty_peaks_include_weighted_score_and_sorting() -> None:
    group_ssm = [
        {
            "name": "quiet",
            "boundary_weight": 0.5,
            "novelty_peaks": [
                {
                    "tick": 64,
                    "score": 0.9,
                    "left_tick_start": 0,
                    "right_tick_start": 64,
                }
            ],
        },
        {
            "name": "structural",
            "boundary_weight": 1.2,
            "novelty_peaks": [
                {
                    "tick": 128,
                    "score": 0.5,
                    "left_tick_start": 64,
                    "right_tick_start": 128,
                }
            ],
        },
    ]

    flattened = flatten_group_novelty_peaks(group_ssm)

    assert flattened[0]["group"] == "structural"
    assert flattened[0]["weighted_score"] == pytest.approx(0.6)
    assert flattened[0]["boundary_weight"] == 1.2
    assert flattened[1]["group"] == "quiet"


def test_flattened_group_novelty_peaks_are_capped() -> None:
    group_ssm = [
        {
            "name": f"group_{index}",
            "boundary_weight": 1.0,
            "novelty_peaks": [
                {
                    "tick": index * 64,
                    "score": 1.0 - index / 1000,
                    "left_tick_start": index * 64 - 64,
                    "right_tick_start": index * 64,
                }
            ],
        }
        for index in range(GROUP_NOVELTY_GLOBAL_MAX_COUNT + 5)
    ]

    flattened = flatten_group_novelty_peaks(group_ssm)

    assert len(flattened) == GROUP_NOVELTY_GLOBAL_MAX_COUNT
    assert flattened[0]["weighted_score"] >= flattened[-1]["weighted_score"]


def test_group_novelty_peaks_are_capped() -> None:
    novelty_curve = [
        {
            "tick": index * 64,
            "score": 1.0 - index / 1000,
            "left_tick_start": index * 64 - 64,
            "right_tick_start": index * 64,
        }
        for index in range(GROUP_SSM_NOVELTY_PEAK_MAX_COUNT + 5)
    ]

    peaks = detect_group_novelty_peaks(novelty_curve)

    assert len(peaks) == GROUP_SSM_NOVELTY_PEAK_MAX_COUNT


def test_structure_boundary_candidates_merge_boundary_and_novelty_sources() -> None:
    candidates = build_structure_boundary_candidates(
        [_boundary_candidate(tick=128, score=4.0)],
        [_group_novelty_peak(tick=160, score=0.6)],
    )

    assert len(candidates) == 1
    assert candidates[0]["tick"] == 128
    assert candidates[0]["sources"] == [
        "boundary_candidate",
        "group_novelty_peak",
    ]
    assert candidates[0]["support"] == {
        "boundary": True,
        "group_novelty": True,
        "multi_group": False,
    }
    assert candidates[0]["matched_novelty_peak_count"] == 1
    assert candidates[0]["matched_novelty_groups"] == ["lead"]
    assert candidates[0]["matched_novelty_peaks"] == [
        {
            "group": "lead",
            "tick": 160,
            "weighted_score": 0.6,
        }
    ]


def test_structure_boundary_confidence_increases_with_source_agreement() -> None:
    boundary_only = build_structure_boundary_candidates(
        [_boundary_candidate(tick=128, score=4.0)],
        [],
    )[0]
    with_novelty = build_structure_boundary_candidates(
        [_boundary_candidate(tick=128, score=4.0)],
        [_group_novelty_peak(tick=128, score=0.6)],
    )[0]

    assert with_novelty["confidence"] > boundary_only["confidence"]


def test_structure_boundary_multi_group_evidence_increases_confidence() -> None:
    single_group = build_structure_boundary_candidates(
        [_boundary_candidate(tick=128, score=4.0)],
        [_group_novelty_peak(group="lead", tick=128, score=0.6)],
    )[0]
    multi_group = build_structure_boundary_candidates(
        [
            _boundary_candidate(
                tick=128,
                score=4.0,
                groups=["lead", "bass"],
                group_weights={"lead": 1.0, "bass": 1.0},
            )
        ],
        [_group_novelty_peak(group="bass", tick=128, score=0.6)],
    )[0]

    assert multi_group["support"]["multi_group"] is True
    assert multi_group["confidence"] > single_group["confidence"]


def test_structure_boundary_low_reliability_only_evidence_is_penalized() -> None:
    reliable = build_structure_boundary_candidates(
        [
            _boundary_candidate(
                tick=128,
                score=8.0,
                group_weights={"lead": 1.0},
            )
        ],
        [],
    )[0]
    low_reliability = build_structure_boundary_candidates(
        [
            _boundary_candidate(
                tick=128,
                score=8.0,
                group_weights={"lead": 0.5},
            )
        ],
        [],
    )[0]

    assert low_reliability["confidence"] < reliable["confidence"]


def test_structure_boundary_keeps_strong_novelty_only_candidate() -> None:
    candidates = build_structure_boundary_candidates(
        [],
        [_group_novelty_peak(group="lead", tick=128, score=0.95)],
    )

    assert len(candidates) == 1
    assert candidates[0]["sources"] == ["group_novelty_peak"]
    assert candidates[0]["boundary_score"] == 0.0
    assert candidates[0]["novelty_score"] == pytest.approx(0.95)


def test_structure_boundary_filters_weak_novelty_only_candidate() -> None:
    candidates = build_structure_boundary_candidates(
        [],
        [_group_novelty_peak(group="lead", tick=128, score=0.5)],
    )

    assert candidates == []


def test_structure_boundary_keeps_multi_group_novelty_only_candidate() -> None:
    candidates = build_structure_boundary_candidates(
        [],
        [
            _group_novelty_peak(group="lead", tick=128, score=0.55),
            _group_novelty_peak(group="bass", tick=160, score=0.55),
        ],
    )

    assert len(candidates) == 1
    assert candidates[0]["support"]["multi_group"] is True
    assert candidates[0]["matched_novelty_groups"] == ["bass", "lead"]


def test_structure_boundary_candidates_are_capped() -> None:
    boundary_candidates = [
        _boundary_candidate(
            tick=index * 128,
            score=8.0 - index / 1000,
            groups=[f"group_{index}"],
            group_weights={f"group_{index}": 1.0},
        )
        for index in range(STRUCTURE_BOUNDARY_MAX_COUNT + 5)
    ]

    candidates = build_structure_boundary_candidates(boundary_candidates, [])

    assert len(candidates) == STRUCTURE_BOUNDARY_MAX_COUNT
    assert candidates[0]["confidence"] >= candidates[-1]["confidence"]


def test_adjacent_change_scores_detect_activity_change() -> None:
    group_report = {"name": "lead"}
    vectors = [
        window_report_to_feature_vector(
            group_report,
            _window_report(tick_start=0, note_count=0, texture="empty"),
        ),
        window_report_to_feature_vector(
            group_report,
            _window_report(tick_start=64, note_count=1),
        ),
    ]

    change = compute_adjacent_change_scores(vectors)[0]

    assert change["group"] == "lead"
    assert change["tick"] == 64
    assert change["components"]["activity"] > 0
    assert change["score"] > 0


def test_adjacent_change_scores_detect_label_changes() -> None:
    group_report = {"name": "lead"}
    vectors = [
        window_report_to_feature_vector(
            group_report,
            _window_report(
                tick_start=0,
                note_count=1,
                texture="single_line_like",
                sustain="none",
            ),
        ),
        window_report_to_feature_vector(
            group_report,
            _window_report(
                tick_start=64,
                note_count=1,
                texture="repeated_pattern_like",
                sustain="split_tail_like",
            ),
        ),
    ]

    change = compute_adjacent_change_scores(vectors)[0]

    assert change["components"]["texture"] > 0
    assert change["components"]["sustain"] > 0


def test_adjacent_change_scores_detect_numeric_component_changes() -> None:
    group_report = {"name": "lead"}
    vectors = [
        window_report_to_feature_vector(
            group_report,
            _window_report(tick_start=0, note_count=1),
        ),
        window_report_to_feature_vector(
            group_report,
            _window_report(
                tick_start=64,
                note_count=1,
                note_density=0.8,
                mean_notes_per_active_tick=3.0,
                pitch_mean=69.0,
                pitch_std=12.0,
                volume_mean=40.0,
                volume_std=20.0,
                pan_mean=150.0,
                pan_std=30.0,
                regularity_score=0.2,
            ),
        ),
    ]

    components = compute_adjacent_change_scores(vectors)[0]["components"]

    assert components["density"] > 0
    assert components["pitch"] > 0
    assert components["volume"] > 0
    assert components["pan"] > 0
    assert components["rhythm"] > 0


def test_group_boundary_weight_reflects_stability_and_fragmentation() -> None:
    report = analyze_note_stereo(
        [
            *[
                _note(tick=tick * 4, layer=1, instrument=0, key=45)
                for tick in range(40)
            ],
            _note(tick=0, layer=2, instrument=7, key=70),
            _note(tick=256, layer=2, instrument=7, key=74),
        ],
        group_configs=[
            LayerGroupConfig(name="stable", layers=(1,)),
            LayerGroupConfig(name="bell", layers=(2,)),
        ],
        window_size=64,
        hop_size=64,
    )

    summary_by_name = {
        group_summary["name"]: group_summary
        for group_summary in report["summary"]["groups"]
    }

    assert summary_by_name["stable"]["boundary_weight"] >= 1.0
    assert summary_by_name["bell"]["boundary_weight"] < 1.0
    assert (
        summary_by_name["stable"]["boundary_weight"]
        != summary_by_name["bell"]["boundary_weight"]
    )


def test_instrument_split_coherent_group_keeps_medium_high_weight() -> None:
    report = analyze_note_stereo(
        [
            *[
                _note(tick=tick * 8, layer=1, instrument=0, key=45)
                for tick in range(20)
            ],
            *[
                _note(tick=tick * 8, layer=2, instrument=5, key=57)
                for tick in range(20)
            ],
        ],
        group_configs=[
            LayerGroupConfig(
                name="split_colors",
                layers=(1, 2),
                grouping_mode="instrument_split",
                layer_parts={
                    1: "head",
                    2: "support",
                },
            ),
        ],
        window_size=64,
        hop_size=64,
    )

    weight = report["summary"]["groups"][0]["boundary_weight"]

    assert weight >= 1.0


def test_sustain_split_coherent_group_keeps_medium_high_weight() -> None:
    report = analyze_note_stereo(
        [
            *[
                _note(tick=tick * 8, layer=19, instrument=6, key=45)
                for tick in range(20)
            ],
            *[
                _note(tick=tick * 8 + 4, layer=20, instrument=6, key=45)
                for tick in range(20)
            ],
        ],
        group_configs=[
            LayerGroupConfig(
                name="flute_sustain",
                layers=(19, 20),
                grouping_mode="sustain_split",
                layer_parts={
                    19: "left_tail",
                    20: "right_tail",
                },
            ),
        ],
        window_size=64,
        hop_size=64,
    )

    weight = report["summary"]["groups"][0]["boundary_weight"]

    assert weight >= 1.0


def test_percussion_group_keeps_at_least_normal_weight() -> None:
    report = analyze_note_stereo(
        [
            _note(tick=0, layer=1, instrument=2),
            _note(tick=16, layer=1, instrument=3),
        ],
        group_configs=[
            LayerGroupConfig(
                name="drums",
                layers=(1,),
                grouping_mode="percussion",
            ),
        ],
        window_size=64,
        hop_size=64,
    )

    assert report["summary"]["groups"][0]["boundary_weight"] >= 1.0


def test_missing_layers_reduce_boundary_weight() -> None:
    report = analyze_note_stereo(
        [
            *[
                _note(tick=tick * 8, layer=1, instrument=0, key=45)
                for tick in range(12)
            ],
        ],
        group_configs=[
            LayerGroupConfig(
                name="complete",
                layers=(1,),
                grouping_mode="instrument_split",
            ),
            LayerGroupConfig(
                name="missing",
                layers=(1, 2, 3),
                grouping_mode="instrument_split",
            ),
        ],
        window_size=64,
        hop_size=64,
    )

    summary_by_name = {
        group_summary["name"]: group_summary
        for group_summary in report["summary"]["groups"]
    }

    assert (
        summary_by_name["missing"]["boundary_weight"]
        < summary_by_name["complete"]["boundary_weight"]
    )


def test_group_boundary_weight_affects_candidate_score() -> None:
    change_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 10.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        }
    ]
    group_summaries = [{"name": "bell", "boundary_weight": 0.5}]

    candidates = detect_boundary_candidates(change_scores, group_summaries)

    assert candidates[0]["group_scores"] == {"bell": 5.0}
    assert candidates[0]["group_raw_scores"] == {"bell": 10.0}
    assert candidates[0]["group_weights"] == {"bell": 0.5}


def test_low_reliability_single_group_candidate_below_threshold_is_filtered() -> None:
    change_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 4.0,
            "components": {
                "activity": 1.0,
                "texture": 1.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        }
    ]
    group_summaries = [{"name": "bell", "boundary_weight": 0.75}]

    assert detect_boundary_candidates(change_scores, group_summaries) == []


def test_low_reliability_single_group_candidate_above_threshold_is_kept() -> None:
    change_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": BOUNDARY_LOW_RELIABILITY_SOLO_MIN_SCORE / 0.75,
            "components": {
                "activity": 1.0,
                "texture": 1.0,
                "sustain": 1.0,
                "density": 1.0,
                "pitch": 1.0,
                "volume": 1.0,
                "pan": 1.0,
                "rhythm": 1.0,
            },
        }
    ]
    group_summaries = [{"name": "bell", "boundary_weight": 0.75}]

    candidates = detect_boundary_candidates(change_scores, group_summaries)

    assert candidates
    assert candidates[0]["group_weights"] == {"bell": 0.75}


def test_multi_group_candidate_with_structural_group_is_kept() -> None:
    change_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 1.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
        {
            "group": "piano",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 3.0,
            "components": {
                "activity": 1.0,
                "texture": 1.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
    ]
    group_summaries = [
        {"name": "bell", "boundary_weight": 0.75},
        {"name": "piano", "boundary_weight": 1.2},
    ]

    candidates = detect_boundary_candidates(change_scores, group_summaries)

    assert candidates
    assert candidates[0]["groups"] == ["bell", "piano"]


def test_top_components_use_weighted_component_scores() -> None:
    change_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 10.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
        {
            "group": "piano",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 3.0,
            "components": {
                "activity": 0.0,
                "texture": 1.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
    ]
    group_summaries = [
        {"name": "bell", "boundary_weight": 0.5},
        {"name": "piano", "boundary_weight": 1.2},
    ]

    candidates = detect_boundary_candidates(change_scores, group_summaries)

    assert candidates[0]["component_scores"] == {
        "activity": 2.0,
        "texture": 1.5,
        "sustain": 0.0,
        "density": 0.0,
        "pitch": 0.0,
        "volume": 0.0,
        "pan": 0.0,
        "rhythm": 0.0,
    }
    assert candidates[0]["weighted_component_scores"] == {
        "activity": 1.0,
        "texture": 1.7999999999999998,
        "sustain": 0.0,
        "density": 0.0,
        "pitch": 0.0,
        "volume": 0.0,
        "pan": 0.0,
        "rhythm": 0.0,
    }
    assert candidates[0]["top_components"] == {
        "texture": 1.7999999999999998,
        "activity": 1.0,
    }


def test_multi_group_low_reliability_candidate_requires_higher_score() -> None:
    low_scores = [
        {
            "group": "bell",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 2.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
        {
            "group": "chime",
            "tick": 128,
            "left_tick_start": 64,
            "right_tick_start": 128,
            "score": 2.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
    ]
    high_scores = [
        {
            **score,
            "score": 6.0,
        }
        for score in low_scores
    ]
    group_summaries = [
        {"name": "bell", "boundary_weight": 0.75},
        {"name": "chime", "boundary_weight": 0.75},
    ]

    assert detect_boundary_candidates(low_scores, group_summaries) == []
    assert detect_boundary_candidates(high_scores, group_summaries)


def test_nearby_boundary_candidates_are_clustered_and_merge_groups() -> None:
    change_scores = [
        {
            "group": "piano",
            "tick": 2080,
            "left_tick_start": 2016,
            "right_tick_start": 2080,
            "score": 3.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
        {
            "group": "bass",
            "tick": 2080 + BOUNDARY_CLUSTER_MAX_TICK_GAP,
            "left_tick_start": 2080,
            "right_tick_start": 2080 + BOUNDARY_CLUSTER_MAX_TICK_GAP,
            "score": 3.5,
            "components": {
                "activity": 0.0,
                "texture": 1.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
    ]

    candidates = detect_boundary_candidates(change_scores)

    assert len(candidates) == 1
    assert candidates[0]["tick"] == 2080 + BOUNDARY_CLUSTER_MAX_TICK_GAP
    assert candidates[0]["tick_start"] == 2080
    assert candidates[0]["tick_end"] == 2080 + BOUNDARY_CLUSTER_MAX_TICK_GAP
    assert candidates[0]["member_count"] == 2
    assert candidates[0]["groups"] == ["bass", "piano"]
    assert "component_scores" in candidates[0]
    assert "weighted_component_scores" in candidates[0]
    assert "group_weights" in candidates[0]


def test_distant_boundary_candidates_remain_separate() -> None:
    change_scores = [
        {
            "group": "piano",
            "tick": 0,
            "left_tick_start": -64,
            "right_tick_start": 0,
            "score": 3.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
        {
            "group": "piano",
            "tick": BOUNDARY_CLUSTER_MAX_TICK_GAP + 1,
            "left_tick_start": 0,
            "right_tick_start": BOUNDARY_CLUSTER_MAX_TICK_GAP + 1,
            "score": 3.0,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        },
    ]

    candidates = detect_boundary_candidates(change_scores)

    assert len(candidates) == 2


def test_detect_boundary_candidates_limits_count() -> None:
    change_scores = [
        {
            "group": f"group_{index}",
            "tick": index * (BOUNDARY_CLUSTER_MAX_TICK_GAP + 1),
            "left_tick_start": index * (BOUNDARY_CLUSTER_MAX_TICK_GAP + 1) - 64,
            "right_tick_start": index * (BOUNDARY_CLUSTER_MAX_TICK_GAP + 1),
            "score": 3.0 + index / 100,
            "components": {
                "activity": 1.0,
                "texture": 0.0,
                "sustain": 0.0,
                "density": 0.0,
                "pitch": 0.0,
                "volume": 0.0,
                "pan": 0.0,
                "rhythm": 0.0,
            },
        }
        for index in range(BOUNDARY_CANDIDATE_MAX_COUNT + 5)
    ]

    candidates = detect_boundary_candidates(change_scores)

    assert len(candidates) == BOUNDARY_FINAL_MAX_COUNT
    assert candidates[0]["score"] >= candidates[-1]["score"]
    assert candidates[0]["top_components"] == {"activity": 2.0, "density": 0.0}


def test_summary_includes_boundary_candidates() -> None:
    report = analyze_note_stereo(
        [
            *[
                _note(tick=tick, layer=1, instrument=0, key=45 + tick // 16)
                for tick in range(0, 64, 16)
            ],
            *[
                _note(tick=tick, layer=1, instrument=2, key=45)
                for tick in range(128, 192, 8)
            ],
            *[
                _note(tick=tick, layer=1, instrument=3, key=45)
                for tick in range(128, 192, 8)
            ],
        ],
        group_configs=[
            LayerGroupConfig(name="group", layers=(1,), grouping_mode="percussion"),
        ],
        window_size=64,
        hop_size=64,
    )

    candidates = report["summary"]["boundary_candidates"]

    assert candidates
    assert "tick" in candidates[0]
    assert "group" not in candidates[0]
    assert candidates[0]["groups"] == ["group"]


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


def test_analysis_json_contains_window_and_sustain_guesses() -> None:
    report = analyze_note_stereo(
        [_note(tick=0, layer=1)],
        group_configs=[LayerGroupConfig(name="group", layers=(1,))],
    )

    jsonable = analysis_report_to_jsonable(report)
    first_window = jsonable["groups"][0]["windows"][0]

    assert first_window["window_texture_guess"] == "effect_or_transition_like"
    assert first_window["sustain_pattern_guess"] == "none"
    assert "musical_role_guess" not in first_window
