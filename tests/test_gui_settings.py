from __future__ import annotations

from pathlib import Path

from nbs2func.config import config_to_dict, default_config
from nbs2func.gui.i18n import Translator
from nbs2func.gui.settings import GuiSettings, load_gui_settings, save_gui_settings


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


def test_wizard_language_switch_preserves_state_and_current_step() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")
    method = source.split("    def set_language", 1)[1].split(
        "    def _build_shell", 1
    )[0]
    assert "current_index = self.current_index" in method
    assert "self._display_step(self.current_index)" in method
    assert "create_default_state" not in method
    assert "load_input_song" not in method
    assert "if self.generation_running:" in method
    assert "save_gui_settings" in method


def test_language_menu_is_disabled_while_generation_runs() -> None:
    source = Path("src/nbs2func/gui/wizard.py").read_text(encoding="utf-8")
    assert 'state = "disabled" if self.generation_running else "normal"' in source
    assert "self.language_menu.entryconfigure(index, state=state)" in source
