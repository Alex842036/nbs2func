# AGENTS.md

## Project Goal

`nbs2func` converts Open Note Block Studio `.nbs` songs into Minecraft Java Edition redstone music structures.

The project is currently in `v0.1.0-preview`. Prefer small, low-risk changes. Preserve generated output unless the task explicitly asks for behavior changes.

Default target version is Minecraft Java Edition 1.16.5.

---

## Current Architecture

Core input and data model:

* `src/nbs2func/nbs_reader.py`: reads `.nbs` files into internal song models.
* `src/nbs2func/models.py`: shared song, layer, and note data models.
* `src/nbs2func/instrument_mapping.py`: maps NBS instruments to Minecraft note block instruments and base blocks.

Layout system:

* `src/nbs2func/layout.py`: facade / compatibility layer. Re-exports old public layout API.
* `src/nbs2func/layout_models.py`: shared layout dataclasses and strategy base types.
* `src/nbs2func/layout_geometry.py`: direction, vector, coordinate, and repeater-position helpers.
* `src/nbs2func/layout_pan.py`: pan, angle, pan-zone, and lateral-zone helpers.
* `src/nbs2func/layout_collision.py`: footprint, block collision, reserved-air, and occupancy helpers.
* `src/nbs2func/layout_basic.py`: `BasicLinearLayout`.
* `src/nbs2func/layout_track_stereo.py`: `TrackBasedStereoLayout`.
* `src/nbs2func/layout_note_stereo.py`: `NoteBasedStereoLayout` and `NoteBasedStereoRailLayout`.

Output and modules:

* `src/nbs2func/command_writer.py`: writes mcfunction/datapack build output.
* `src/nbs2func/minecraft_version.py`: Minecraft version profile and datapack metadata settings.
* `src/nbs2func/starter_module.py`: optional starter module.
* `src/nbs2func/playback_assist_module.py`: optional minecart playback assist module.
* `src/nbs2func/cli.py`: command-line entry point and debug/report output.

---

## Stable Conventions

* Default build mode uses `player_tp`.
* Playback Assist uses minecart entities, not pigs.
* Default Minecraft target is Java Edition 1.16.5.
* Java 1.16.5 datapacks use `pack_format = 6`.
* Current datapack output should be a complete datapack folder:

  * `pack.mcmeta`
  * `data/nbs/functions/...`
* Do not create `src/nbs2func/layout/` as a package while `src/nbs2func/layout.py` still exists.

---

## Important Rules

Do not modify these unless the task explicitly asks for it:

* collision detection semantics;
* footprint / reserved-air rules;
* final pan formula;
* pan-zone / angle-zone thresholds;
* note-based candidate generation;
* note-based assignment / retry behavior;
* center-split behavior;
* depth-mirror behavior;
* player-tp build scheduling;
* minecart playback assist timing;
* generated command format.

Do not change test expected output during structural cleanup unless the existing expectation is demonstrably wrong and the task explicitly asks for it.

Prefer small, incremental edits over whole-repository refactors.

---

## Git Safety Rules

Before making code changes:

1. Run `git status`.
2. If the working tree is not clean, stop and report the status unless the user explicitly says to continue.

After making code changes:

1. Run the relevant tests.
2. Report:

   * `git diff --stat`
   * `git status`
   * test results

Do not run these commands unless the user explicitly asks:

* `git add`
* `git commit`
* `git push`
* `git reset --hard`
* `git clean`

For exploratory features, use a feature branch. Example:

```bash
git switch -c feature/note-stereo-analyzer
```

If branch creation is requested but the working tree is not clean, stop and report instead of creating the branch.

---

## Common Test Commands

From the repository root:

```bash
PYTHONPATH=src python -m pytest
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

Do not run large `.nbs` generation tests unless the task explicitly asks for it.

---

## Current Development Direction

The existing layout modes should remain stable:

* `BasicLinearLayout`
* `TrackBasedStereoLayout`
* `NoteBasedStereoLayout`
* `NoteBasedStereoRailLayout`

Future high-precision work should be developed separately from the existing note-based stereo baseline.

Planned exploratory direction:

* `note_stereo_analyzer.py`
* layer-level analysis;
* optional group config analysis;
* window-based pan / volume / density / instrument / pitch / rhythm reports;
* future stream-aware or high-precision note stereo layout.

Analyzer work must be read-only at first. It should not modify layout generation, writer output, or existing playback behavior.

---

## Coding Style

* Keep new modules focused and small.
* Prefer pure helper functions where possible.
* Avoid circular imports.
* New shared helpers should not import `layout.py`.
* Existing compatibility imports from `nbs2func.layout` should continue to work unless the task explicitly removes them.
* Add tests for new behavior.
* Do not silently broaden task scope.
