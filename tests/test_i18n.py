from __future__ import annotations

import json
from importlib.resources import files
from string import Formatter

from nbs2func.generation import GenerationEvent
from nbs2func.cli import _print_generation_event
from nbs2func.gui.i18n import Translator
from nbs2func.gui.steps.generate_step import (
    format_generation_event,
    format_progress_event,
)


def _catalog(language: str) -> dict[str, str]:
    return json.loads(
        files("nbs2func")
        .joinpath("locales", f"{language}.json")
        .read_text(encoding="utf-8")
    )


def test_locale_key_parity_and_string_values() -> None:
    english = _catalog("en")
    chinese = _catalog("zh_CN")
    assert english.keys() == chinese.keys()
    assert all(isinstance(value, str) for value in english.values())
    assert all(isinstance(value, str) for value in chinese.values())
    for key in english:
        english_fields = {
            field for _, field, _, _ in Formatter().parse(english[key]) if field
        }
        chinese_fields = {
            field for _, field, _, _ in Formatter().parse(chinese[key]) if field
        }
        assert english_fields == chinese_fields, key


def test_translator_language_and_fallbacks(monkeypatch) -> None:
    translator = Translator("zh_CN")
    assert translator.gettext("common.next") == "下一步"
    monkeypatch.delitem(Translator._catalogs["zh_CN"], "common.next")
    assert translator.gettext("common.next") == "Next"
    translator.set_language("not-a-locale")
    assert translator.language == "en"
    assert translator.gettext("common.next") == "Next"
    assert translator.gettext("not.present") == "[missing:not.present]"


def test_translator_formats_parameters_without_crashing() -> None:
    translator = Translator("zh_CN")
    assert translator.gettext("validation.integer_required", field="原点 X") == (
        "原点 X 必须是整数。"
    )
    assert translator.gettext("validation.integer_required") == (
        "[format-error:validation.integer_required]"
    )


def test_event_message_uses_translation_or_english_message_fallback() -> None:
    translator = Translator("zh_CN")
    assert translator.event_message(
        "Generated datapack: out", "output.datapack", {"path": "out"}
    ) == "已生成数据包（datapack）：out"
    assert translator.event_message("raw", "not.present") == "raw"
    assert translator.event_message("raw", "validation.integer_required") == "raw"


def test_all_generation_units_have_english_and_chinese_translations() -> None:
    for language in ("en", "zh_CN"):
        translator = Translator(language)
        for unit in (
            "notes", "emitters", "ticks", "cells", "blocks",
            "files", "parts", "windows", "commands",
        ):
            assert translator.has_key(f"unit.{unit}")
            assert not translator.gettext(f"unit.{unit}").startswith("[")


def test_all_wizard_steps_have_bilingual_names() -> None:
    for language in ("en", "zh_CN"):
        translator = Translator(language)
        for step in (
            "input", "layout", "layout_options", "modules",
            "output", "summary", "generate",
        ):
            assert translator.has_key(f"step.{step}.name")


def test_generation_event_gui_localizes_but_message_stays_english() -> None:
    event = GenerationEvent(
        "progress",
        "Generating candidates",
        current=1000,
        total=13517,
        unit="emitters",
        i18n_key="generation.progress.candidate_generation",
    )
    chinese = Translator("zh_CN")
    assert format_progress_event(event, chinese) == (
        "生成候选位置：1000 / 13517 个发声单元"
    )
    assert event.message == "Generating candidates"

    output = GenerationEvent(
        "output",
        "Generated datapack: out",
        i18n_key="output.datapack",
        i18n_params={"path": "out"},
    )
    assert format_generation_event(output, chinese) == (
        "[输出] 已生成数据包（datapack）：out"
    )


def test_generation_event_missing_translation_uses_english_message() -> None:
    event = GenerationEvent(
        "notice",
        "English diagnostic",
        i18n_key="generation.notice.not_present",
    )
    assert "English diagnostic" in format_generation_event(event, Translator("zh_CN"))


def test_cli_generation_formatter_keeps_english_message(capsys) -> None:
    event = GenerationEvent(
        "notice",
        "Generated datapack: out",
        i18n_key="output.datapack",
        i18n_params={"path": "out"},
    )
    _print_generation_event(event)
    assert capsys.readouterr().out == "NOTICE: Generated datapack: out\n"
