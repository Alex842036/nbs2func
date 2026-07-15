# Architecture

`nbs2func` uses one config-driven generation pipeline for the CLI and GUI:

```text
CLI or GUI
  -> Nbs2FuncConfig
  -> generate_from_config()
  -> NBS reader
  -> layout strategy
  -> LayoutResult
  -> output.block_builder
  -> GeneratedBuildPlan
  -> scoped plans
       datapack full plan
       schematic structure plan
       both runtime-only plan
  -> command_writer / schematic_writer
```

## Entry Points And Config

`config.py` defines `Nbs2FuncConfig`, defaults, JSON load/save, validation, and
compatibility migration. CLI precedence is defaults, loaded JSON, then explicit
arguments. The GUI edits the same config model.

`generation.py` owns ordinary generation orchestration through
`generate_from_config(config, progress_callback=None, include_diagnostics=False)`.
It reads the song, resolves the version profile, validates instruments and
tempo settings, runs layout, builds the structured plan, selects output scopes,
invokes writers, and returns output paths.

The CLI requests diagnostics and prints its detailed developer report. The GUI
does not request diagnostics and shows only structured progress events.

## Core

- `core/models.py` defines songs, tracks, and notes.
- `core/nbs_reader.py` parses `.nbs` files.
- `core/minecraft_version.py` centralizes exact version profiles, aliases, pack
  format, build height, function-directory names, instrument support, schematic
  capability, and tempo backend.
- `core/instrument_mapping.py` maps NBS instruments to Minecraft note-block
  instruments/base blocks and validates profile support.
- `core/tempo_control.py` owns all tempo formulas, reports, command formatting,
  backend selection, limits, warnings, and permission hints.

## Layout

`layout/` owns placement decisions and returns `LayoutResult`:

- `facade.py` exposes strategy construction and compatibility imports.
- `models.py` defines layout cells, rails, emitters, reports, and internal
  `LayoutProgressEvent`.
- `geometry.py`, `pan.py`, and `collision.py` provide shared spatial rules.
- `basic.py`, `track_stereo.py`, and `note_stereo.py` implement the three
  automatic layout strategies.

Layout code decides where tracks, cells, rails, repeaters, note blocks, and
reserved spaces belong. It does not serialize datapacks or schematics.

## Structured Output

`output/models.py` defines `PlacedBlock`, `GeneratedCommand`, sections, and
`GeneratedBuildPlan`.

`output/block_builder.py` converts a layout plus resolved writer/module config
into the final structured plan. It owns final block IDs/states, NBT, source
labels, module blocks, and non-block runtime commands. Both writers consume this
data; schematic generation never parses mcfunction text.

Four plan scopes are available:

- **Full:** structure blocks, module blocks, and runtime logic.
- **Structure-only:** main layout blocks without module blocks or runtime logic.
- **Structure with module blocks:** main structure plus module command blocks,
  without runtime-only commands.
- **Runtime-only:** commands such as scoreboard, summon, execute, and entity
  setup, without structure/module blocks.

Output mapping:

| Format | Datapack plan | Schematic plan |
|---|---|---|
| `datapack` | Full | None |
| `schem` | None | Structure-only |
| `both` | Runtime-only | Structure with module blocks |

This mapping is a stability boundary: combined output must not duplicate the
main note-block/repeater structure in its datapack.

## Writers

`output/command_writer.py` serializes a `GeneratedBuildPlan` into a complete
datapack. Simple-chain output uses directly connected function files with a
65535-command per-file limit. Player-tp output groups command packets by spatial
windows and schedules teleport, wait, part, and completion functions.

`output/schematic_writer.py` converts the same `PlacedBlock` values into
relative schematic coordinates and writes `.schem` through `mcschematic`.
Inline block state and command-block NBT are preserved where supported.
Generated commands that represent entity creation remain runtime commands; they
are reported as omitted from schem-only serialization.

Before datapack writing, `generation.py` removes only the nbs2func-managed build
function directory under the selected namespace. It does not delete other
namespaces. The GUI confirms when the datapack root already exists; the CLI
performs the scoped cleanup and overwrite without interactive input.

## Modules

`modules/starter.py` builds synchronized starter cells, marker setup, and the
start command block.

`modules/playback_assist.py` builds minecart playback command blocks, scoreboard
logic, buttons, movement commands, and tempo start/reset integration. It consumes
tempo reports from `core/tempo_control.py`; it does not duplicate tempo formulas.

## GUI

`gui/wizard.py` owns the seven-step navigation shell, menus, config state,
validation, close protection, and datapack overwrite confirmation. Individual
pages live under `gui/steps/`.

The Generate page starts `generate_from_config()` in a background Python thread.
The progress callback places immutable `GenerationEvent` values in a thread-safe
queue. Tk's `after()` loop drains the queue and updates local widgets:

- phase, notice, warning, output, done, and error events append to the log;
- progress events overwrite the current-stage display;
- overall progress is monotonic;
- no polling cycle rebuilds the whole page.

The GUI does not run a CLI subprocess and does not parse stdout. It has no
independent layout, build-plan, or writer implementation.

## CLI And Analysis

`cli.py` handles argument parsing, config precedence, default-config utilities,
analysis dispatch, and detailed diagnostic reporting. Normal generation is
delegated to `generate_from_config(include_diagnostics=True)`.

`analysis/spatial_analyzer.py` is read-only. It reports spatial properties and
does not mutate generation behavior.

## Stability Boundaries

- Exact Minecraft profiles determine output capabilities and paths.
- Layout owns geometry; block builder owns final structured output; writers own
  serialization.
- GUI and CLI share config and generation orchestration.
- Combined output keeps runtime-only datapack semantics.
- Playback assist uses minecarts.
- Tempo formulas remain in `core/tempo_control.py`.
