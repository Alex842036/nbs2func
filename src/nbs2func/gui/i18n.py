from __future__ import annotations

import json
from importlib.resources import files
from threading import RLock
from typing import Mapping


SUPPORTED_LANGUAGES = ("en", "zh_CN")


class Translator:
    """Small, dependency-free translator for GUI resources."""

    _catalogs: dict[str, dict[str, str]] = {}
    _lock = RLock()

    def __init__(self, language: str = "en") -> None:
        self._ensure_catalogs()
        self._language = self.normalize_language(language)

    @staticmethod
    def normalize_language(language: str) -> str:
        return language if language in SUPPORTED_LANGUAGES else "en"

    @classmethod
    def _ensure_catalogs(cls) -> None:
        if cls._catalogs:
            return
        with cls._lock:
            if cls._catalogs:
                return
            loaded: dict[str, dict[str, str]] = {}
            locale_root = files("nbs2func").joinpath("locales")
            for language in SUPPORTED_LANGUAGES:
                raw = json.loads(
                    locale_root.joinpath(f"{language}.json").read_text(encoding="utf-8")
                )
                if not isinstance(raw, dict) or not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in raw.items()
                ):
                    raise ValueError(f"Invalid locale resource: {language}.json")
                loaded[language] = raw
            cls._catalogs = loaded

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        self._language = self.normalize_language(language)

    def has_key(self, key: str) -> bool:
        return key in self._catalogs[self._language] or key in self._catalogs["en"]

    def try_gettext(self, key: str, **params: object) -> str | None:
        template = self._catalogs[self._language].get(key)
        if template is None:
            template = self._catalogs["en"].get(key)
        if template is None:
            return None
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError, AttributeError):
            return None

    def gettext(self, key: str, **params: object) -> str:
        text = self.try_gettext(key, **params)
        if text is not None:
            return text
        if self.has_key(key):
            return f"[format-error:{key}]"
        return f"[missing:{key}]"

    def tr(self, key: str, **params: object) -> str:
        return self.gettext(key, **params)

    def event_message(
        self,
        message: str,
        i18n_key: str | None,
        i18n_params: Mapping[str, object] | None = None,
    ) -> str:
        if i18n_key is None:
            return message
        return self.try_gettext(i18n_key, **dict(i18n_params or {})) or message
