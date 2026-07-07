# Architecture

nbs2func is organized as a small pipeline:

1. `core/nbs_reader.py` parses `.nbs` data into project models.
2. `core/models.py` defines `Song`, `Track`, and `NoteEvent`.
3. `layout/` converts notes into positioned layout cells or note-based rail
   preview assignments.
4. `core/instrument_mapping.py` maps NBS/Minecraft instruments to note block support
   blocks and gravity support rules.
5. `output/block_builder.py` converts layout data into structured final block
   placements shared by output formats.
6. `output/command_writer.py` writes Minecraft functions from the structured
   build plan.
7. `output/schematic_writer.py` writes `.schem` files from the same block
   placement data.
8. `modules/playback_assist.py` optionally generates a minecart-based playback
   helper for in-world testing.

The important boundary is that layout code decides coordinates, while command
output code decides final block data and serializes it to the selected format.
