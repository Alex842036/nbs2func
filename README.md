# nbs2func

`nbs2func` converts Open Note Block Studio `.nbs` songs into Minecraft Java Edition datapacks / `.mcfunction` build functions for redstone note block music.

Current status: **v0.1.0-preview**.

The project is usable for preview builds, including large note-based stereo tests, but it is still experimental. Back up your world before running generated functions.

## What it generates

`nbs2func` reads an `.nbs` file, computes note positions, and writes a generated datapack containing build functions. The build functions place:

- note blocks;
- instrument blocks under note blocks;
- support blocks for gravity blocks such as sand;
- repeaters and track blocks;
- optional starter structures;
- optional minecart playback assist command blocks.

The default build output is a split datapack designed for large structures. Instead of relying on `forceload`, the generated build function teleports a configured build player through build windows so nearby chunks can load before each batch of `setblock` commands runs.

## Supported Minecraft versions

The project targets **Minecraft Java Edition 1.14+**. Older Java versions such as 1.12 and 1.13 are intentionally not supported.

Currently implemented version profiles:

| CLI value | Exact profile used | Datapack functions directory | Notes |
|---|---:|---|---|
| `1.14` or `1.14.4` | `1.14.4` | `data/<namespace>/functions/` | Supports the standard 1.14+ note block instrument set. |
| `1.16` or `1.16.5` | `1.16.5` | `data/<namespace>/functions/` | Default and main tested baseline. |
| `1.18` or `1.18.2` | `1.18.2` | `data/<namespace>/functions/` | Uses the newer world height range. |
| `1.20` or `1.20.1` | `1.20.1` | `data/<namespace>/functions/` | Exact profile only; not a blanket claim for all 1.20.x versions. |
| `1.21` or `1.21.1` | `1.21.1` | `data/<namespace>/function/` | Supports the 1.21 profile and copper note block instruments. |

Aliases such as `1.20` select one explicit profile, currently `1.20.1`; they do **not** mean every patch version in that series is supported.

The selected version profile controls:

- `pack.mcmeta` `pack_format`;
- datapack function directory layout;
- supported note block instruments;
- supported instrument base blocks;
- build height validation;
- output module capability checks.

If an input song uses an instrument or base block unsupported by the selected Minecraft version, generation fails instead of silently falling back to another sound.

## Requirements

- Python 3.11 or newer is recommended.
- No external runtime package is currently required.
- `pytest` is required only for running tests.

Install for local development:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The repository is not packaged as an installable Python package yet. Use `PYTHONPATH=src` when running from source.

## Quick start

Run the bundled demo:

```powershell
$env:PYTHONPATH = "src"
python main.py
```

Generate from your own `.nbs` file:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs
```

Choose a target Minecraft profile:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs --minecraft-version 1.16.5
```

Recommended preview command for a large stereo test:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs --minecraft-version 1.16.5 --layout-mode note_based_stereo --direction east --enable-playback-assist --playback-player-name YourName --build-player-name YourName
```

For a small single-file debug output:

```powershell
$env:PYTHONPATH = "src"
python main.py examples\demo.nbs --layout-mode basic_linear --track-id 0 --no-split-functions
```

## Output layout

By default, the output parent directory is `output/`. For an input file named `song.nbs`, the generated datapack root is usually:

```text
output/song/
```

For Minecraft versions using the legacy plural function directory, build functions are written under:

```text
output/song/data/nbs/functions/build/
```

For profiles using the newer singular directory layout, such as `1.21.1`, build functions are written under:

```text
output/song/data/nbs/function/build/
```

The entry function is still called with the same function namespace/path form in-game:

```mcfunction
/function nbs:build/start
```

For split output, the generated datapack contains:

```text
pack.mcmeta
data/nbs/functions/build/...   # or data/nbs/function/build/... for profiles that use singular paths
```

## Using the datapack in Minecraft

1. Generate the datapack.
2. Copy the generated datapack folder into your world’s `datapacks/` directory.
3. Enter the world.
4. Run:

```mcfunction
/reload
/function nbs:build/start
```

For large builds, the default player-tp build mode:

1. teleports the configured build player to a build window;
2. waits for chunks to load;
3. runs scheduled build parts;
4. moves to the next window;
5. repeats until the build is complete.

Do not switch dimensions, manually move far away, or interrupt the build while it is running.

## Layout modes

### `basic_linear`

Simple single-track redstone line layout.

Use it for:

- parser validation;
- small debug output;
- minimal single-track tests.

If the NBS has multiple non-empty tracks, pass `--track-id`.

### `track_based_stereo`

Places each NBS track at a stable position derived from layer volume and stereo.

Use it when you want:

- a simpler stereo layout;
- fixed per-track positions;
- lower complexity than note-level stereo.

### `note_based_stereo`

Preview-quality rail-based note-level stereo layout. Each note computes a target position from final volume and final panning, then assigns the note emitter to an activation rail slot.

This is the default layout mode and the current main development target. It has been tested on large 30k / 40k note NBS files, but it remains heuristic and can still require tuning for difficult songs.

## Playback Assist

The optional playback assist module generates a minecart-based playback helper.

Enable it with:

```powershell
--enable-playback-assist --playback-player-name YourName
```

Typical flow:

1. Build the generated structure.
2. Press the generated Prepare button to summon/reset the playback minecart and counters.
3. Enter the minecart.
4. Press the Start button.
5. The command loop moves the minecart along the track while the starter system activates the music.

Useful parameters:

```text
--enable-playback-assist
--playback-player-name
--playback-vehicle-tag
--music-start-x / --music-start-y / --music-start-z
--command-module-origin-x / --command-module-origin-y / --command-module-origin-z
--no-playback-buttons
```

## Common CLI options

General:

```text
--minecraft-version
--output
--layout-mode
--direction
--origin-x / --origin-y / --origin-z
--no-split-functions
```

Stereo:

```text
--max-hearing-distance
--min-distance
--max-stereo-angle-degrees
--center-split-policy
--center-split-override
```

Note-based stereo:

```text
--max-candidates-per-emitter
--retry-max-candidates-per-emitter
--max-candidate-y-layers
--max-candidate-lateral-positions
--radius-search-tolerance
--disable-depth-mirror-candidates
--preferred-depth-sign
--depth-mirror-penalty
--profile
```

Player-tp build:

```text
--build-player-name
--max-commands-per-build-part
--schedule-delay-ticks-between-parts
--player-tp-window-length-blocks
--player-tp-window-lateral-width-blocks
--player-tp-chunk-load-wait-ticks
--player-tp-after-build-wait-ticks
--build-tp-y
--build-finish-tp-x / --build-finish-tp-y / --build-finish-tp-z
```

Run `python main.py --help` for the complete option list.

## Layout spatial analysis

`nbs2func` also includes a read-only layout spatial analyzer. It can inspect layers, windows, density, pan, volume, and texture-like properties without generating a datapack.

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs --analyze-layout-spatial --analysis-detail summary
```

Write analysis JSON to a file:

```powershell
$env:PYTHONPATH = "src"
python main.py path\to\song.nbs --analyze-layout-spatial --analysis-detail full --analysis-output analysis.json
```

The old `--analyze-stereo` option has been removed.

## Known limitations

- `note_based_stereo` is still preview-quality and heuristic.
- Large NBS files can take minutes to generate.
- Large generated structures can take time to build in-game.
- The split build mode teleports the configured build player between build windows.
- Unsupported target-version instruments cause generation to fail; there is no silent fallback.
- The project currently targets Minecraft Java Edition only, not Bedrock Edition.
- Song tempo adaptation is not implemented yet. 


## Project structure

```text
main.py
src/nbs2func/
  cli.py
  nbs_reader.py
  models.py
  minecraft_version.py
  instrument_mapping.py
  layout.py
  layout_basic.py
  layout_track_stereo.py
  layout_note_stereo.py
  command_writer.py
  starter_module.py
  playback_assist_module.py
docs/
examples/
tests/
```

Key modules:

- `nbs_reader.py`: reads `.nbs` files.
- `models.py`: shared song, track, and note models.
- `minecraft_version.py`: target version profiles and datapack metadata settings.
- `instrument_mapping.py`: NBS/Minecraft instrument mapping and version validation.
- `layout_*`: layout strategies and note-based stereo rail preview logic.
- `command_writer.py`: datapack and `.mcfunction` output.
- `starter_module.py`: optional starter activation module.
- `playback_assist_module.py`: optional minecart playback assist module.
- `layout_spatial_analyzer.py`: read-only spatial analysis.

## Development notes

The project favors small, output-preserving changes. For generation logic changes, run the test suite and compare output on a small `.nbs` before testing large files.

Do not commit large `.nbs` files unless you have the rights to distribute them. The repository intentionally keeps only the tiny demo file by default.

## Roadmap

Possible future work:

- further candidate generation performance optimization;
- more detailed progress logging for large songs;
- additional Minecraft Java version profiles;
- `.schem` output;
- GUI or visual preview tooling;
- RCON or server-assisted build modes.

## License

This project is licensed under the MIT License. See `LICENSE` for the full license text.

The MIT License applies to the `nbs2func` source code.

Generated datapacks and `.mcfunction` files may contain musical arrangements derived from the input `.nbs` file. Users are responsible for ensuring they have the right to use, modify, and distribute their input songs and generated outputs.
