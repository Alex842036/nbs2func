# nbs2func

`nbs2func` is an experimental Python tool that reads Note Block Studio `.nbs`
files and generates Minecraft Java Edition `.mcfunction` / datapack build
functions for redstone note block music.

Current status: **v0.1.0-preview / experimental**.

Current tested Minecraft version: **Java Edition 1.16.5**.

No open-source license has been selected yet. See `LICENSE` before publishing
publicly.

## Features

- Parses `.nbs` files into `Song`, `Track`, and `NoteEvent` models.
- Computes `final_volume` and `final_panning` from layer and note data.
- Supports layout modes:
  - `basic_linear`
  - `track_based_stereo`
  - `note_based_stereo`
- Generates note blocks, instrument blocks, gravity block support, redstone
  repeaters, track blocks, and starter structures.
- Uses split datapack output for large builds.
- Default build mode uses player teleport windows instead of `forceload`.
- Optional Playback Assist Module uses a minecart tagged `playback_vehicle`.
- Tested successfully with large NBS files around 30k / 40k note blocks.

## Install

Python 3.11 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

There are currently no external runtime dependencies. The parser is implemented
with Python's standard library.

## Basic Usage

Run with the default sample:

```powershell
$env:PYTHONPATH = "src"
python main.py
```

The default layout mode is `note_based_stereo`, so the bundled `demo.nbs` can
run without selecting a single track.

Run your own NBS:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs
```

Generate the recommended preview build:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs --layout-mode note_based_stereo --direction east --enable-playback-assist --playback-player-name YourName
```

For a small single-file debug output:

```powershell
$env:PYTHONPATH = "src"
python main.py examples\demo.nbs --layout-mode basic_linear --track-id 0 --no-split-functions
```

Default output path:

```text
output/generated.mcfunction
```

Split datapack output is written under:

```text
output/data/nbs/functions/build/
```

## Layout Modes

### basic_linear

Simple single-track line layout. It is useful for parser tests and small
debugging runs. If the NBS has more than one non-empty track, pass `--track-id`.

### track_based_stereo

Uses layer-level volume and stereo to place each track at a fixed offset.
This mode is stable and buildable, but it does not follow per-note panning.

### note_based_stereo

Experimental rail-based note-level stereo layout. Each note computes an ideal
emitter position from `final_volume` and `final_panning`, then assigns the
emitter to an activation rail slot.

This is the recommended preview mode for large stereo tests, but it is still
experimental.

## Useful Parameters

Common:

- `--layout-mode basic_linear|track_based_stereo|note_based_stereo`
- `--direction east|west|south|north`
- `--origin-x/y/z`
- `--output`
- `--no-split-functions`

Basic linear:

- `--track-id`

Stereo:

- `--max-hearing-distance`
- `--min-distance`
- `--max-stereo-angle-degrees`
- `--center-split-policy`
- `--center-split-override TRACK_ID=split|none`

Note-based stereo:

- `--max-candidates-per-emitter`
- `--retry-max-candidates-per-emitter`
- `--max-candidate-y-layers`
- `--max-candidate-lateral-positions`
- `--enable-same-side-zone-split-fallback`
- `--profile`

Player-tp build:

- `--build-player-name`
- `--player-tp-window-length-blocks`
- `--player-tp-window-lateral-width-blocks`
- `--player-tp-chunk-load-wait-ticks`
- `--player-tp-after-build-wait-ticks`
- `--max-commands-per-build-part`
- `--schedule-delay-ticks-between-parts`
- `--build-tp-y`
- `--build-finish-tp-x/y/z`

Playback assist:

- `--enable-playback-assist`
- `--playback-player-name`
- `--playback-vehicle-tag`
- `--vehicle-spawn-x/y/z`
- `--music-start-x/y/z`
- `--command-module-origin-x/y/z`
- `--no-playback-buttons`

## Minecraft Usage

For split output, copy or place the generated `data/` directory into a datapack,
then run:

```mcfunction
/reload
/function nbs:build/start
```

The default player-tp build mode works by teleporting the configured build
player to each build window:

1. The player is teleported to the window center.
2. The function waits 100 ticks by default for chunks to load.
3. Build parts run with scheduled delays.
4. The function waits 20 ticks by default after the window finishes.
5. The next window starts automatically.

Do not switch dimensions, move away manually, or interrupt the build while it is
running. Back up your world before testing large generated structures.

If Playback Assist is enabled:

1. Press the Prepare button to summon a minecart and reset counters.
2. Enter the minecart manually.
3. Press the Start button.
4. The minecart is teleported forward by the command loop.
5. When the counter reaches `start_music`, starter armor stands activate the
   note block structure.

## Recommended Preview Config

For large NBS testing on Java Edition 1.16.5:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs `
  --layout-mode note_based_stereo `
  --direction east `
  --enable-playback-assist `
  --playback-player-name YourName `
  --build-player-name YourName `
  --max-commands-per-build-part 500 `
  --player-tp-chunk-load-wait-ticks 100
```

If the game still stutters or misses chunks, lower
`--max-commands-per-build-part` or raise `--player-tp-chunk-load-wait-ticks`.

## Known Issues

- `note_based_stereo` is still experimental.
- Stereo and volume motion can be less smooth when collision avoidance has to
  move emitters.
- Large structures take time to build.
- The build process teleports the configured player.
- Minecraft worlds should be backed up before running generated functions.
- Java Edition 1.16.5 is the tested target; other versions may require command
  or block mapping changes.

## Project Docs

- `docs/architecture.md`
- `docs/modes.md`
- `docs/known_issues.md`
- `examples/README.md`

## Future Plans

- Smoother `note_based_stereo` assignment and movement.
- `.schem` output.
- GUI preview.
- RCON build mode.
- Better progress reporting for long builds.
