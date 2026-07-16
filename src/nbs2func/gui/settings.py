from __future__ import annotations

import json
import locale
from dataclasses import asdict, dataclass
from pathlib import Path

from nbs2func.gui.i18n import Translator


@dataclass
class GuiSettings:
    language: str = "en"

    def __post_init__(self) -> None:
        self.language = Translator.normalize_language(self.language)


def settings_path() -> Path:
    return Path.home() / ".nbs2func" / "gui_settings.json"


def system_default_language(system_locale: str | None = None) -> str:
    if system_locale is None:
        try:
            system_locale = locale.getlocale()[0]
        except (ValueError, TypeError):
            system_locale = None
    normalized = (system_locale or "").replace("-", "_").lower()
    return "zh_CN" if normalized.startswith("zh") else "en"


def load_gui_settings(
    path: str | Path | None = None,
    *,
    system_locale: str | None = None,
) -> GuiSettings:
    target = Path(path) if path is not None else settings_path()
    try:
        if not target.exists():
            return GuiSettings(language=system_default_language(system_locale))
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("GUI settings must be a JSON object")
        return GuiSettings(language=str(raw.get("language", "en")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return GuiSettings(language="en")


def save_gui_settings(
    settings: GuiSettings,
    path: str | Path | None = None,
) -> None:
    target = Path(path) if path is not None else settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = GuiSettings(language=settings.language)
    target.write_text(
        json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
