# Known Issues

- `note_based_stereo` is still preview-quality and heuristic.
- Large NBS files can take minutes to generate.
- Large generated structures can take time to build in-game.
- The split build mode teleports the configured build player between build windows.
- Unsupported target-version instruments cause generation to fail; there is no silent fallback.
- The project currently targets Minecraft Java Edition only, not Bedrock Edition.
- Song tempo adaptation is not implemented yet. The generated redstone timing currently assumes the project's fixed playback timing model and does not automatically adjust the Minecraft tick rate to match every `.nbs` song tempo. Future versions may add tempo support through `starter_module` or `playback_assist_module`: older target versions may use Carpet Mod's `/tick rate` command, while newer Minecraft versions may use the vanilla `/tick rate` command where available. This is not automatic in the current preview.

