# Wizard GUI Guide

The `v0.1.0-gui-preview` wizard is a config-driven Tkinter interface for the
same generation pipeline used by the CLI. Windows is the primary tested GUI
platform.

## Starting The GUI

On Windows, install dependencies with `install_requirements.bat`, then start
the application with `run_gui.bat`.

PowerShell equivalent:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m nbs2func.gui.app
```

The step bar shows completed, current, and locked steps. Completed steps can be
clicked without losing config values. Every navigation action applies and
validates the current step first.

## 1. Input

Choose an `.nbs` file with Browse, or type a path and select Load NBS. A
successful read shows the song name, length, tempo, layer count, note count,
and available instrument summary.

If the path changes, the wizard reloads and validates it before continuing. An
empty path, missing file, directory, or malformed NBS blocks navigation instead
of reusing an older song summary. Local Unicode file names, including Chinese
and Japanese names, are supported.

## 2. Layout

Choose one layout strategy:

- `basic_linear`: one selected track in a straight line.
- `track_based_stereo`: fixed layer/track positions derived from volume and pan.
- `note_based_stereo`: note-level rail-slot placement; the default heuristic
  preview mode.

## 3. Layout Options

Set the track direction, world origin X/Y/Z, exact Minecraft version, and the
options relevant to the selected layout.

Direction choices are east (+X), west (-X), south (+Z), and north (-Z). The GUI
validates origin Y against the selected version profile while reserving the
48-block vertical sound-distance range on both sides. It does not expose manual
`min_world_y` or `max_world_y` overrides.

Track-based stereo exposes its user-facing distance control while fixed
collision and center-split behavior remains automatic. Note-based stereo offers
safe, balanced, dense, and custom profiles; preset values are read-only, while
custom enables the advanced candidate controls.

## 4. Modules

The Modules page groups Starter Module, Playback Assist, and Tempo Control.

- Starter creates the synchronized start command-block position.
- Playback assist adds minecart-based runtime logic, player scoreboard state,
  and optional Prepare/Start buttons.
- Playback assist requires Starter in the GUI.
- Tempo command mode requires playback assist.

Starter and command-module origins are validated relative to the layout
direction. Playback music start follows the layout origin. Disabled module
fields are ignored during validation.

Tempo modes are `none`, `report`, and `command`; backends are `auto`, `carpet`,
and `vanilla`. Report mode does not alter world tick rate. Command mode writes
start/reset commands and requires the necessary server permissions and backend.

## 5. Output

Choose one output format:

- `datapack`: full block build plus enabled runtime modules.
- `schem`: structure-only `.schem`; runtime-dependent modules are unavailable.
- `both`: full block schematic plus runtime-only datapack commands.

Datapack fields include an output path, Unicode-capable folder name, namespace,
and build style. Schematic fields include an output path, file name, and origin
mode. The default schematic name follows the input NBS stem and preserves
Unicode.

Datapack build styles:

- Simple function chain splits large output into directly connected function
  files, with no teleport, chunk wait, player-tp windows, or scheduled delay.
- Player-tp segmented build uses spatial windows, teleports the configured build
  player, waits for chunks, and schedules command parts. It is the default and
  is recommended for large structures.

If Starter or Playback Assist is enabled, schem-only is disabled because those
modules require runtime logic. Choose `both` to combine schematic blocks with
runtime commands.

## 6. Summary

Review the input song, layout, important options, output format and paths,
modules, tempo mode, and warnings. Save Config writes the current
`Nbs2FuncConfig` to JSON. The bottom Generate button applies the Summary state,
performs final validation, confirms any existing datapack folder, and enters the
Generate page.

## 7. Generate

Generation runs in a background Python thread and reports structured events to
the Tk main loop. The page shows:

- monotonic overall progress;
- current-stage progress that is overwritten instead of appended repeatedly;
- concise phase, notice, warning, output, done, and error log entries;
- Open datapack/mcfunction folder and Open schematic folder actions;
- Generate another, Back, and Finish actions.

Navigation, Finish, and state-changing menus are disabled while generation is
running. When generation completes or fails, Back returns to Summary and Finish
uses the normal close handler. Generate another clears generation state and
returns to Input with default config.

Closing the window or selecting File > Exit during generation asks for explicit
confirmation because the worker cannot be safely cancelled and incomplete files
may remain.

For `datapack` and `both`, the GUI asks before generating into an existing
datapack root. Rejecting the prompt leaves the wizard editable and does not
start the worker or delete files. Schem-only output does not show this datapack
prompt.

Opening output folders is currently supported only on Windows in this preview.

## Config Menu

- New resets the wizard and GUI-only state to defaults.
- Load Config creates a fresh wizard state from JSON and attempts to reload the
  input song.
- Save Config and Save Config As apply the current page before writing.
- Exit uses the same close handler as the window close button.

The GUI has no separate generation implementation and does not parse CLI stdout.
