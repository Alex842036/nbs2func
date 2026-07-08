import json
import sys
from pathlib import Path

import pytest

from nbs2func import cli
from nbs2func import generation
from nbs2func.output.command_writer import CommandWriteResult
from nbs2func.config import (
    config_from_dict,
    config_to_dict,
    default_config,
    load_config,
    save_config,
)
from nbs2func.layout.geometry import BlockPosition
from nbs2func.layout.models import LayoutCell, LayoutResult
from nbs2func.core.models import NoteEvent, Song, Track


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


def _small_layout() -> LayoutResult:
    return LayoutResult(
        mode="test",
        cells=(
            LayoutCell(
                tick=0,
                track_id="0",
                source_track_id=0,
                repeater_position=BlockPosition(0, 128, 0),
                repeater_facing="west",
                track_block_position=BlockPosition(0, 127, 0),
                note_block_position=BlockPosition(-1, 128, 0),
                instrument_block_position=BlockPosition(-1, 127, 0),
                note=None,
            ),
        ),
        notes=(),
        conflicts=(),
    )


def _patch_small_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation, "read_nbs", lambda path: _song())
    monkeypatch.setattr(generation, "build_layout_strategy", lambda **kwargs: object())
    monkeypatch.setattr(
        generation,
        "layout_song",
        lambda song, strategy: _small_layout(),
    )
    monkeypatch.setattr(generation, "total_track_length_from_layout", lambda *args: 0)


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
    assert args.minecraft_version == "1.16.5"
    assert args.output == "build"


def test_parser_accepts_minecraft_version_argument() -> None:
    exact_args = cli.build_parser().parse_args(
        ["song.nbs", "--minecraft-version", "1.16.5"]
    )
    alias_args = cli.build_parser().parse_args(
        ["song.nbs", "--minecraft-version", "1.16"]
    )

    assert exact_args.minecraft_version == "1.16.5"
    assert alias_args.minecraft_version == "1.16"


def test_default_config_returns_current_defaults_and_new_instances() -> None:
    first = default_config()
    second = default_config()

    assert first is not second
    assert first.center_split_overrides is not second.center_split_overrides
    assert first.input_path == "examples/demo.nbs"
    assert first.output == "output"
    assert first.output_format == "datapack"
    assert first.schematic_origin_mode == "generation_origin"
    assert first.schematic_output is None
    assert first.schematic_name is None
    assert first.minecraft_version == "1.16.5"
    assert first.layout_mode == "note_based_stereo"
    assert first.split_functions is True
    assert first.function_namespace == "nbs"
    assert first.max_commands_per_build_part == 500
    assert first.preview_time_limit_seconds == 1200


def test_config_json_round_trip(tmp_path: Path) -> None:
    config = default_config()
    path = tmp_path / "config.json"

    data = config_to_dict(config)
    loaded_from_dict = config_from_dict(data)
    save_config(loaded_from_dict, path)
    loaded_from_file = load_config(path)

    assert loaded_from_dict == config
    assert loaded_from_file == config
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_missing_config_fields_use_defaults() -> None:
    config = config_from_dict({"minecraft_version": "1.20", "origin_y": 64})

    assert config.minecraft_version == "1.20"
    assert config.origin_y == 64
    assert config.input_path == "examples/demo.nbs"
    assert config.layout_mode == "note_based_stereo"


def test_unknown_config_field_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown config field"):
        config_from_dict({"does_not_exist": True})


def test_config_type_error_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="origin_x"):
        config_from_dict({"origin_x": "not an int"})


def test_dump_default_config_outputs_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["main.py", "--dump-default-config"])

    result = cli.main()

    assert result == 0
    data = json.loads(capsys.readouterr().out)
    assert data["minecraft_version"] == "1.16.5"
    assert data["layout_mode"] == "note_based_stereo"
    assert data["output_format"] == "datapack"


def test_cli_config_file_is_loaded_and_explicit_args_override(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "input_path": "from_config.nbs",
                "output": "configured_output",
                "minecraft_version": "1.20",
                "layout_mode": "basic_linear",
            }
        ),
        encoding="utf-8",
    )
    parser = cli.build_parser()
    argv = [
        "--config",
        str(config_path),
        "--minecraft-version",
        "1.16.5",
        "--layout-mode",
        "note_based_stereo",
    ]
    args = parser.parse_args(argv)
    explicit = cli._explicit_cli_destinations(parser, argv)

    config = cli.resolve_config_from_args(args, explicit)

    assert config.input_path == "from_config.nbs"
    assert config.output == "configured_output"
    assert config.minecraft_version == "1.16.5"
    assert config.layout_mode == "note_based_stereo"


def test_save_config_writes_final_effective_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "input_config.json"
    save_path = tmp_path / "saved" / "config.json"
    nbs_path = tmp_path / "missing.nbs"
    config_path.write_text(
        json.dumps({"input_path": str(nbs_path), "minecraft_version": "1.20"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--config",
            str(config_path),
            "--minecraft-version",
            "1.16.5",
            "--save-config",
            str(save_path),
        ],
    )

    result = cli.main()

    assert result == 1
    capsys.readouterr()
    saved = json.loads(save_path.read_text(encoding="utf-8"))
    assert saved["input_path"] == str(nbs_path)
    assert saved["minecraft_version"] == "1.16.5"


def test_default_generation_writes_datapack_key_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "examples/demo.nbs", "--output", str(tmp_path)],
    )

    result = cli.main()

    capsys.readouterr()
    assert result == 0
    datapack_root = tmp_path / "demo"
    assert (datapack_root / "pack.mcmeta").is_file()
    assert (
        datapack_root / "data" / "nbs" / "functions" / "build" / "start.mcfunction"
    ).is_file()


def test_output_format_schem_writes_only_schematic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    output_path = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--output",
            str(output_path),
            "--output-format",
            "schem",
            "--enable-starter-module",
            "--enable-playback-assist",
            "--layout-mode",
            "basic_linear",
        ],
    )
    _patch_small_generation(monkeypatch)

    result = cli.main()

    stdout = capsys.readouterr().out
    assert result == 0
    assert (output_path / "song.schem").is_file()
    assert not (output_path / "song" / "pack.mcmeta").exists()
    assert "Generated schematic:" in stdout
    assert "Generated datapack:" not in stdout
    assert "does not include starter or playback assist modules" in stdout


def test_output_format_both_writes_datapack_and_schematic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    output_path = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--output",
            str(output_path),
            "--output-format",
            "both",
            "--layout-mode",
            "basic_linear",
        ],
    )
    _patch_small_generation(monkeypatch)

    result = cli.main()

    capsys.readouterr()
    datapack_root = output_path / "song"
    assert result == 0
    assert (datapack_root / "pack.mcmeta").is_file()
    assert (
        datapack_root / "data" / "nbs" / "functions" / "build" / "start.mcfunction"
    ).is_file()
    assert (output_path / "song.schem").is_file()


def test_output_format_both_mcfunction_contains_only_runtime_logic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    output_path = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--output",
            str(output_path),
            "--output-format",
            "both",
            "--layout-mode",
            "basic_linear",
            "--enable-starter-module",
            "--enable-playback-assist",
            "--no-split-functions",
        ],
    )
    _patch_small_generation(monkeypatch)

    result = cli.main()

    stdout = capsys.readouterr().out
    mcfunction = (
        output_path
        / "song"
        / "data"
        / "nbs"
        / "functions"
        / "build"
        / "start.mcfunction"
    )
    text = mcfunction.read_text(encoding="utf-8")
    assert result == 0
    assert (output_path / "song.schem").is_file()
    assert "setblock" not in text
    assert "command_block" not in text
    assert "scoreboard objectives add" in text
    assert "summon minecraft:armor_stand" in text
    assert "contains all blocks including command blocks" in stdout
    assert "contains runtime logic" in stdout


def test_output_format_both_split_runtime_output_omits_structure_and_cleans_old_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    output_path = tmp_path / "out"
    old_file = (
        output_path
        / "song"
        / "data"
        / "nbs"
        / "functions"
        / "build"
        / "old_structure.mcfunction"
    )
    old_file.parent.mkdir(parents=True)
    old_file.write_text(
        "setblock 0 128 0 minecraft:note_block\n# layout.cell.note_block\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--output",
            str(output_path),
            "--output-format",
            "both",
            "--layout-mode",
            "basic_linear",
            "--enable-starter-module",
            "--enable-playback-assist",
        ],
    )
    _patch_small_generation(monkeypatch)

    result = cli.main()

    capsys.readouterr()
    datapack_root = output_path / "song"
    generated_functions = tuple(datapack_root.rglob("*.mcfunction"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in generated_functions)
    forbidden = (
        "minecraft:note_block",
        "minecraft:repeater",
        "layout.cell",
        "layout.note_based",
        "layout.cell.note_block",
        "layout.note_based.note_block",
        "layout.cell.repeater",
        "layout.note_based.repeater",
    )

    assert result == 0
    assert generated_functions
    assert not old_file.exists()
    assert all(snippet not in text for snippet in forbidden)


@pytest.mark.parametrize(
    ("version_arg", "expected_profile"),
    (
        ("1.16", "1.16.5"),
        ("1.20", "1.20.1"),
    ),
)
def test_generation_uses_minecraft_version_alias_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    version_arg: str,
    expected_profile: str,
) -> None:
    nbs_path = _write_placeholder_nbs(tmp_path)
    captured = {}
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            str(nbs_path),
            "--minecraft-version",
            version_arg,
            "--output",
            str(tmp_path / "out"),
        ],
    )
    monkeypatch.setattr(generation, "read_nbs", lambda path: _song())
    monkeypatch.setattr(generation, "build_layout_strategy", lambda **kwargs: object())
    monkeypatch.setattr(
        generation,
        "layout_song",
        lambda song, strategy: LayoutResult(
            mode="test",
            cells=(),
            notes=(),
            conflicts=(),
        ),
    )
    monkeypatch.setattr(generation, "total_track_length_from_layout", lambda *args: 0)

    def fake_write_mcfunction(layout, path, config, **kwargs):
        captured["profile"] = config.minecraft_version_profile
        return CommandWriteResult(total_commands=0, split_function_parts=1)

    monkeypatch.setattr(generation, "write_mcfunction", fake_write_mcfunction)

    result = cli.main()

    capsys.readouterr()
    assert result == 0
    assert captured["profile"].version_id == expected_profile


def test_cli_unknown_minecraft_version_exits_before_generation(
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
            "--minecraft-version",
            "1.12.2",
        ],
    )

    result = cli.main()

    stdout = capsys.readouterr().out
    assert result == 1
    assert "Unsupported Minecraft Java version" in stdout
    assert "1.16.5" in stdout
    assert "1.20" in stdout


def test_cli_requests_generation_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = {}
    monkeypatch.setattr(sys, "argv", ["main.py", "missing-is-ok-when-mocked.nbs"])

    def fake_generate_from_config(config, progress_callback=None, **kwargs):
        captured["progress_callback"] = progress_callback
        captured["include_diagnostics"] = kwargs.get("include_diagnostics")
        return generation.GenerationResult(output_format="datapack")

    monkeypatch.setattr(cli, "generate_from_config", fake_generate_from_config)
    monkeypatch.setattr(cli, "_print_cli_generation_report", lambda result, args: None)

    result = cli.main()

    capsys.readouterr()
    assert result == 0
    assert captured["progress_callback"] is None
    assert captured["include_diagnostics"] is True


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

    monkeypatch.setattr(cli, "generate_from_config", fail_if_called)

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
