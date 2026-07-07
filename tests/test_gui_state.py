import json
from pathlib import Path

from nbs2func.config import config_to_dict, load_config, save_config
from nbs2func.gui.helpers import (
    GUI_MINECRAFT_VERSION_CHOICES,
    direction_display_to_value,
    direction_value_to_display,
    infer_note_profile,
    is_output_format_selectable,
)
from nbs2func.gui.state import (
    create_default_state,
    load_input_song,
    set_layout_mode,
    set_output_format,
    update_config,
    validate_ready_to_generate,
)


def test_gui_state_can_be_created_from_default_config() -> None:
    state = create_default_state()

    assert state.config.input_path == "examples/demo.nbs"
    assert state.config.layout_mode == "note_based_stereo"
    assert state.config.output_format == "datapack"
    assert state.input_song_summary is None


def test_gui_state_writes_layout_mode_to_config() -> None:
    state = create_default_state()

    set_layout_mode(state, "basic_linear")

    assert state.config.layout_mode == "basic_linear"


def test_gui_state_writes_output_format_to_config() -> None:
    state = create_default_state()
    update_config(
        state,
        enable_starter_module=True,
        enable_playback_assist=True,
    )

    set_output_format(state, "schem")

    assert state.config.output_format == "schem"
    assert state.config.enable_starter_module is True
    assert state.config.enable_playback_assist is True


def test_gui_version_choices_only_include_exact_supported_versions() -> None:
    assert GUI_MINECRAFT_VERSION_CHOICES == (
        "1.14.4",
        "1.16.5",
        "1.18.2",
        "1.20.1",
        "1.21.1",
    )
    assert "1.16.x" not in GUI_MINECRAFT_VERSION_CHOICES
    assert "1.20" not in GUI_MINECRAFT_VERSION_CHOICES


def test_gui_direction_display_values_map_to_canonical_config_values() -> None:
    assert direction_display_to_value("east (+x)") == "east"
    assert direction_display_to_value("west (-x)") == "west"
    assert direction_display_to_value("south (+z)") == "south"
    assert direction_display_to_value("north (-z)") == "north"
    assert direction_value_to_display("east") == "east (+x)"


def test_gui_schem_only_is_not_selectable_when_runtime_modules_enabled() -> None:
    state = create_default_state()
    update_config(state, enable_starter_module=True)

    assert is_output_format_selectable(state.config, "datapack") is True
    assert is_output_format_selectable(state.config, "both") is True
    assert is_output_format_selectable(state.config, "schem") is False


def test_gui_schem_only_is_selectable_without_runtime_modules() -> None:
    state = create_default_state()

    assert is_output_format_selectable(state.config, "schem") is True


def test_gui_note_profile_infers_preset_and_preserves_custom() -> None:
    state = create_default_state()

    assert infer_note_profile(state.config, "balanced") == "balanced"

    update_config(state, max_candidates_per_emitter=99)
    assert infer_note_profile(state.config, "balanced") == "custom"
    assert infer_note_profile(state.config, "custom") == "custom"


def test_gui_state_config_round_trip_still_uses_project_config(tmp_path: Path) -> None:
    state = create_default_state()
    set_layout_mode(state, "track_based_stereo")
    set_output_format(state, "both")
    path = tmp_path / "gui-config.json"

    save_config(state.config, path)
    loaded = load_config(path)

    assert loaded == state.config
    assert json.loads(path.read_text(encoding="utf-8")) == config_to_dict(state.config)


def test_gui_input_song_summary_loads_demo() -> None:
    state = create_default_state()

    summary = load_input_song(state, "examples/demo.nbs")

    assert Path(state.config.input_path) == Path("examples/demo.nbs")
    assert Path(str(summary["path"])) == Path("examples/demo.nbs")
    assert isinstance(summary["note_count"], int)
    assert isinstance(summary["layer_count"], int)


def test_gui_generation_validation_checks_input_path() -> None:
    state = create_default_state()
    update_config(state, input_path="missing-file.nbs")

    errors = validate_ready_to_generate(state)

    assert "Select a valid .nbs input file." in errors
