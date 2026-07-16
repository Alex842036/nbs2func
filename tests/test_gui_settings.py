from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nbs2func.config import config_to_dict, default_config
from nbs2func.generation import GenerationEvent, GenerationResult
from nbs2func.gui.i18n import Translator
from nbs2func.gui.settings import GuiSettings, load_gui_settings, save_gui_settings
from nbs2func.gui.state import create_default_state, update_config
from nbs2func.gui.wizard import (
    WizardApp,
    WizardNavigationState,
    restored_navigation_state,
)


def test_missing_settings_uses_system_locale(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    assert load_gui_settings(path, system_locale="zh-CN").language == "zh_CN"
    assert load_gui_settings(path, system_locale="en_US").language == "en"


def test_settings_round_trip_and_parent_creation(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "gui_settings.json"
    save_gui_settings(GuiSettings(language="zh_CN"), path)
    assert load_gui_settings(path).language == "zh_CN"


def test_corrupt_or_unknown_settings_fall_back_to_english(tmp_path: Path) -> None:
    path = tmp_path / "gui_settings.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_gui_settings(path, system_locale="zh_CN").language == "en"
    path.write_text('{"language": "xx"}', encoding="utf-8")
    assert load_gui_settings(path).language == "en"


def test_language_selection_does_not_change_project_config() -> None:
    config = default_config()
    before = config_to_dict(config)
    translator = Translator("en")
    translator.set_language("zh_CN")
    assert config_to_dict(config) == before


def test_restored_navigation_state_preserves_unlocks() -> None:
    restored = restored_navigation_state(
        WizardNavigationState(4, 4, False),
        step_count=7,
    )
    assert restored == WizardNavigationState(4, 4, False)

    generate_restored = restored_navigation_state(
        WizardNavigationState(6, 6, True),
        step_count=7,
    )
    assert generate_restored == WizardNavigationState(6, 6, True)


def test_invalid_current_draft_cancels_language_switch_without_destroying() -> None:
    state = create_default_state()
    original_origin_x = state.config.origin_x
    step = SimpleNamespace(draft="invalid", destroy=Mock())
    language_var = Mock()
    validation_languages: list[str] = []

    def reject_draft() -> bool:
        validation_languages.append(app.translator.language)
        update_config(state, origin_x=999)
        return False

    app = SimpleNamespace(
        generation_running=False,
        language_var=language_var,
        translator=Translator("en"),
        current_index=2,
        max_unlocked_index=4,
        generate_unlocked=False,
        state_data=state,
        leave_current_step=reject_draft,
        steps=[step],
        step_buttons=[],
    )

    WizardApp.set_language(app, "zh_CN")  # type: ignore[arg-type]

    assert app.translator.language == "en"
    assert state.config.origin_x == original_origin_x
    assert step.draft == "invalid"
    assert validation_languages == ["en"]
    step.destroy.assert_not_called()
    language_var.set.assert_called_once_with("en")


def test_valid_current_draft_survives_language_rebuild(tmp_path: Path) -> None:
    state = create_default_state()
    state.input_song_summary = {"name": "Draft song"}
    state.note_based_profile = "custom"
    state.datapack_name = "custom_pack"
    state.starter_origin_user_modified = True
    state.command_module_origin_user_modified = True
    state.datapack_name_user_modified = True
    state.schematic_name_user_modified = True
    state.config_path = "saved.json"
    state.generation_result = GenerationResult(output_format="datapack")
    state.generation_events.append(GenerationEvent("done", "done"))
    state.output_log.append("log")
    state_identity = id(state)
    old_step_objects = [SimpleNamespace(destroy=Mock()) for _ in range(7)]
    old_button_objects = [SimpleNamespace(destroy=Mock()) for _ in range(7)]
    display_step = Mock()

    def accept_draft() -> bool:
        update_config(state, origin_x=42)
        return True

    app = SimpleNamespace(
        generation_running=False,
        language_var=Mock(),
        translator=Translator("en"),
        current_index=4,
        max_unlocked_index=4,
        generate_unlocked=True,
        state_data=state,
        leave_current_step=accept_draft,
        gui_settings_path=tmp_path / "gui_settings.json",
        steps=list(old_step_objects),
        step_buttons=list(old_button_objects),
        title=Mock(),
        back_button=SimpleNamespace(configure=Mock()),
        _build_menu=Mock(),
        _display_step=display_step,
    )
    app.tr = lambda key, **params: app.translator.gettext(key, **params)

    def load_steps() -> None:
        app.steps.extend(SimpleNamespace(destroy=Mock()) for _ in range(7))

    app._load_steps = load_steps

    with patch("nbs2func.gui.wizard.save_gui_settings"):
        WizardApp.set_language(app, "zh_CN")  # type: ignore[arg-type]

    assert id(app.state_data) == state_identity
    assert state.config.origin_x == 42
    assert app.translator.language == "zh_CN"
    assert app.current_index == 4
    assert app.max_unlocked_index == 4
    assert app.generate_unlocked is True
    assert state.input_song_summary == {"name": "Draft song"}
    assert state.note_based_profile == "custom"
    assert state.datapack_name == "custom_pack"
    assert state.starter_origin_user_modified is True
    assert state.command_module_origin_user_modified is True
    assert state.datapack_name_user_modified is True
    assert state.schematic_name_user_modified is True
    assert state.config_path == "saved.json"
    assert state.generation_result == GenerationResult(output_format="datapack")
    assert state.generation_events == [GenerationEvent("done", "done")]
    assert state.output_log == ["log"]
    display_step.assert_called_once_with(4)
    assert all(step.destroy.call_count == 1 for step in old_step_objects)
    assert all(button.destroy.call_count == 1 for button in old_button_objects)


def test_language_menu_is_disabled_while_generation_runs() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")
    assert 'state = "disabled" if self.generation_running else "normal"' in source
    assert "self.language_menu.entryconfigure(index, state=state)" in source
