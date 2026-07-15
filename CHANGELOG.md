# Changelog

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
