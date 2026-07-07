import tempfile
import unittest
from pathlib import Path

from nbs2func.output.command_writer import BasicMcfunctionWriter, CommandWriterConfig
from nbs2func.layout import (
    BasicLinearLayout,
    BlockPosition,
    LayoutCell,
    LayoutResult,
    PlacedNote,
    _detect_block_collisions,
)
from nbs2func.core.models import NoteEvent, Song, Track


class GravityInstrumentSupportTest(unittest.TestCase):
    def test_snare_generates_sand_and_gravity_support(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(3))
        cell = layout.cells[0]

        self.assertEqual(cell.gravity_support_block_position, BlockPosition(-1, 126, 0))

        text = BasicMcfunctionWriter(
            CommandWriterConfig(split_functions=False)
        ).write_text(layout)
        self.assertIn("setblock -1 127 0 minecraft:sand", text)
        self.assertIn("setblock -1 126 0 minecraft:stone", text)

    def test_non_gravity_instrument_has_no_extra_support(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))

        self.assertIsNone(layout.cells[0].gravity_support_block_position)

    def test_collision_detection_includes_gravity_support_block(self) -> None:
        support_cell = LayoutCell(
            tick=0,
            track_id="0",
            source_track_id=0,
            repeater_position=BlockPosition(0, 128, 0),
            repeater_facing="west",
            track_block_position=BlockPosition(0, 127, 0),
            note_block_position=BlockPosition(-1, 128, 0),
            instrument_block_position=BlockPosition(-1, 127, 0),
            gravity_support_block_position=BlockPosition(-1, 126, 0),
        )
        conflicting_cell = LayoutCell(
            tick=0,
            track_id="1",
            source_track_id=1,
            repeater_position=BlockPosition(-1, 126, 0),
            repeater_facing="west",
            track_block_position=BlockPosition(2, 127, 0),
            note_block_position=BlockPosition(1, 128, 0),
            instrument_block_position=BlockPosition(-1, 125, 0),
        )

        collisions = _detect_block_collisions((support_cell, conflicting_cell))

        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0].collision_type, "occupied_occupied")
        self.assertEqual(collisions[0].first_block_type, "gravity_support_block")
        self.assertEqual(collisions[0].second_block_type, "repeater")

    def test_occupied_blocks_at_same_position_are_hard_collision(self) -> None:
        first_cell = _empty_cell("0", repeater=BlockPosition(0, 128, 0))
        second_cell = _empty_cell("1", repeater=BlockPosition(0, 128, 0))

        collisions = _detect_block_collisions((first_cell, second_cell))

        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0].collision_type, "occupied_occupied")
        self.assertEqual(collisions[0].first_block_type, "repeater")
        self.assertEqual(collisions[0].second_block_type, "repeater")

    def test_block_above_note_block_is_reserved_air_collision(self) -> None:
        note_cell = _note_cell(
            "0",
            note_position=BlockPosition(0, 128, 0),
            repeater=BlockPosition(10, 128, 0),
        )
        blocking_cell = _empty_cell(
            "1",
            repeater=BlockPosition(20, 128, 0),
            track_block=BlockPosition(0, 129, 0),
        )

        collisions = _detect_block_collisions((note_cell, blocking_cell))

        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0].collision_type, "occupied_reserved_air")
        self.assertEqual(collisions[0].first_track_id, "1")
        self.assertEqual(collisions[0].first_block_type, "track_block")
        self.assertEqual(collisions[0].second_track_id, "0")
        self.assertEqual(collisions[0].second_block_type, "reserved_air")

    def test_shared_reserved_air_without_extra_block_is_not_reserved_air_collision(
        self,
    ) -> None:
        first_cell = _note_cell(
            "0",
            note_position=BlockPosition(0, 128, 0),
            repeater=BlockPosition(10, 128, 0),
        )
        second_cell = _note_cell(
            "1",
            note_position=BlockPosition(0, 128, 0),
            repeater=BlockPosition(20, 128, 0),
        )

        collisions = _detect_block_collisions((first_cell, second_cell))

        self.assertTrue(
            any(collision.collision_type == "occupied_occupied" for collision in collisions)
        )
        self.assertFalse(
            any(
                collision.collision_type == "occupied_reserved_air"
                for collision in collisions
            )
        )

    def test_adjacent_z_without_block_above_note_is_not_hard_collision(self) -> None:
        first_cell = _note_cell(
            "0",
            note_position=BlockPosition(0, 128, 0),
            repeater=BlockPosition(10, 128, 0),
        )
        second_cell = _note_cell(
            "1",
            note_position=BlockPosition(0, 128, 1),
            repeater=BlockPosition(20, 128, 1),
        )

        collisions = _detect_block_collisions((first_cell, second_cell))

        self.assertEqual(collisions, [])

    def test_split_output_writes_support_before_sand(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(3))

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "song.mcfunction"
            BasicMcfunctionWriter(
                CommandWriterConfig(
                    split_functions=True,
                    max_commands_per_build_part=4,
                )
            ).write_file(layout, output_path)

            build_dir = Path(tmp_dir) / "data" / "nbs" / "functions" / "build"
            text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted(build_dir.rglob("part_*.mcfunction"))
            )

        support_index = text.index("setblock -1 126 0 minecraft:stone")
        sand_index = text.index("setblock -1 127 0 minecraft:sand")
        self.assertLess(support_index, sand_index)


def _song_with_instrument(instrument: int) -> Song:
    return Song(
        name="Gravity support test",
        author="tests",
        length=1,
        tracks=(
            Track(
                id=0,
                name="Track 0",
                source_layer=0,
                notes=(
                    NoteEvent(
                        tick=0,
                        layer=0,
                        instrument=instrument,
                        key=45,
                    ),
                ),
            ),
        ),
    )


def _empty_cell(
    track_id: str,
    repeater: BlockPosition,
    track_block: BlockPosition | None = None,
) -> LayoutCell:
    return LayoutCell(
        tick=0,
        track_id=track_id,
        source_track_id=int(track_id),
        repeater_position=repeater,
        repeater_facing="west",
        track_block_position=track_block or BlockPosition(repeater.x, repeater.y - 1, repeater.z),
        note_block_position=BlockPosition(repeater.x - 1, repeater.y, repeater.z),
        instrument_block_position=BlockPosition(repeater.x - 1, repeater.y - 1, repeater.z),
    )


def _note_cell(
    track_id: str,
    note_position: BlockPosition,
    repeater: BlockPosition,
) -> LayoutCell:
    instrument_position = BlockPosition(
        note_position.x,
        note_position.y - 1,
        note_position.z,
    )
    return LayoutCell(
        tick=0,
        track_id=track_id,
        source_track_id=int(track_id),
        repeater_position=repeater,
        repeater_facing="west",
        track_block_position=BlockPosition(repeater.x, repeater.y - 1, repeater.z),
        note_block_position=note_position,
        instrument_block_position=instrument_position,
        note=PlacedNote(
            tick=0,
            track_id=track_id,
            source_track_id=int(track_id),
            layer=int(track_id),
            instrument=0,
            key=45,
            final_volume=100,
            final_panning=100,
            track_volume=100,
            track_panning=100,
            virtual_role=None,
            note_block_position=note_position,
            instrument_block_position=instrument_position,
        ),
    )


if __name__ == "__main__":
    unittest.main()
