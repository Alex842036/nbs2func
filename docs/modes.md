# Generation Modes

[English](modes.md) | [简体中文](zh-CN/modes.md)

This document describes the user-selectable generation modes in
`v0.1.1`. CLI-only advanced controls are listed where useful; the
GUI intentionally presents a smaller, safer set.

## Layout Modes

### `basic_linear`

**Purpose:** Generate one NBS track as a straight redstone line.

**Recommended use:** Small structures, parser checks, output debugging, and
simple songs with one relevant track.

**Important behavior:** The selected track is placed along the configured
direction from the world origin. If multiple tracks contain notes, a track id
must be selected.

**Limitations:** It does not preserve a multi-track stereo field and is not a
general multi-layer arrangement mode.

**Controls:** Choose Basic Linear in the GUI and set Track ID in Layout Options,
or use `--layout-mode basic_linear --track-id <id>`.

### `track_based_stereo`

**Purpose:** Give each NBS layer/track a stable spatial position.

**Recommended use:** Multi-track stereo generation where predictable,
track-level placement is more important than note-level spatial detail.

**Important behavior:** Final layer volume and panning determine each track's
position. Per-track center splitting and whole-track collision resolution are
available. The GUI keeps collision spreading and center-split behavior on their
automatic defaults and exposes only the ordinary distance control.

**Limitations:** Every note in a track shares that track's placement. It cannot
represent note-by-note pan changes as precisely as note-based stereo.

**Controls:** Choose Track-Based Stereo in the GUI, or use
`--layout-mode track_based_stereo`. CLI users can access advanced center-split
and resolver options shown by `python main.py --help`.

### `note_based_stereo`

**Purpose:** Place individual note emitters using final volume and panning.

**Recommended use:** The main preview mode for songs that benefit from
note-level spatialization.

**Important behavior:** The layout generates emitter candidates, assigns rail
slots, validates rail geometry and collisions, and retries failed emitters in
multiple passes. GUI profiles provide safe, balanced, dense, and custom
settings. The generated result still uses the shared block-plan/output pipeline.

**Limitations:** The algorithm is heuristic. Complex songs are not guaranteed
to produce an ideal arrangement, and large files may require substantial CPU
time and memory. No specific maximum song size is guaranteed.

**Controls:** Choose Note-Based Stereo in the GUI, or use
`--layout-mode note_based_stereo`. Candidate, retry, collision, profiling, and
analysis controls remain available through the CLI/config for advanced use.

## Output Formats

### `datapack`

**Purpose:** Generate a complete datapack that builds the structure and runs
enabled module logic.

**Recommended use:** Building directly in a Minecraft world, especially when
starter or playback assist behavior is needed.

**Important behavior:** Output contains `pack.mcmeta` and version-correct
function directories. The main structure and enabled runtime behavior share one
build plan. Regeneration replaces the nbs2func-managed build function directory.

**Limitations:** Build functions modify the world. Back up the world and use an
appropriate build style for chunk loading.

**Controls:** Select Datapack in the GUI, or use `--output-format datapack`.

### `schem`

**Purpose:** Generate a WorldEdit-compatible `.schem` block structure.

**Recommended use:** Inspecting or placing the main redstone structure through
WorldEdit/Litematica-compatible workflows.

**Important behavior:** The schematic writer consumes the same structured
blocks as the datapack writer. `generation_origin` is the default coordinate
origin; `min_corner` is available. Unicode input stems are retained in default
file names.

**Limitations:** Schem-only output excludes starter and playback assist because
their behavior requires runtime commands. Summoned armor stands and minecarts
are not embedded as live schematic entities.

**Controls:** Select Schematic in the GUI, or use `--output-format schem`,
`--schematic-output`, `--schematic-name`, and `--schematic-origin-mode`.

### `both`

**Purpose:** Combine block placement through `.schem` with runtime behavior
through a datapack.

**Recommended use:** Place the full structure from a schematic while retaining
starter, playback, scoreboard, summon, execute, and entity setup logic.

**Important behavior:** The schematic includes structure and module blocks,
including command-block NBT where supported. The datapack receives the
runtime-only plan and does not duplicate note blocks, repeaters, support blocks,
or other main layout structure.

**Limitations:** Runtime-created entity instances are not schematic entities.
Both output artifacts must be installed/used correctly.

**Controls:** Select Both in the GUI, or use `--output-format both`.

## Datapack Build Styles

### `simple_chain`

**Purpose:** Execute generated commands through directly connected function
files without player-assisted chunk loading.

**Recommended use:** Smaller builds, tests, or controlled areas that are already
loaded.

**Important behavior:** Each file contains at most 65535 commands. Non-final
files reserve one command for directly calling the next part. There is no
player teleport, window partition, chunk wait, scheduled delay, or wait helper.

**Limitations:** Distant unloaded chunks are not made available automatically.
The caller is responsible for keeping the target area loaded.

**Controls:** Choose Simple Function Chain in the GUI, or use
`--datapack-build-style simple_chain`.

`--no-split-functions` is retained only as a compatibility CLI/config entry and
maps to `simple_chain`; despite its old name, large output is split into directly
connected files.

### `player_tp`

**Purpose:** Build large structures in spatial windows with an online player
providing chunk loading.

**Recommended use:** Large structures spread across many chunks. This is the
default GUI/config style.

**Important behavior:** The writer divides commands into windows and parts,
teleports the configured build player, waits for chunks, and schedules each
part and subsequent window. Advanced CLI/config values control window size,
waits, delays, player name, and commands per part.

**Limitations:** The configured build player must be valid and online. Leaving
the dimension, disconnecting, or interrupting execution can leave a partial
build.

**Controls:** Choose Player-TP Segmented Build in the GUI, or use
`--datapack-build-style player_tp` plus optional advanced player-tp flags.

## Optional Runtime Modules

### Starter

**Purpose:** Start generated tracks together from a configured command block.

**Recommended use:** Multi-track layouts and playback-assist setups.

**Important behavior:** Adds starter cells, marker setup, and a start command
block. The starter origin must be behind the music origin relative to the track
direction.

**Limitations:** Runtime behavior cannot be represented by schem-only output.

**Controls:** Enable Starter Module in the GUI, or use
`--enable-starter-module` and the starter position/tag options.

### Playback Assist

**Purpose:** Provide minecart-based playback movement and controls.

**Recommended use:** In-world playback where scoreboard-driven movement and
Prepare/Start controls are useful.

**Important behavior:** Adds command blocks, scoreboard state, minecart summon
and movement commands, and optional buttons. The GUI requires Starter before
Playback Assist can be enabled. The playback music start is tied to the layout
origin in GUI-generated config.

**Limitations:** Requires a valid player name, command permissions, and runtime
datapack logic. It is unavailable with schem-only output in the GUI.

**Controls:** Use the Modules step, or CLI options beginning with
`--enable-playback-assist`, `--playback-`, `--vehicle-`, and
`--command-module-origin-`.

## Tempo Control Modes

### `none`

**Purpose:** Disable tempo-control calculation and commands.

**Recommended use:** Keep the fixed redstone timing model without a report.

**Important behavior:** No tempo report or tick-rate command is generated.

**Limitations:** Song tempo differences are not compensated through tick rate.

**Controls:** `--tempo-control-mode none` or None in the GUI.

### `report`

**Purpose:** Calculate a recommended Minecraft tick rate without changing the
world.

**Recommended use:** Default safe mode and manual tempo planning.

**Important behavior:** Reports NBS tempo, timing model, recommended tick rate,
backend, command, reset command, warnings, and permission hints.

**Limitations:** The report alone does not execute a command.

**Controls:** `--tempo-control-mode report` or Report in the GUI.

### `command`

**Purpose:** Apply the recommended tick rate through playback start/reset logic.

**Recommended use:** Playback-assist setups where the required backend and
permissions are available.

**Important behavior:** Requires playback assist. The start sequence emits the
tick-rate command, and playback can reset to 20 TPS when configured.

**Limitations:** Older profiles require Carpet-compatible capability. The
1.21.1 profile uses its vanilla command profile, which still requires suitable
permissions and may not be available to command blocks/datapacks by default.

**Controls:** Use `--tempo-control-mode command`,
`--tempo-control-backend auto|carpet|vanilla`, and optional reset/precision
settings, or the Modules step in the GUI.
