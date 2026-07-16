# Known Issues And Preview Limitations

[English](known_issues.md) | [简体中文](zh-CN/known_issues.md)

`v0.1.1` is usable but experimental. Back up the target Minecraft
world before running generated build functions.

- `note_based_stereo` remains heuristic. Difficult songs may not produce an
  ideal arrangement.
- Very large songs may require substantial processing time and memory. The
  current layout generator is largely single-threaded, so total CPU utilization
  may appear low on multi-core systems.
- CPU-bound generation shares CPython's GIL with the Tkinter main thread, so the
  GUI may briefly appear unresponsive even when overall CPU utilization is low.
- There is no safe cancellation operation during generation.
- Closing during generation can terminate the daemon worker and leave incomplete
  output files. The GUI warns before closing.
- Simple-chain output does not load chunks or wait between function files. Keep
  the entire target area loaded.
- Player-tp output requires a valid online build player. Disconnecting, changing
  dimension, or interrupting commands can leave a partial build.
- The GUI is primarily tested on Windows. macOS/Linux GUI behavior is not fully
  verified.
- Open output folder is Windows-only in this preview.
- Schem-only output cannot include runtime-dependent starter or playback-assist
  behavior.
- Schematic files do not embed summoned armor stands or minecarts as live
  schematic entities. Runtime commands create them in datapack/both workflows.
- Existing nbs2func-generated build function files are replaced on regeneration.
  The GUI asks before reusing an existing datapack folder; the CLI overwrites
  automatically.
- Unsupported instruments or base blocks fail generation rather than silently
  falling back to another sound.
- Minecraft Bedrock Edition is not supported.
- Manual track/group arrangement is not implemented in this release.
- There is no interactive 2D/3D layout editor or preview.
- Server-assisted and RCON workflows are not implemented.

Tempo calculation is implemented. The default `report` mode only recommends a
tick rate; it does not change the world. `command` mode requires playback assist,
appropriate permissions, and the selected Carpet-compatible or vanilla backend.
Older supported profiles do not natively provide the 1.21.1 vanilla command
profile.

Before running `/function nbs:build/start`, confirm the selected exact Minecraft
profile, namespace/build path, configured player names, output location, and
required server permissions or mods.
