# nbs2func

[English](README.md) | [简体中文](README.zh-CN.md)

**Current version: v0.1.1**

`nbs2func` converts Open Note Block Studio `.nbs` songs into Minecraft Java
Edition redstone note-block structures. It provides a Windows-focused Tkinter
wizard, a full CLI, datapack build functions, and WorldEdit-compatible
`.schem` output.

## Preview Status

This is a preview release. The core generator, wizard GUI, datapack output,
and schematic output are usable, but the project is not production-ready.
`note_based_stereo` remains heuristic, and difficult or very large songs may
require substantial CPU time and memory.

Back up your Minecraft world before executing generated build functions.

## Platform And Requirements

- Python 3.11 or newer.
- Dependencies from `requirements.txt`, including `mcschematic` and `pytest`.
- Minecraft Java Edition. Bedrock Edition is not supported.
- Primary development and GUI testing platform: Windows.

`run_gui.bat` and `install_requirements.bat` are Windows helpers. Opening output
folders from the GUI is currently supported only on Windows. The Python source
may work on macOS or Linux, but GUI behavior there has not been fully verified.

The repository is not currently a pip-installable package. Run it from the
project root with `PYTHONPATH=src`.

## Windows GUI Quick Start

1. Install Python 3.11 or newer.
2. Extract or clone this repository.
3. Double-click `install_requirements.bat`.
4. Double-click `run_gui.bat`.

`run_gui.bat` changes to the project root, sets `PYTHONPATH` to `src`, prefers
`py -3`, and falls back to `python`.

Equivalent PowerShell commands:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m nbs2func.gui.app
```

See [docs/gui.md](docs/gui.md) for the complete wizard guide.

## CLI Quick Start

Install dependencies and set the source path:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

Generate the bundled demo with the default config:

```powershell
python main.py
```

Generate another song:

```powershell
python main.py path\to\song.nbs
```

Choose an output format or datapack build style:

```powershell
python main.py path\to\song.nbs --output-format schem
python main.py path\to\song.nbs --output-format both
python main.py path\to\song.nbs --datapack-build-style simple_chain
python main.py path\to\song.nbs --datapack-build-style player_tp
```

Run `python main.py --help` for the complete CLI option list.

## GUI Workflow

The wizard preserves one `Nbs2FuncConfig` while moving through seven steps:

1. Input
2. Layout
3. Layout Options
4. Modules
5. Output
6. Summary
7. Generate

Completed steps can be revisited from the step bar. Summary provides config
saving and the bottom Generate action. Generate shows overall and current-stage
progress, concise structured logs, output-folder actions, Generate another,
Back, and Finish.

The GUI calls the same `generate_from_config()` entry point as the CLI. It does
not launch the CLI as a subprocess or parse CLI output.

The GUI supports English and Simplified Chinese. Use Language in the menu bar
to switch; the choice is saved in `~/.nbs2func/gui_settings.json` and restored
the next time the GUI starts. Switching languages preserves the current config,
unlocked steps, valid in-progress edits, and completed generation results. If
the current page contains invalid input, the switch is cancelled so the draft
can be corrected without losing it. The CLI remains English-only.

## Output Formats

### `datapack`

Writes a complete datapack containing `pack.mcmeta` and generated build
functions. The datapack includes the main structure and any enabled modules.

For Minecraft 1.14.4 through 1.20.1:

```text
<datapack>/data/<namespace>/functions/<build_function_dir>/...
```

For Minecraft 1.21.1:

```text
<datapack>/data/<namespace>/function/<build_function_dir>/...
```

### `schem`

Writes a `.schem` from the same structured block plan used by datapack output.
The default file name comes from the input NBS stem and preserves Unicode.
Schematic coordinates use `generation_origin` by default; `min_corner` is also
available.

Schem-only output contains the main redstone structure. Starter and playback
assist depend on runtime logic and are not included. The GUI prevents this
incompatible combination.

### `both`

Writes complementary outputs:

- The `.schem` contains the full block structure, including module command
  blocks and their NBT where supported.
- The datapack contains runtime-only commands such as scoreboard, summon,
  execute, and entity setup.
- The datapack does not duplicate the main note-block/repeater structure.
- Summoned entities such as armor stands and minecarts are not embedded as live
  schematic entities; runtime commands create them.

## Datapack Build Styles

### `simple_chain`

- Splits large command output into directly connected mcfunction files.
- Each file contains at most 65535 commands.
- Non-final files reserve one command for calling the next function file.
- Does not teleport the player, wait for chunks, use player-tp windows, or add
  scheduled delays between parts.
- Requires the target area to remain loaded.
- Best for smaller builds, testing, or controlled loaded areas.

### `player_tp`

- Default GUI and config build style.
- Divides the build into spatial windows.
- Teleports the configured build player to each window.
- Waits for nearby chunks to load and runs scheduled command parts.
- Adds more helper commands and takes more ticks.
- Recommended for large structures.

Do not leave the dimension, disconnect the build player, or interrupt a
player-tp build while it is running.

`--no-split-functions` remains a compatibility alias for `simple_chain`. New
commands should use `--datapack-build-style simple_chain` or
`--datapack-build-style player_tp`.

## Layout Modes

### `basic_linear`

Generates one selected track as a straight redstone line. It is mainly useful
for small structures, parser checks, and debugging. Songs with multiple
non-empty tracks require a track id.

### `track_based_stereo`

Assigns each NBS layer/track a stable spatial position from its volume and
panning. It supports per-track center splitting and is simpler and generally
more predictable than note-level stereo.

### `note_based_stereo`

The default preview layout. Each note emitter receives a target derived from
final volume and panning, then uses rail-slot candidate generation, assignment,
validation, and retries. This mode is heuristic: complex songs are not
guaranteed to receive an ideal arrangement, and large inputs can be expensive.

See [docs/modes.md](docs/modes.md) for detailed controls and limitations.

## Optional Modules

### Starter module

Adds synchronized starter cells and a command block used to begin the generated
music structure.

### Playback assist

Adds minecart-based playback runtime logic, scoreboard state, Prepare/Start
controls, and movement commands. In the GUI, playback assist requires the
starter module. Player names, tags, module positions, and related advanced
settings are available through config and CLI options.

Runtime-dependent modules cannot be used with schem-only output in the GUI.
Choose `datapack` or `both` instead.

## Tempo Control

Tempo control uses the shared timing model in `core/tempo_control.py`:

- `none`: does not calculate or apply tempo-control behavior.
- `report`: the default safe mode. Calculates and reports a recommended
  Minecraft tick rate without changing the world tick rate.
- `command`: requires playback assist and inserts tick-rate commands into the
  playback start/reset logic. Resetting to 20 TPS after playback is configurable.

Backends:

- `auto` selects the backend from the exact Minecraft version profile.
- Older supported profiles use Carpet-compatible tick-rate commands.
- The 1.21.1 profile uses the supported vanilla tick-rate command profile.

The user still needs suitable permissions and any required mod or server
capability. Not every supported Minecraft version provides a native `/tick`
command.

## Supported Minecraft Versions

| Exact profile | CLI aliases | Pack format | Build height | Function directory | Tempo backend |
|---|---|---:|---:|---|---|
| `1.14.4` | `1.14`, `1.14.x` | 4 | `0..255` | `functions/` | Carpet-compatible |
| `1.16.5` | `1.16`, `1.16.x` | 6 | `0..255` | `functions/` | Carpet-compatible |
| `1.18.2` | `1.18`, `1.18.x` | 9 | `-64..319` | `functions/` | Carpet-compatible |
| `1.20.1` | `1.20` | 15 | `-64..319` | `functions/` | Carpet-compatible |
| `1.21.1` | `1.21` | 48 | `-64..319` | `function/` | Vanilla profile |

Aliases select one exact profile; they are not compatibility promises for an
entire patch series. Profiles determine pack format, build height, instrument
support, tempo backend, function-directory layout, and output capabilities.
Unsupported instruments or base blocks fail generation rather than silently
falling back.

## Output And In-Game Use

With the default namespace and build directory, install the generated datapack
in the world's `datapacks` directory, then run:

```mcfunction
/reload
/function nbs:build/start
```

For WorldEdit, place generated `.schem` files in the schematic folder used by
your WorldEdit installation, then load and paste them according to WorldEdit's
commands. Back up the world first.

Before writing a datapack, nbs2func replaces the generated build-function
directory it owns. The GUI asks before reusing an existing datapack root; the
CLI overwrites automatically. Other namespaces under the datapack root are not
removed by this cleanup.

## Config Files And CLI Overrides

Configuration precedence is:

```text
default_config()
  -> --config JSON
  -> explicit CLI arguments
```

Useful config commands:

```powershell
python main.py --dump-default-config
python main.py path\to\song.nbs --save-config song-config.json
python main.py --config song-config.json
```

The GUI initializes from the same defaults, can load/save JSON config files,
and sends the resulting `Nbs2FuncConfig` to the shared generator. CLI-only
analysis and advanced diagnostic controls are intentionally not exposed in the
wizard.

## Known Limitations

- `note_based_stereo` remains heuristic.
- Very large songs may require substantial processing time and memory. The
  current layout generator is largely single-threaded, so total CPU utilization
  may appear low on multi-core systems.
- CPU-bound generation shares CPython's GIL with the Tkinter main thread, so the
  GUI may briefly appear unresponsive even when overall CPU utilization is low.
- There is no safe cancellation operation during generation.
- Simple-chain builds do not load chunks or wait between function files.
- Player-tp builds depend on a valid online build player and can be interrupted.
- GUI testing and output-folder opening are currently Windows-focused.
- Schematic files do not embed summoned entities as live schematic entities.
- Manual arrangement and interactive 2D/3D editing are not implemented.

See [docs/known_issues.md](docs/known_issues.md) before using generated output.

## Documentation

- [GUI guide](docs/gui.md)
- [Generation modes](docs/modes.md)
- [Architecture](docs/architecture.md)
- [Known issues](docs/known_issues.md)
- [Changelog](CHANGELOG.md)
- [Example files](examples/README.md)
- [简体中文 README](README.zh-CN.md)

## Development And Testing

Run the complete test suite from the project root:

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

The project favors focused, output-preserving changes. Do not commit or publish
NBS songs unless you have the right to redistribute them.

## Roadmap

Possible future work, without release-date commitments:

- manual track/group arrangement mode;
- manual override visualization;
- performance improvements for very large note-based layouts;
- safe cancellation or a process-based generation worker;
- packaging and installable releases;
- additional exact Minecraft version profiles;
- optional 2D/3D layout visualization;
- server-assisted or RCON workflows.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

Generated datapacks, functions, and schematics may contain musical arrangements
derived from the input NBS file. Users are responsible for the rights to use,
modify, and distribute their songs and generated output.
