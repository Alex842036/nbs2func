# Layout Modes

## basic_linear

Generates one selected NBS track as a simple straight line. This is useful for
small tests and for validating NBS parsing.

## track_based_stereo

Assigns each NBS layer/track a stable fixed offset based on layer volume and
stereo. It is easier to build than note-level stereo and includes whole-track
collision avoidance.

## note_based_stereo

Experimental traditional redstone rail layout. Each note computes a volume and
pan based target, then assigns an emitter to an activation rail slot. This mode
has successfully generated and played large 30k / 40k note block NBS tests, but
it is still preview-quality and may need tuning per song.

## Build Output

The default split output uses player-tp build windows:

1. Teleport the configured build player to a window center.
2. Wait for chunks to load.
3. Run several scheduled build parts.
4. Move to the next window.

Use `--no-split-functions` for small single-file debugging.
