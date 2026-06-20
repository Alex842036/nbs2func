import json
import sys
from pathlib import Path

import pytest

from nbs2func import cli
from nbs2func.models import NoteEvent, Song, Track


def _song() -> Song:
    return Song(
        name="Analyze Song",
        author="Tester",
        length=256,
        tracks=(
            Track(
                id=1,
                name="Layer 1",
                source_layer=1,
                notes=(
                    NoteEvent(tick=0, layer=1, instrument=2, key=40),
                    NoteEvent(tick=64, layer=1, instrument=3, key=42),
                ),
            ),
            Track(
                id=2,
                name="Layer 2",
                source_layer=2,
                notes=(NoteEvent(tick=128, layer=2, instrument=0, key=45),),
            ),
        ),
    )


def _write_placeholder_nbs(tmp_path: Path) -> Path:
    nbs_path = tmp_path / "song.nbs"
    nbs_path.write_bytes(b"placeholder")
    return nbs_path


def test_parser_keeps_existing_cli_arguments_available() -> None:
    args = cli.build_parser().parse_args(
        [
            "song.nbs",
            "--layout-mode",
            "basic_linear",
            "-o",
            "build",
        ]
    )

    assert args.analyze_layout_spatial is False
    assert args.analyze_stereo is False
    assert args.analysis_detail == "summary"
    assert args.layout_mode == "basic_linear"
    assert args.output == "build"


def test_analyze_layout_spatial_does_not_call_layout_writer_or_create_build_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    output_path = tmp_path / "build_output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
            "--output",
            str(output_path),
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    def fail_if_called(*args, **kwargs):
        raise AssertionError("generation path should not be called")

    monkeypatch.setattr(cli, "build_layout_strategy", fail_if_called)
    monkeypatch.setattr(cli, "layout_song", fail_if_called)
    monkeypatch.setattr(cli, "write_mcfunction", fail_if_called)

    result = cli.main()

    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    assert result == 0
    assert report["analysis_type"] == "layout_spatial"
    assert report["layers"][0]["layer_id"] == 1
    assert "groups" not in report
    assert not output_path.exists()


def test_analyze_layout_spatial_writes_analysis_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    analysis_output = tmp_path / "reports" / "analysis.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
            "--analysis-output",
            str(analysis_output),
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    result = cli.main()

    assert result == 0
    assert capsys.readouterr().out == ""
    report = json.loads(analysis_output.read_text(encoding="utf-8"))
    assert report["analysis_type"] == "layout_spatial"
    assert report["layers"][0]["note_count"] == 2


def test_analyze_layout_spatial_prints_json_to_stdout_without_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    result = cli.main()

    stdout = capsys.readouterr().out
    assert result == 0
    assert stdout.startswith("{\n  ")
    assert json.loads(stdout)["layers"][0]["layer_id"] == 1


def test_analyze_layout_spatial_passes_window_size_hop_size_and_detail_to_analyzer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    captured = {}
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
            "--analysis-window-size",
            "64",
            "--analysis-hop-size",
            "16",
            "--analysis-detail",
            "full",
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    def fake_analyze_layout_spatial(song, *, window_size, hop_size, detail):
        captured["song"] = song
        captured["window_size"] = window_size
        captured["hop_size"] = hop_size
        captured["detail"] = detail
        return {"analysis_type": "layout_spatial", "overview": {}, "layers": []}

    monkeypatch.setattr(
        cli,
        "analyze_layout_spatial",
        fake_analyze_layout_spatial,
    )

    result = cli.main()

    assert result == 0
    assert captured["song"].name == "Analyze Song"
    assert captured["window_size"] == 64
    assert captured["hop_size"] == 16
    assert captured["detail"] == "full"


def test_analyze_layout_spatial_full_detail_outputs_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
            "--analysis-detail",
            "full",
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    result = cli.main()

    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert "windows" in report["layers"][0]


def test_analyze_layout_spatial_rejects_group_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    group_config_path = tmp_path / "song.groups.json"
    group_config_path.write_text('{"groups":[]}', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-layout-spatial",
            "--group-config",
            str(group_config_path),
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    result = cli.main()

    stdout = capsys.readouterr().out
    assert result == 1
    assert "--group-config is not supported" in stdout
    assert not stdout.lstrip().startswith("{")


def test_analyze_stereo_fails_with_clear_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--analyze-stereo",
        ],
    )
    monkeypatch.setattr(cli, "read_nbs", lambda path: _song())

    result = cli.main()

    stdout = capsys.readouterr().out
    assert result == 1
    assert "--analyze-stereo was removed" in stdout
    assert "--analyze-layout-spatial" in stdout
