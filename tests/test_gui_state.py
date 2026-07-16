import json
from pathlib import Path
from unittest.mock import patch

from nbs2func import __version__
from nbs2func.config import config_to_dict, load_config, save_config
from nbs2func.generation import GenerationEvent
from nbs2func.gui.helpers import (
    GUI_MINECRAFT_VERSION_CHOICES,
    TRACK_BASED_GUI_FIELDS,
    absolute_path,
    apply_track_based_gui_defaults,
    datapack_group_enabled,
    default_datapack_folder_name,
    default_schematic_name,
    direction_display_to_value,
    direction_value_to_display,
    infer_note_profile,
    is_output_format_selectable,
    parse_float,
    parse_int,
    resolve_gui_generation_config,
    resolved_command_module_origin,
    resolved_starter_origin,
    resolved_vehicle_spawn_position,
    validate_layout_options,
    validate_module_coordinates,
)
from nbs2func.gui.steps.input_step import input_path_needs_reload
from nbs2func.gui.steps.modules_step import (
    module_int_fields_to_parse,
    normalize_module_toggles,
)
from nbs2func.gui.steps.output_step import (
    DATAPACK_BUILD_STYLE_CHOICES,
    output_datapack_controls_enabled,
)
from nbs2func.gui.steps.generate_step import (
    format_overall_progress,
    format_generation_event,
    format_progress_event,
    should_continue_polling,
)
from nbs2func.gui.state import (
    create_state_from_config,
    create_default_state,
    load_input_song,
    set_layout_mode,
    set_output_format,
    update_config,
    validate_ready_to_generate,
)
from nbs2func.gui.wizard import WizardApp


def test_gui_state_can_be_created_from_default_config() -> None:
    state = create_default_state()

    assert Path(state.config.input_path).is_absolute()
    assert Path(state.config.input_path).name == "demo.nbs"
    assert Path(state.config.output).is_absolute()
    assert Path(str(state.config.schematic_output)).is_absolute()
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

    assert Path(state.config.input_path) == absolute_path("examples/demo.nbs")
    assert Path(str(summary["path"])) == absolute_path("examples/demo.nbs")
    assert isinstance(summary["note_count"], int)
    assert isinstance(summary["layer_count"], int)


def test_input_path_mismatch_requires_reload_after_successful_load() -> None:
    state = create_default_state()
    summary = load_input_song(state, "examples/demo.nbs")

    assert input_path_needs_reload(str(summary["path"]), summary) is False
    assert input_path_needs_reload("missing-file.nbs", summary) is True
    assert input_path_needs_reload("", summary) is True


def test_gui_generation_validation_checks_input_path() -> None:
    state = create_default_state()
    update_config(state, input_path="missing-file.nbs")

    errors = validate_ready_to_generate(state)

    assert "Select a valid .nbs input file." in errors


def test_gui_ready_validation_checks_function_resource_paths() -> None:
    state = create_default_state()
    update_config(state, function_namespace="My Namespace")

    assert any("function_namespace" in error for error in validate_ready_to_generate(state))

    state = create_default_state()
    update_config(state, build_function_dir="Build Dir")

    assert any("build_function_dir" in error for error in validate_ready_to_generate(state))


def test_origin_y_validation_uses_version_height_and_note_block_range() -> None:
    cases = (
        ("1.16.5", 48, False),
        ("1.16.5", 207, False),
        ("1.16.5", 47, True),
        ("1.16.5", 208, True),
        ("1.20.1", -16, False),
        ("1.20.1", 271, False),
        ("1.20.1", -17, True),
        ("1.20.1", 272, True),
    )
    for version, origin_y, should_error in cases:
        state = create_default_state()
        update_config(state, minecraft_version=version, origin_y=origin_y)

        errors = validate_layout_options(state.config)

        assert bool(errors) is should_error


def test_gui_numeric_parsers_reject_non_finite_and_invalid_ranges() -> None:
    for value in ("nan", "inf", "-inf"):
        try:
            parse_float(value, "Min distance", min_value=0)
        except ValueError as exc:
            assert "finite" in str(exc)
        else:
            raise AssertionError(f"{value!r} should be invalid")

    try:
        parse_float("-1", "Min distance", min_value=0)
    except ValueError as exc:
        assert "at least 0" in str(exc)
    else:
        raise AssertionError("negative min_distance should be invalid")

    assert parse_float("0", "Min distance", min_value=0) == 0

    try:
        parse_int("0", "Max commands per function", min_value=1)
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("zero max commands should be invalid")

    assert parse_int("10000", "Max commands per function", min_value=1) == 10000


def test_track_based_gui_fixed_options_are_not_exposed_and_are_resolved() -> None:
    state = create_default_state()
    update_config(
        state,
        layout_mode="track_based_stereo",
        max_hearing_distance=12,
        max_stereo_angle_degrees=45,
        center_split_policy="none",
        enable_collision_resolver=False,
    )

    resolved = apply_track_based_gui_defaults(state.config)

    assert "max_hearing_distance" not in TRACK_BASED_GUI_FIELDS
    assert "max_stereo_angle_degrees" not in TRACK_BASED_GUI_FIELDS
    assert "center_split_mode" not in TRACK_BASED_GUI_FIELDS
    assert "center_split_policy" not in TRACK_BASED_GUI_FIELDS
    assert "enable_collision_resolver" not in TRACK_BASED_GUI_FIELDS
    assert resolved.max_hearing_distance == 48
    assert resolved.max_stereo_angle_degrees == 90
    assert resolved.enable_collision_resolver is True
    assert resolved.center_split_policy == "auto_on_collision"
    assert resolved.center_split_mode == "duplicate_half_volume"


def _configured_for_starter(direction: str, starter_x: int, starter_z: int):
    state = create_default_state()
    update_config(
        state,
        enable_starter_module=True,
        direction=direction,
        origin_x=0,
        origin_y=128,
        origin_z=0,
        command_block_x=starter_x,
        command_block_y=128,
        command_block_z=starter_z,
    )
    return state.config


def test_starter_origin_direction_validation() -> None:
    assert validate_module_coordinates(_configured_for_starter("east", -10, 0)) == []
    assert validate_module_coordinates(_configured_for_starter("east", 10, 0))
    assert validate_module_coordinates(_configured_for_starter("west", 10, 0)) == []
    assert validate_module_coordinates(_configured_for_starter("west", -10, 0))
    assert validate_module_coordinates(_configured_for_starter("south", 0, -10)) == []
    assert validate_module_coordinates(_configured_for_starter("south", 0, 10))
    assert validate_module_coordinates(_configured_for_starter("north", 0, 10)) == []
    assert validate_module_coordinates(_configured_for_starter("north", 0, -10))


def _configured_for_command_module(
    direction: str,
    command_x: int,
    command_z: int,
):
    state = create_default_state()
    update_config(
        state,
        enable_starter_module=True,
        enable_playback_assist=True,
        direction=direction,
        origin_x=0,
        origin_y=128,
        origin_z=0,
        command_block_x=-10 if direction == "east" else 10 if direction == "west" else 0,
        command_block_y=128,
        command_block_z=-10 if direction == "south" else 10 if direction == "north" else 0,
        command_module_origin_x=command_x,
        command_module_origin_y=128,
        command_module_origin_z=command_z,
    )
    return state.config


def test_command_module_origin_direction_validation() -> None:
    assert validate_module_coordinates(_configured_for_command_module("east", -11, 0)) == []
    assert validate_module_coordinates(_configured_for_command_module("east", -10, 0))
    assert validate_module_coordinates(_configured_for_command_module("west", 11, 0)) == []
    assert validate_module_coordinates(_configured_for_command_module("west", 10, 0))
    assert validate_module_coordinates(_configured_for_command_module("south", 0, -11)) == []
    assert validate_module_coordinates(_configured_for_command_module("south", 0, -10))
    assert validate_module_coordinates(_configured_for_command_module("north", 0, 11)) == []
    assert validate_module_coordinates(_configured_for_command_module("north", 0, 10))


def test_gui_generation_resolution_binds_music_start_to_layout_origin() -> None:
    state = create_default_state()
    update_config(
        state,
        enable_playback_assist=True,
        origin_x=4,
        origin_y=70,
        origin_z=8,
        music_start_x=999,
        music_start_y=999,
        music_start_z=999,
    )

    resolved = resolve_gui_generation_config(state.config)

    assert (resolved.music_start_x, resolved.music_start_y, resolved.music_start_z) == (
        4,
        70,
        8,
    )


def test_gui_generation_resolution_derives_playback_positions_from_starter() -> None:
    state = create_default_state()
    update_config(
        state,
        enable_starter_module=True,
        enable_playback_assist=True,
        direction="east",
        origin_x=0,
        origin_y=128,
        origin_z=0,
        command_block_x=-10,
        command_block_y=128,
        command_block_z=0,
        command_module_origin_x=None,
        command_module_origin_y=None,
        command_module_origin_z=None,
        vehicle_spawn_x=None,
        vehicle_spawn_y=None,
        vehicle_spawn_z=None,
    )

    resolved = resolve_gui_generation_config(state.config)

    assert (
        resolved.command_module_origin_x,
        resolved.command_module_origin_y,
        resolved.command_module_origin_z,
    ) == (-15, 128, 0)
    assert (
        resolved.vehicle_spawn_x,
        resolved.vehicle_spawn_y,
        resolved.vehicle_spawn_z,
    ) == (-11, 128, 0)


def test_vehicle_spawn_for_playback_assist_uses_starter_origin_by_direction() -> None:
    cases = {
        "east": ((-10, 128, 0), (-11, 128, 0)),
        "west": ((10, 128, 0), (11, 128, 0)),
        "south": ((0, 128, -10), (0, 128, -11)),
        "north": ((0, 128, 10), (0, 128, 11)),
    }
    for direction, (starter, expected) in cases.items():
        state = create_default_state()
        update_config(
            state,
            enable_starter_module=True,
            enable_playback_assist=True,
            direction=direction,
            command_block_x=starter[0],
            command_block_y=starter[1],
            command_block_z=starter[2],
            vehicle_spawn_x=999,
            vehicle_spawn_y=999,
            vehicle_spawn_z=999,
        )

        assert resolved_vehicle_spawn_position(state.config) == expected


def test_disabled_module_fields_are_not_parsed_when_modules_are_off() -> None:
    assert module_int_fields_to_parse(
        enable_starter_module=False,
        enable_playback_assist=False,
    ) == {"tempo_rate_decimals"}
    assert "command_module_origin_x" not in module_int_fields_to_parse(
        enable_starter_module=True,
        enable_playback_assist=False,
    )


def test_playback_assist_toggle_depends_on_starter_module() -> None:
    assert normalize_module_toggles(False, True) == (False, False)
    assert normalize_module_toggles(True, True) == (True, True)
    assert normalize_module_toggles(True, False) == (True, False)


def test_starter_origin_defaults_follow_direction() -> None:
    cases = {
        "east": (-10, 128, 0),
        "west": (10, 128, 0),
        "south": (0, 128, -10),
        "north": (0, 128, 10),
    }
    for direction, expected in cases.items():
        state = create_default_state()
        update_config(state, direction=direction, origin_x=0, origin_y=128, origin_z=0)

        assert resolved_starter_origin(state.config) == expected


def test_command_module_origin_defaults_follow_starter_and_direction() -> None:
    cases = {
        "east": ((-10, 128, 0), (-15, 128, 0)),
        "west": ((10, 128, 0), (15, 128, 0)),
        "south": ((0, 128, -10), (0, 128, -15)),
        "north": ((0, 128, 10), (0, 128, 15)),
    }
    for direction, (starter, expected) in cases.items():
        state = create_default_state()
        update_config(
            state,
            direction=direction,
            command_block_x=starter[0],
            command_block_y=starter[1],
            command_block_z=starter[2],
            command_module_origin_x=None,
            command_module_origin_y=None,
            command_module_origin_z=None,
        )

        assert resolved_command_module_origin(state.config) == expected


def test_gui_generation_resolution_keeps_game_ticks_per_song_tick_fixed() -> None:
    state = create_default_state()
    update_config(state, game_ticks_per_song_tick=9)

    resolved = resolve_gui_generation_config(state.config)

    assert resolved.game_ticks_per_song_tick == 4


def test_datapack_group_enabled_by_output_format() -> None:
    assert datapack_group_enabled("datapack") is True
    assert datapack_group_enabled("both") is True
    assert datapack_group_enabled("schem") is False


def test_output_datapack_build_style_controls_follow_output_format() -> None:
    assert output_datapack_controls_enabled("datapack") is True
    assert output_datapack_controls_enabled("both") is True
    assert output_datapack_controls_enabled("schem") is False
    assert DATAPACK_BUILD_STYLE_CHOICES == ("simple_chain", "player_tp")


def test_datapack_name_default_and_manual_state() -> None:
    state = create_default_state()

    assert state.datapack_name == "demo"
    state.datapack_name = "custom_pack"
    state.datapack_name_user_modified = True

    assert state.datapack_name == "custom_pack"


def test_create_state_from_loaded_config_resets_gui_only_flags() -> None:
    old = create_default_state()
    old.starter_origin_user_modified = True
    old.command_module_origin_user_modified = True
    old.datapack_name_user_modified = True
    old.schematic_name_user_modified = True
    update_config(old, datapack_name="Loaded Pack")

    loaded = create_state_from_config(old.config, config_path="loaded.json")

    assert loaded.config_path == "loaded.json"
    assert loaded.datapack_name == "Loaded Pack"
    assert loaded.input_song_summary is None
    assert loaded.starter_origin_user_modified is False
    assert loaded.command_module_origin_user_modified is False
    assert loaded.datapack_name_user_modified is False
    assert loaded.schematic_name_user_modified is False


def test_gui_path_normalization_and_default_file_names() -> None:
    state = create_default_state()

    assert absolute_path("examples/demo.nbs") == Path(state.config.input_path)
    assert absolute_path("output") == Path(state.config.output)
    assert Path(str(state.config.schematic_output)).is_absolute()
    assert default_schematic_name(state.config) == "demo"
    assert default_datapack_folder_name(state.config) == "demo"


def test_generate_step_formats_generation_events() -> None:
    assert (
        format_generation_event(GenerationEvent("phase", "Reading NBS"))
        == "[Phase] Reading NBS"
    )
    assert (
        format_generation_event(GenerationEvent("warning", "Careful"))
        == "[Warning] Careful"
    )
    assert (
        format_generation_event(GenerationEvent("output", "Generated schematic: x"))
        == "[Output] Generated schematic: x"
    )
    assert (
        format_generation_event(GenerationEvent("done", "Generation finished."))
        == "[Done] Generation finished."
    )


def test_generate_step_formats_progress_events() -> None:
    assert (
        format_progress_event(
            GenerationEvent(
                "progress",
                "Generating candidates",
                current=1000,
                total=13517,
                unit="notes",
                key="note_candidates",
            )
        )
        == "Generating candidates: 1000 / 13517 notes"
    )
    assert (
        format_progress_event(
            GenerationEvent(
                "progress",
                "Validating rails: candidates=12000 rails_checked=340000",
                key="rail_validation",
            )
        )
        == "Validating rails: candidates=12000 rails_checked=340000"
    )
    assert (
        format_progress_event(
            GenerationEvent(
                "progress",
                "Pass3 assignment / rail validation",
                current=0,
                total=0,
            )
        )
        == "Skipped: Pass3 assignment / rail validation"
    )
    assert format_overall_progress(62.4) == "Overall progress: 62%"


def test_generate_step_polling_continues_until_thread_done_and_queue_empty() -> None:
    assert should_continue_polling(thread_alive=False, queue_empty=False) is True
    assert should_continue_polling(thread_alive=False, queue_empty=True) is False
    assert should_continue_polling(thread_alive=True, queue_empty=True) is True


def test_generate_step_no_longer_uses_subprocess_cli_stdout() -> None:
    source = Path("src/nbs2func/gui/steps/generate_step.py").read_text(
        encoding="utf-8"
    )

    assert "subprocess.Popen" not in source
    assert "main.py" not in source
    assert "--config" not in source
    assert "include_diagnostics=False" in source
    assert "event.kind == \"progress\"" in source
    assert 'self.app.tr("step.generate.finished_stage")' in source


def test_wizard_save_config_applies_current_step_before_writing() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")

    assert "if not self.leave_current_step():" in source


def test_output_step_writes_datapack_name_to_config() -> None:
    source = Path("src/nbs2func/gui/steps/output_step.py").read_text(
        encoding="utf-8"
    )

    assert 'updates["datapack_name"] = self.state.datapack_name' in source


def test_output_step_writes_build_style_and_hides_internal_player_tp_fields() -> None:
    source = Path("src/nbs2func/gui/steps/output_step.py").read_text(
        encoding="utf-8"
    )
    on_change_source = source.split("def _on_format_change", 1)[1].split(
        "def _build_form",
        1,
    )[0]

    assert 'updates["datapack_build_style"] = self.build_style_var.get()' in source
    assert "max_commands_per_build_part" not in source
    assert "player_tp_window_length_blocks" not in source
    assert "player_tp_window_lateral_width_blocks" not in source
    assert "self.app.refresh()" not in on_change_source
    assert "self.app._refresh_buttons()" in on_change_source


class _CloseAppStub:
    def __init__(self, generation_running: bool) -> None:
        self.generation_running = generation_running
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


def test_wizard_close_handler_confirms_only_while_generation_is_running() -> None:
    idle = _CloseAppStub(generation_running=False)
    with patch("nbs2func.gui.wizard.messagebox.askyesno") as confirm:
        WizardApp.request_close(idle)  # type: ignore[arg-type]
    assert idle.destroyed is True
    confirm.assert_not_called()

    running = _CloseAppStub(generation_running=True)
    with patch("nbs2func.gui.wizard.messagebox.askyesno", return_value=False):
        WizardApp.request_close(running)  # type: ignore[arg-type]
    assert running.destroyed is False

    with patch("nbs2func.gui.wizard.messagebox.askyesno", return_value=True):
        WizardApp.request_close(running)  # type: ignore[arg-type]
    assert running.destroyed is True


def test_wizard_exit_routes_use_one_close_handler() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")

    assert 'self.protocol("WM_DELETE_WINDOW", self.request_close)' in source
    assert 'label=self.tr("menu.file.exit"), command=self.request_close' in source


def test_summary_and_generate_navigation_buttons_are_not_duplicated() -> None:
    summary_source = Path("src/nbs2func/gui/steps/summary_step.py").read_text(
        encoding="utf-8"
    )
    wizard_source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")

    assert 'text=self.app.tr("common.save_config")' in summary_source
    assert 'common.generate' not in summary_source
    assert 'text=self.tr("common.generate"), command=self.go_generate' in wizard_source
    assert 'text=self.tr("common.finish")' in wizard_source
    assert "command=self.request_close" in wizard_source
    assert "Back to Summary" not in wizard_source
    assert "def back_to_summary" not in wizard_source
    assert "self.show_step(self.current_index - 1)" in wizard_source


def test_generate_navigation_buttons_follow_generation_running_state() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")

    assert "self.current_index > 0 and not self.generation_running" in source
    assert "current.is_complete() and not self.generation_running" in source


def test_existing_datapack_confirmation_follows_output_format(tmp_path: Path) -> None:
    state = create_default_state()
    target = tmp_path / "out" / "Preview Pack"
    target.mkdir(parents=True)
    update_config(
        state,
        output=str(tmp_path / "out"),
        datapack_name="Preview Pack",
        output_format="datapack",
    )
    app = type("AppStub", (), {"state_data": state})()

    with patch("nbs2func.gui.wizard.messagebox.askyesno", return_value=False) as confirm:
        assert WizardApp._confirm_datapack_overwrite(app) is False  # type: ignore[arg-type]
    confirm.assert_called_once()

    update_config(state, output_format="both")
    with patch("nbs2func.gui.wizard.messagebox.askyesno", return_value=True) as confirm:
        assert WizardApp._confirm_datapack_overwrite(app) is True  # type: ignore[arg-type]
    confirm.assert_called_once()

    update_config(state, output_format="schem")
    with patch("nbs2func.gui.wizard.messagebox.askyesno") as confirm:
        assert WizardApp._confirm_datapack_overwrite(app) is True  # type: ignore[arg-type]
    confirm.assert_not_called()

    target.rmdir()
    update_config(state, output_format="datapack")
    with patch("nbs2func.gui.wizard.messagebox.askyesno") as confirm:
        assert WizardApp._confirm_datapack_overwrite(app) is True  # type: ignore[arg-type]
    confirm.assert_not_called()


def test_gui_preview_version_and_windows_launchers_are_consistent() -> None:
    assert __version__ == "0.1.0-gui-preview"
    wizard_source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")
    assert "from nbs2func import __version__" in wizard_source
    assert "v0.1.0-" + "preview" not in wizard_source

    run_gui = Path("run_gui.bat").read_text(encoding="utf-8")
    install = Path("install_requirements.bat").read_text(encoding="utf-8")
    assert "cd /d \"%~dp0\"" in run_gui
    assert 'set "PYTHONPATH=%CD%\\src"' in run_gui
    assert "-m nbs2func.gui.app" in run_gui
    assert "requirements.txt" in install


def test_requirements_use_one_file_without_dev_file_reference() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "mcschematic" in requirements
    assert "pytest" in requirements
    assert "requirements" + "-dev.txt" not in requirements
