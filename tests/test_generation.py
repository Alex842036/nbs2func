from __future__ import annotations

from pathlib import Path

import pytest

from nbs2func.config import config_from_dict, default_config
from nbs2func.core.models import NoteEvent, Song, Track
from nbs2func.generation import (
    GenerationDiagnostics,
    GenerationEvent,
    GenerationResult,
    generate_from_config,
    monotonic_overall_progress,
    overall_percent_for_stage,
)
from nbs2func.layout.geometry import BlockPosition
from nbs2func.layout.models import LayoutProgressEvent, LayoutResult, StereoLayoutConfig
from nbs2func.layout.note_stereo import NoteBasedStereoLayout
from nbs2func.output.block_builder import build_generated_plan
from nbs2func.output.command_writer import (
    BasicMcfunctionWriter,
    CommandWriteResult,
    CommandWriterConfig,
)
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
    event = GenerationEvent(
        "progress",
        "Generating candidates",
        detail="candidate_generation",
        current=1000,
        total=13517,
        key="note_candidates",
        overall_percent=12.5,
        unit="emitters",
    )
    result = GenerationResult(
        output_format="both",
        datapack_path=Path("out/song"),
        schematic_path=Path("out/song.schem"),
        warnings=("careful",),
        diagnostics=GenerationDiagnostics(song="song", layout="layout"),
    )

    assert event.kind == "progress"
    assert event.detail == "candidate_generation"
    assert event.current == 1000
    assert event.total == 13517
    assert event.key == "note_candidates"
    assert event.overall_percent == 12.5
    assert event.unit == "emitters"
    assert result.datapack_path == Path("out/song")
    assert result.schematic_path == Path("out/song.schem")
    assert result.warnings == ("careful",)
    assert result.diagnostics is not None


def test_overall_progress_helpers_are_monotonic() -> None:
    assert overall_percent_for_stage("candidate_generation", 50, 100) == 14.0
    assert monotonic_overall_progress(40.0, 35.0) == 40.0
    assert monotonic_overall_progress(40.0, 45.0) == 45.0
    assert monotonic_overall_progress(40.0, None) == 40.0
    assert monotonic_overall_progress(40.0, 45.0, done=True) == 100.0


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
        lambda layout, writer_config, **kwargs: GeneratedBuildPlan(blocks=()),
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
    assert result.diagnostics is None
    kinds = [event.kind for event in events]
    assert "phase" in kinds
    assert "output" in kinds
    assert "done" not in kinds
    assert any(event.message.startswith("Generated datapack:") for event in events)


def test_layout_progress_event_and_config_callback() -> None:
    received: list[LayoutProgressEvent] = []
    event = LayoutProgressEvent(
        stage="candidate_generation",
        message="Generating candidates",
        current=1,
        total=2,
        key="note_candidates",
    )
    config = StereoLayoutConfig(progress_callback=received.append)

    assert config.progress_callback is not None
    config.progress_callback(event)

    assert received == [event]


def test_note_based_stereo_emits_candidate_and_assignment_progress() -> None:
    events: list[LayoutProgressEvent] = []
    layout = NoteBasedStereoLayout(
        config=StereoLayoutConfig(progress_callback=events.append)
    )

    layout.layout_song(_song())

    candidate_events = [event for event in events if event.key == "note_candidates"]
    assignment_events = [
        event for event in events if event.key == "pass1_assignment_validation"
    ]
    assert candidate_events[0].current == 0
    assert candidate_events[0].total == 1
    assert assignment_events[0].current == 0
    assert assignment_events[0].total == 1
    assert all(event.key != "rail_validation" for event in events)


def test_generate_from_config_can_return_diagnostics(
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
        lambda layout, writer_config, **kwargs: GeneratedBuildPlan(blocks=()),
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

    result = generate_from_config(config, include_diagnostics=True)

    assert result.diagnostics is not None
    assert result.diagnostics.song.name == "Generation Song"
    assert result.diagnostics.layout.mode == "test"
    assert result.diagnostics.write_result is not None


def test_generate_from_config_forwards_layout_progress(
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
            "layout_mode": "note_based_stereo",
            "tempo_control_mode": "none",
        }
    )
    events: list[GenerationEvent] = []

    monkeypatch.setattr("nbs2func.generation.read_nbs", lambda path: _song())

    def fake_build_layout_strategy(**kwargs):
        stereo_config = kwargs["stereo_config"]
        assert stereo_config.progress_callback is not None
        stereo_config.progress_callback(
            LayoutProgressEvent(
                stage="candidate_generation",
                message="Generating candidates",
                current=1000,
                total=13517,
                key="note_candidates",
                unit="emitters",
            )
        )
        return object()

    monkeypatch.setattr(
        "nbs2func.generation.build_layout_strategy",
        fake_build_layout_strategy,
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
        lambda layout, writer_config, **kwargs: GeneratedBuildPlan(blocks=()),
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

    generate_from_config(config, progress_callback=events.append)

    candidate_events = [
        event
        for event in events
        if event.kind == "progress" and event.key == "note_candidates"
    ]
    assert len(candidate_events) == 1
    assert candidate_events[0].message == "Generating candidates"
    assert candidate_events[0].detail == "candidate_generation"
    assert candidate_events[0].current == 1000
    assert candidate_events[0].total == 13517
    assert candidate_events[0].unit == "emitters"
    assert candidate_events[0].overall_percent is not None
    assert candidate_events[0].overall_percent >= 8.0


def test_block_builder_progress_callback_reaches_total() -> None:
    layout = _minimal_layout()
    events: list[tuple[int, int]] = []

    build_generated_plan(
        layout,
        CommandWriterConfig(split_functions=False),
        progress_callback=lambda current, total: events.append((current, total)),
    )

    assert events[0] == (0, 1)
    assert events[-1] == (1, 1)


def test_command_writer_progress_callback_reaches_total(tmp_path: Path) -> None:
    layout = _minimal_layout()
    events: list[tuple[int, int, str]] = []
    output_path = tmp_path / "song.mcfunction"

    BasicMcfunctionWriter(CommandWriterConfig(split_functions=False)).write_file(
        layout,
        output_path,
        progress_callback=lambda current, total, message: events.append(
            (current, total, message)
        ),
    )

    assert events[0] == (0, 1, "Writing datapack file")
    assert events[-1] == (1, 1, "Writing datapack file")


def test_generate_from_config_uses_datapack_name(
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
            "datapack_name": "Custom Pack",
            "layout_mode": "basic_linear",
            "tempo_control_mode": "none",
        }
    )

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
        lambda layout, writer_config, **kwargs: GeneratedBuildPlan(blocks=()),
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

    result = generate_from_config(config)

    assert result.datapack_path == tmp_path / "out" / "custom_pack"


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
        lambda layout, writer_config, **kwargs: GeneratedBuildPlan(blocks=()),
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
