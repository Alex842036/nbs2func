# Architecture

nbs2func is organized as a small pipeline:

1. `core/nbs_reader.py` parses `.nbs` data into project models.
2. `core/models.py` defines `Song`, `Track`, and `NoteEvent`.
3. `layout/` converts notes into positioned layout cells or note-based rail
   preview assignments.
4. `core/instrument_mapping.py` maps NBS/Minecraft instruments to note block support
   blocks and gravity support rules.
5. `output/command_writer.py` writes Minecraft functions from a `LayoutResult`.
6. `modules/playback_assist.py` optionally generates a minecart-based playback
   helper for in-world testing.

The important boundary is that layout code decides coordinates, while command
writing decides Minecraft command text and block IDs.
