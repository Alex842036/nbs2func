from __future__ import annotations

from pathlib import Path

import pytest

from nbs2func.config import config_from_dict, default_config
from nbs2func.core.models import NoteEvent, Song, Track
from nbs2func.generation import (
    GenerationEvent,
    GenerationResult,
    generate_from_config,
)
from nbs2func.layout.geometry import BlockPosition
from nbs2func.layout.models import LayoutResult
from nbs2func.output.command_writer import CommandWriteResult
from nbs2func.output.models import GeneratedBuildPlan


def _song() -> Song:
    return Song(
        name="Generation Song",
        author="Tester",
        length=64,
        tracks=(
            Track(
                id=1,
                name="Layer 1",
                source_layer=1,
                notes=(NoteEvent(tick=0, layer=1, instrument=0, key=45),),
            ),
        ),
    )


def _minimal_layout() -> LayoutResult:
    return LayoutResult(
        mode="test",
        cells=(),
        notes=(),
        conflicts=(),
    )


def test_generation_event_and_result_models() -> None:
    event = GenerationEvent("phase", "Reading NBS", detail="song.nbs")
    result = GenerationResult(
        output_format="both",
        datapack_path=Path("out/song"),
        schematic_path=Path("out/song.schem"),
        warnings=("careful",),
    )

    assert event.kind == "phase"
    assert event.detail == "song.nbs"
    assert result.datapack_path == Path("out/song")
    assert result.schematic_path == Path("out/song.schem")
    assert result.warnings == ("careful",)


def test_generate_from_config_emits_phase_output_and_done_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nbs_path = tmp_path / "song.nbs"
    nbs_path.write_bytes(b"placeholder")
    config = config_from_dict(
        {
            **default_config().__dict__,
            "input_path": str(nbs_path),
            "output": str(tmp_path / "out"),
            "layout_mode": "basic_linear",
            "tempo_control_mode": "none",
        }
    )
    events: list[GenerationEvent] = []

    monkeypatch.setattr("nbs2func.generation.read_nbs", lambda path: _song())
    monkeypatch.setattr(
        "nbs2func.generation.build_layout_strategy",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "nbs2func.generation.layout_song",
        lambda song, strategy: _minimal_layout(),
    )
    monkeypatch.setattr(
        "nbs2func.generation.total_track_length_from_layout",
        lambda *args: 0,
    )
    monkeypatch.setattr(
        "nbs2func.generation.build_generated_plan",
        lambda layout, writer_config: GeneratedBuildPlan(blocks=()),
    )
    monkeypatch.setattr(
        "nbs2func.generation.filter_generated_plan",
        lambda plan, options: plan,
    )
    monkeypatch.setattr(
        "nbs2func.generation.write_mcfunction",
        lambda *args, **kwargs: CommandWriteResult(
            total_commands=0,
            split_function_parts=1,
        ),
    )

    result = generate_from_config(config, progress_callback=events.append)

    assert result.output_format == "datapack"
    assert result.datapack_path == tmp_path / "out" / "song"
    assert result.schematic_path is None
    kinds = [event.kind for event in events]
    assert "phase" in kinds
    assert "output" in kinds
    assert kinds[-1] == "done"
    assert any(event.message.startswith("Generated datapack:") for event in events)


def test_generate_from_config_emits_error_and_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nbs_path = tmp_path / "song.nbs"
    nbs_path.write_bytes(b"placeholder")
    config = config_from_dict(
        {
            **default_config().__dict__,
            "input_path": str(nbs_path),
            "tempo_control_mode": "none",
        }
    )
    events: list[GenerationEvent] = []

    def fail_read(path: Path) -> object:
        raise ValueError("boom")

    monkeypatch.setattr("nbs2func.generation.read_nbs", fail_read)

    with pytest.raises(ValueError, match="boom"):
        generate_from_config(config, progress_callback=events.append)

    assert events[-1] == GenerationEvent("error", "boom")


def test_generate_from_config_can_emit_schematic_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nbs_path = tmp_path / "song.nbs"
    nbs_path.write_bytes(b"placeholder")
    config = config_from_dict(
        {
            **default_config().__dict__,
            "input_path": str(nbs_path),
            "output": str(tmp_path / "out"),
            "output_format": "schem",
            "layout_mode": "basic_linear",
            "tempo_control_mode": "none",
        }
    )
    events: list[GenerationEvent] = []

    monkeypatch.setattr("nbs2func.generation.read_nbs", lambda path: _song())
    monkeypatch.setattr(
        "nbs2func.generation.build_layout_strategy",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "nbs2func.generation.layout_song",
        lambda song, strategy: _minimal_layout(),
    )
    monkeypatch.setattr(
        "nbs2func.generation.total_track_length_from_layout",
        lambda *args: 0,
    )
    monkeypatch.setattr(
        "nbs2func.generation.build_generated_plan",
        lambda layout, writer_config: GeneratedBuildPlan(blocks=()),
    )
    monkeypatch.setattr(
        "nbs2func.generation.filter_generated_plan",
        lambda plan, options: plan,
    )
    monkeypatch.setattr(
        "nbs2func.generation.resolve_schematic_origin",
        lambda plan, mode, origin: BlockPosition(0, 128, 0),
    )

    def fake_write_schematic(*args, **kwargs) -> Path:
        schematic_path = tmp_path / "out" / "song.schem"
        schematic_path.parent.mkdir(parents=True, exist_ok=True)
        schematic_path.write_text("schem", encoding="utf-8")
        return schematic_path

    monkeypatch.setattr("nbs2func.generation.write_schematic", fake_write_schematic)
    monkeypatch.setattr("nbs2func.generation.schematic_warnings", lambda plan: ())

    result = generate_from_config(config, progress_callback=events.append)

    assert result.datapack_path is None
    assert result.schematic_path == tmp_path / "out" / "song.schem"
    assert any(event.message.startswith("Generated schematic:") for event in events)
