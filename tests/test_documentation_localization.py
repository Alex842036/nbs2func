from __future__ import annotations

import json
import re
from pathlib import Path

from nbs2func import __version__


ROOT = Path(__file__).resolve().parents[1]

DOCUMENT_PAIRS = (
    (Path("README.md"), Path("README.zh-CN.md")),
    (Path("CHANGELOG.md"), Path("CHANGELOG.zh-CN.md")),
    (Path("docs/gui.md"), Path("docs/zh-CN/gui.md")),
    (Path("docs/modes.md"), Path("docs/zh-CN/modes.md")),
    (Path("docs/architecture.md"), Path("docs/zh-CN/architecture.md")),
    (Path("docs/known_issues.md"), Path("docs/zh-CN/known_issues.md")),
    (Path("examples/README.md"), Path("examples/README.zh-CN.md")),
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+]\(([^)]+)\)")


def _text(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _local_link_targets(path: Path) -> list[Path]:
    targets: list[Path] = []
    for raw_target in MARKDOWN_LINK.findall(_text(path)):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        targets.append((ROOT / path.parent / target).resolve())
    return targets


def test_all_public_documentation_has_english_and_chinese_files() -> None:
    for english, chinese in DOCUMENT_PAIRS:
        assert (ROOT / english).is_file(), english
        assert (ROOT / chinese).is_file(), chinese


def test_language_links_are_immediately_after_each_title_and_targets_exist() -> None:
    for english, chinese in DOCUMENT_PAIRS:
        for path in (english, chinese):
            lines = _text(path).splitlines()
            assert lines[0].startswith("# "), path
            assert lines[1] == "", path
            assert lines[2].startswith("[English]("), path
            assert " | [简体中文](" in lines[2], path
            for target in _local_link_targets(path):
                assert target.is_file(), f"{path}: {target}"


def test_release_version_is_consistent_in_code_and_current_documents() -> None:
    assert __version__ == "0.1.1"
    assert f"v{__version__}" in _text(Path("README.md"))
    assert f"v{__version__}" in _text(Path("README.zh-CN.md"))
    assert f"## {__version__}" in _text(Path("CHANGELOG.md"))
    assert f"## {__version__}" in _text(Path("CHANGELOG.zh-CN.md"))
    for path in (
        Path("docs/gui.md"),
        Path("docs/modes.md"),
        Path("docs/known_issues.md"),
        Path("docs/zh-CN/gui.md"),
        Path("docs/zh-CN/modes.md"),
        Path("docs/zh-CN/known_issues.md"),
    ):
        assert f"v{__version__}" in _text(path), path


def test_chinese_readme_links_to_all_chinese_public_guides() -> None:
    readme = _text(Path("README.zh-CN.md"))
    expected = (
        "docs/zh-CN/gui.md",
        "docs/zh-CN/modes.md",
        "docs/zh-CN/architecture.md",
        "docs/zh-CN/known_issues.md",
        "CHANGELOG.zh-CN.md",
        "examples/README.zh-CN.md",
        "LICENSE",
    )
    for target in expected:
        assert f"]({target})" in readme, target
        assert (ROOT / target).is_file(), target


def test_chinese_guides_preserve_english_section_coverage() -> None:
    for english, chinese in DOCUMENT_PAIRS:
        english_sections = [
            line for line in _text(english).splitlines() if line.startswith("## ")
        ]
        chinese_sections = [
            line for line in _text(chinese).splitlines() if line.startswith("## ")
        ]
        assert len(chinese_sections) == len(english_sections), (english, chinese)


def test_current_documentation_does_not_contain_stale_release_wording() -> None:
    current_docs = (
        Path("README.md"),
        Path("README.zh-CN.md"),
        Path("docs/gui.md"),
        Path("docs/modes.md"),
        Path("docs/architecture.md"),
        Path("docs/known_issues.md"),
        Path("docs/zh-CN/gui.md"),
        Path("docs/zh-CN/modes.md"),
        Path("docs/zh-CN/architecture.md"),
        Path("docs/zh-CN/known_issues.md"),
        Path("examples/README.md"),
        Path("examples/README.zh-CN.md"),
    )
    forbidden = (
        "0.1.0-gui-preview",
        "GUI is planned",
        "tempo adaptation is not implemented",
        "single-file",
        "requirements-dev.txt",
        'CPU-heavy Python work may cause brief Windows "Not Responding"',
    )
    for path in current_docs:
        text = _text(path)
        for phrase in forbidden:
            assert phrase not in text, f"{path}: {phrase}"


def test_chinese_guides_preserve_required_internal_identifiers() -> None:
    modes = _text(Path("docs/zh-CN/modes.md"))
    for value in (
        "basic_linear",
        "track_based_stereo",
        "note_based_stereo",
        "datapack",
        "schem",
        "both",
        "simple_chain",
        "player_tp",
        "--no-split-functions",
        "65535",
    ):
        assert f"`{value}`" in modes or value == "65535" and value in modes

    architecture = _text(Path("docs/zh-CN/architecture.md"))
    assert "GUI text -> Translator -> en.json / zh_CN.json" in architecture
    assert "~/.nbs2func/gui_settings.json" in architecture
    assert "generate_from_config()" in architecture


def test_chinese_document_terms_follow_the_gui_locale() -> None:
    locale = json.loads(
        (ROOT / "src/nbs2func/locales/zh_CN.json").read_text(encoding="utf-8")
    )
    readme = _text(Path("README.zh-CN.md"))
    gui = _text(Path("docs/zh-CN/gui.md"))
    modes = _text(Path("docs/zh-CN/modes.md"))
    for key in (
        "step.input.name",
        "step.layout.name",
        "step.layout_options.name",
        "step.modules.name",
        "step.output.name",
        "step.summary.name",
        "step.generate.name",
    ):
        assert locale[key] in readme, key
    for key in (
        "step.layout.mode.basic_linear",
        "step.layout.mode.track_based_stereo",
        "step.layout.mode.note_based_stereo",
        "step.output.format.datapack",
        "step.output.format.schem",
        "step.output.format.both",
        "step.output.build_style.simple_chain",
        "step.output.build_style.player_tp",
    ):
        assert locale[key] in gui or locale[key] in modes, key
