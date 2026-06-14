# AGENTS.md

## Project Goal

nbs2func converts NBS songs into Minecraft Java Edition mcfunction/datapack
redstone music structures.

The project is currently in `v0.1.0-preview`. Prefer small, low-risk changes that
preserve generated command output unless a task explicitly asks for behavior changes.

## Main Modules

- `src/nbs2func/nbs_reader.py`: reads NBS files into internal song models.
- `src/nbs2func/models.py`: shared song, track, and note data models.
- `src/nbs2func/layout.py`: layout strategies and placement validation.
  - `BasicLinearLayout`
  - `TrackBasedStereoLayout`
  - `NoteBasedStereoLayout`
  - geometry, pan/angle, collision, and note-based preview helpers
- `src/nbs2func/command_writer.py`: writes mcfunction/datapack build output.
- `src/nbs2func/playback_assist_module.py`: optional playback assist module.
- `src/nbs2func/starter_module.py`: optional starter module.
- `src/nbs2func/cli.py`: command-line entry point and debug reporting.

## Important Rules

- Do not modify collision detection unless the task explicitly asks for it.
- Do not modify final pan or angle zone algorithms unless explicitly requested.
- Do not default to running large NBS tests or expensive fixture runs.
- Prefer small, incremental edits over whole-repository refactors.
- Keep `BasicLinearLayout`, `TrackBasedStereoLayout`, and
  `NoteBasedStereoLayout` behavior stable unless a task asks otherwise.
- Do not change test expected output as part of structural cleanup.

## Current Stable Conventions

- Default build mode uses `player_tp`.
- Playback Assist uses minecart entities, not pigs.
- Minecraft Java 1.16.5 datapacks use `pack_format = 6`.

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

## Layout Cleanup Notes

`layout.py` is still intentionally monolithic during preview stabilization. When
splitting it later, move the lowest-risk pure helpers first, then update imports
in small steps with full test runs between changes.
