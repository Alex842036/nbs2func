# Changelog

[English](CHANGELOG.md) | [简体中文](CHANGELOG.zh-CN.md)

## 0.1.1

### Added

- Complete Simplified Chinese localization for the seven-step wizard GUI.
- Persistent English/Simplified Chinese language selection with system-language
  detection on first launch and English fallback.
- Parallel English and Simplified Chinese public documentation, including the
  README, changelog, GUI guide, generation modes, architecture, known issues,
  and examples guide.
- Documentation localization tests for paired files, language links, version
  consistency, Chinese README links, and stale wording.

### Fixed

- Language switching now preserves the current page, unlocked-step range,
  Generate unlock state, config, song summary, profile selections, output names,
  user-modified flags, config path, generation result, events, and output log.
- Valid page drafts are applied before a language switch; invalid drafts cancel
  the switch without destroying widgets or losing input.
- Layout and Output completion checks now use persistent `WizardState` config
  instead of uninitialized Tk variables in rebuilt hidden steps.
- Generate now restores succeeded or failed status, progress, localized logs,
  results, and output-folder buttons after a language switch.
- Summary displays localized labels for layout, direction, output format,
  datapack build style, tempo mode, and tempo backend while keeping internal
  enum values unchanged.
- Completed steps use a language-independent check mark instead of a hard-coded
  English `OK` marker.

## 0.1.0-gui-preview

### Added

- Tkinter seven-step wizard GUI with clickable step navigation.
- Config save/load and shared `Nbs2FuncConfig` round trips.
- Structured generation phase, progress, notice, warning, output, and error events.
- Datapack, schematic, and combined output formats.
- Directly connected simple function chain build style.
- Player-tp segmented build style for chunk-aware large builds.
- Optional starter module and minecart playback assist.
- Tempo-control `none`, `report`, and `command` modes.
- Exact Minecraft profiles for 1.14.4, 1.16.5, 1.18.2, 1.20.1, and 1.21.1.
- Unicode-capable datapack folder and schematic file names.
- Windows GUI and dependency-install launcher scripts.

### Changed

- CLI and GUI now share `generate_from_config()` and the same config system.
- Datapack and schematic writers consume a shared structured build plan.
- Combined output writes the full block structure to `.schem` and runtime-only
  logic to the datapack.
- Simple-chain output now splits large builds into directly connected function
  files, each limited to 65535 commands.
- GUI generation logs use concise structured events while CLI diagnostics remain detailed.

### Fixed

- GUI generation unlock, completion race, and navigation-state issues.
- Current-stage progress residue and empty retry-stage display.
- Stale generated datapack build files after regeneration.
- Unicode output names falling back to generic ASCII names.
- GUI-only state leaking across config loads and reset actions.
- Invalid values in disabled module fields blocking navigation.
- Missing datapack overwrite confirmation in the GUI.
- Missing close warning while background generation is running.

### Known Preview Limitations

- Note-based stereo placement is heuristic and can be expensive for large songs.
- Generation cannot be safely cancelled; forced exit can leave incomplete files.
- Simple-chain output assumes the target area is already loaded.
- Player-tp output requires an available configured build player.
- GUI testing and output-folder opening are currently Windows-focused.
- Schematic output does not embed summoned entities as live schematic entities.
- Manual arrangement and interactive layout visualization are not included.

See [docs/known_issues.md](docs/known_issues.md) for the complete list.
