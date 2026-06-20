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

## Branch Policy

Default active development branch for core generator work is `main`.

Use `main` for:

* bug fixes;
* low-risk performance optimization;
* note-based stereo generation stability;
* rail assignment / rail center upgrade fixes;
* candidate generation optimization;
* output-preserving refactors.

Use a feature branch only for exploratory or potentially disruptive work, such as:

* new analyzer experiments;
* full virtual rail architecture prototypes;
* best-first candidate traversal;
* major public API changes;
* experimental layout modes.

Before switching branches or creating a branch:

```bash
git status
git branch --show-current
```

If the working tree is not clean, stop and report the status unless the user explicitly says to continue.

Do not run these commands unless the user explicitly asks:

```bash
git add
git commit
git push
git reset --hard
git clean
```

---

## Current Performance Focus

The current priority is optimizing the main generation path for large `.nbs` files.

Primary target:

* `NoteBasedStereoLayout`
* `NoteBasedStereoRailLayout`
* rail assignment performance
* rail center upgrade performance
* candidate generation performance
* large NBS debug/performance reporting

Large NBS reports currently show that the main bottlenecks are:

1. `rail center upgrade time`, especially when side-only rail cells are later upgraded to center note cells;
2. candidate generation after geometry skeleton caching, especially concrete candidate materialization, scoring, sorting, and truncation;
3. retry / Pass 2 behavior on dense songs.

The immediate priority is not analyzer work. Analyzer modules remain useful for future layout quality work, but they are currently lower priority than main generator performance.

---

## Active Optimization Queue

Prefer this order unless the user explicitly changes it:

1. Remove full `_FootprintOccupancy` copy from rail center upgrade.

   * Do not copy the whole occupancy map for each upgrade attempt.
   * Use local transaction / rollback logic around only the affected rail center and below-center positions.
   * Preserve collision, reserved-air, support block, center slot, side slot, and writer output semantics.

2. Re-test large NBS performance after the rail center upgrade fix.

   * Compare `rail center upgrade time`.
   * Compare `assignment total time`.
   * Compare total layout time.
   * Report whether full virtual rail architecture is still necessary.

3. Optimize candidate generation after geometry skeleton cache.

   * Keep geometry skeleton cache exact, not approximate.
   * Consider lazy concrete candidate materialization:

     * compute lightweight sort keys first;
     * select top K skeleton references;
     * materialize full `EmitterCandidate` objects only for retained candidates.
   * Consider scored top-K skeleton-index cache only after lazy materialization is measured.

4. Consider full virtual rail architecture only if local rail center upgrade repair is still insufficient.

   * Full virtual rail cell state is a medium/high-risk refactor.
   * Do not implement it in the same task as candidate pipeline changes.
   * Evaluate based on measured post-fix performance.

5. Consider best-first candidate traversal only after lower-risk candidate optimizations.

   * This changes raw candidate traversal logic.
   * It is higher risk than lazy materialization or scored top-K cache.

---

## Main Generator Stability Rules

Do not modify these unless the task explicitly asks for it:

* collision detection semantics;
* footprint / reserved-air rules;
* support block behavior;
* final pan formula;
* pan-zone / angle-zone thresholds;
* depth mirror behavior;
* depth==0 fallback behavior;
* note-based candidate scoring;
* candidate sorting order;
* candidate truncation semantics;
* assignment retry behavior;
* player-tp build scheduling;
* minecart playback assist timing;
* generated command format;
* datapack folder structure.

Performance optimizations should preserve generated output unless the task explicitly allows behavior changes.

When changing performance-sensitive code, add or preserve diagnostics for:

* total layout time;
* candidate generation time;
* assignment total time;
* retry total time;
* rail center upgrade time;
* rail validation time;
* footprint collision time;
* candidate count before / after truncation;
* geometry skeleton cache hit / miss / unique key count;
* rail center upgrade attempted / accepted / rejected;
* local rollback count if rail center upgrade uses transaction logic.

---

## Current Development Direction

The current development direction is no longer primarily analyzer exploration.

Current focus:

* make large `.nbs` generation complete within practical time;
* reduce pathological assignment costs;
* keep note-based stereo output stable;
* isolate high-risk architectural changes behind measured evidence;
* prefer small, measurable performance fixes before large refactors.

Analyzer work remains read-only and lower priority unless the user explicitly asks to resume it.

Potential future work:

* full virtual rail architecture;
* candidate lazy materialization;
* scored top-K skeleton-index cache;
* best-first candidate traversal;
* stream-aware or high-precision note stereo layout.

Do not silently broaden a task from a local performance fix into a full architecture rewrite.
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

## Coding Style

* Keep new modules focused and small.
* Prefer pure helper functions where possible.
* Avoid circular imports.
* New shared helpers should not import `layout.py`.
* Existing compatibility imports from `nbs2func.layout` should continue to work unless the task explicitly removes them.
* Add tests for new behavior.
* Do not silently broaden task scope.
