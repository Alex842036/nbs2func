import tempfile
import unittest
from pathlib import Path

from nbs2func.output.command_writer import BasicMcfunctionWriter, CommandWriterConfig
from nbs2func.layout import (
    ActivationRail,
    ActivationSlot,
    BlockPosition,
    EmitterCandidate,
    LayoutCell,
    LayoutResult,
    NoteBasedStereoRailLayoutPreview,
    NoteEmitter,
    RailUsageStatistic,
    SlotAssignment,
)


class CommandWriterSplitTest(unittest.TestCase):
    def test_no_split_output_writes_single_file(self) -> None:
        layout = LayoutResult(
            mode="test",
            cells=(_cell(0),),
            notes=(),
            conflicts=(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "song.mcfunction"
            writer = BasicMcfunctionWriter(
                CommandWriterConfig(
                    split_functions=False,
                )
            )
            writer.write_file(layout, output_path)

            self.assertTrue(output_path.exists())
            self.assertFalse((Path(tmp_dir) / "data").exists())

    def test_player_tp_output_writes_window_functions(self) -> None:
        layout = LayoutResult(
            mode="test",
            cells=tuple(_cell(tick) for tick in range(4)),
            notes=(),
            conflicts=(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "song.mcfunction"
            result = BasicMcfunctionWriter(
                CommandWriterConfig(
                    split_functions=True,
                    max_commands_per_build_part=5,
                    build_player_name="Builder",
                    player_tp_chunk_load_wait_ticks=100,
                    player_tp_after_build_wait_ticks=20,
                    schedule_delay_ticks_between_parts=10,
                    function_namespace="nbs",
                    build_function_dir="build",
                )
            ).write_file(layout, output_path)

            build_dir = Path(tmp_dir) / "data" / "nbs" / "functions" / "build"
            window_dir = build_dir / "window_000"

            self.assertIsNotNone(result.player_tp_build)
            self.assertTrue((build_dir / "start.mcfunction").exists())
            self.assertTrue((build_dir / "done.mcfunction").exists())
            self.assertTrue((window_dir / "tp.mcfunction").exists())
            self.assertTrue((window_dir / "wait.mcfunction").exists())
            self.assertTrue((window_dir / "part_000.mcfunction").exists())
            self.assertTrue((window_dir / "done.mcfunction").exists())
            self.assertIn(
                "schedule function nbs:build/window_000/tp 1t",
                (build_dir / "start.mcfunction").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "tp Builder",
                (window_dir / "tp.mcfunction").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "schedule function nbs:build/window_000/wait 100t",
                (window_dir / "tp.mcfunction").read_text(encoding="utf-8"),
            )
            parts = sorted(window_dir.glob("part_*.mcfunction"))
            self.assertIn(
                "schedule function nbs:build/window_000/done 20t",
                parts[-1].read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "forceload",
                "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in build_dir.rglob("*.mcfunction")
                ),
            )
            for part in parts:
                self.assertLessEqual(_command_count(part), 5)

    def test_player_tp_output_schedules_next_window(self) -> None:
        layout = LayoutResult(
            mode="test",
            cells=tuple(_cell(tick) for tick in range(90)),
            notes=(),
            conflicts=(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "song.mcfunction"
            result = BasicMcfunctionWriter(
                CommandWriterConfig(
                    split_functions=True,
                    player_tp_window_length_blocks=32,
                    player_tp_window_lateral_width_blocks=192,
                    max_commands_per_build_part=500,
                    function_namespace="nbs",
                    build_function_dir="build",
                )
            ).write_file(layout, output_path)

            build_dir = Path(tmp_dir) / "data" / "nbs" / "functions" / "build"
            self.assertIsNotNone(result.player_tp_build)
            self.assertGreater(result.player_tp_build.total_windows, 1)
            self.assertEqual(result.player_tp_build.split_axis, "x")
            self.assertTrue((build_dir / "window_001" / "tp.mcfunction").exists())
            self.assertIn(
                "schedule function nbs:build/window_001/tp 1t",
                (build_dir / "window_000" / "done.mcfunction").read_text(
                    encoding="utf-8"
                ),
            )

    def test_cell_repeaters_are_written_with_delay_two(self) -> None:
        layout = LayoutResult(
            mode="test",
            cells=(_cell(0),),
            notes=(),
            conflicts=(),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(split_functions=False)
        ).write_text(layout)

        self.assertIn(
            "setblock 0 128 0 minecraft:repeater[facing=west,delay=2]",
            text,
        )

    def test_starter_repeaters_are_written_with_delay_two(self) -> None:
        layout = LayoutResult(
            mode="test",
            cells=(_cell(0),),
            notes=(),
            conflicts=(),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
            )
        ).write_text(layout)

        self.assertIn("minecraft:repeater[facing=west,delay=2]", text)

    def test_note_based_center_slot_writes_note_block_over_rail_center(self) -> None:
        layout = LayoutResult(
            mode="note_based_stereo_preview",
            cells=(),
            notes=(),
            conflicts=(),
            note_based_preview=_note_based_preview(
                (
                    _assignment(
                        rail_id="rail_4_0",
                        rail_offset_y=4,
                        rail_offset_lateral=0,
                        slot_index=0,
                        position=BlockPosition(0, 132, 0),
                    ),
                )
            ),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(split_functions=False)
        ).write_text(layout)

        self.assertIn("setblock 0 132 0 minecraft:note_block[note=12]", text)
        self.assertIn("setblock 0 131 0 minecraft:dirt", text)
        self.assertIn("setblock 1 132 0 minecraft:repeater[facing=west,delay=2]", text)
        self.assertIn("setblock 1 131 0 minecraft:stone", text)
        self.assertNotIn("setblock 0 132 0 minecraft:repeater", text)

    def test_note_based_side_slot_keeps_rail_repeater_and_writes_side_note(self) -> None:
        layout = LayoutResult(
            mode="note_based_stereo_preview",
            cells=(),
            notes=(),
            conflicts=(),
            note_based_preview=_note_based_preview(
                (
                    _assignment(
                        rail_id="rail_4_0",
                        rail_offset_y=4,
                        rail_offset_lateral=0,
                        slot_index=1,
                        position=BlockPosition(0, 132, 1),
                    ),
                )
            ),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(split_functions=False)
        ).write_text(layout)

        self.assertIn("setblock 1 132 0 minecraft:repeater[facing=west,delay=2]", text)
        self.assertIn("setblock 1 131 0 minecraft:stone", text)
        self.assertIn("setblock 0 132 0 minecraft:stone", text)
        self.assertIn("setblock 0 131 0 minecraft:stone", text)
        self.assertIn("setblock 0 132 1 minecraft:note_block[note=12]", text)

    def test_note_based_gravity_instrument_writes_support_before_instrument(self) -> None:
        layout = LayoutResult(
            mode="note_based_stereo_preview",
            cells=(),
            notes=(),
            conflicts=(),
            note_based_preview=_note_based_preview(
                (
                    _assignment(
                        rail_id="rail_4_0",
                        rail_offset_y=4,
                        rail_offset_lateral=0,
                        slot_index=0,
                        position=BlockPosition(0, 132, 0),
                        instrument=3,
                    ),
                )
            ),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(split_functions=False)
        ).write_text(layout)

        support_index = text.index("setblock 0 130 0 minecraft:stone")
        sand_index = text.index("setblock 0 131 0 minecraft:sand")
        note_index = text.index("setblock 0 132 0 minecraft:note_block")
        self.assertLess(support_index, sand_index)
        self.assertLess(sand_index, note_index)

    def test_note_based_starter_uses_fixed_cell_geometry(self) -> None:
        layout = LayoutResult(
            mode="note_based_stereo_preview",
            cells=(_note_based_cell(),),
            notes=(),
            conflicts=(),
            note_based_preview=_note_based_preview(
                (
                    _assignment(
                        rail_id="rail_4_0",
                        rail_offset_y=4,
                        rail_offset_lateral=0,
                        slot_index=0,
                        position=BlockPosition(0, 132, 0),
                    ),
                )
            ),
        )

        text = BasicMcfunctionWriter(
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
            )
        ).write_text(layout)

        self.assertIn("setblock -1 132 0 minecraft:repeater[facing=west,delay=2]", text)
        self.assertIn("setblock -2 131 0 minecraft:stone", text)
        self.assertIn("summon minecraft:armor_stand -2 132 0", text)


def _cell(tick: int) -> LayoutCell:
    x = tick * 2
    return LayoutCell(
        tick=tick,
        track_id="0",
        source_track_id=0,
        repeater_position=BlockPosition(x, 128, 0),
        repeater_facing="west",
        track_block_position=BlockPosition(x, 127, 0),
        note_block_position=BlockPosition(x - 1, 128, 0),
        instrument_block_position=BlockPosition(x - 1, 127, 0),
        note=None,
    )


def _note_based_cell() -> LayoutCell:
    return LayoutCell(
        tick=0,
        track_id="rail_4_0",
        source_track_id=0,
        repeater_position=BlockPosition(1, 132, 0),
        repeater_facing="west",
        track_block_position=BlockPosition(1, 131, 0),
        note_block_position=BlockPosition(0, 132, 0),
        instrument_block_position=BlockPosition(0, 131, 0),
    )


def _command_count(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def _note_based_preview(
    assignments: tuple[SlotAssignment, ...],
) -> NoteBasedStereoRailLayoutPreview:
    rails = {
        assignment.rail.rail_id: assignment.rail
        for assignment in assignments
    }
    rail_stats = tuple(
        RailUsageStatistic(
            rail_id=rail.rail_id,
            offset_y=rail.offset_y,
            offset_lateral=rail.offset_lateral,
            candidate_value=rail.candidate_value,
            active_cell_count=1,
            used_slot_count=sum(
                1
                for assignment in assignments
                if assignment.rail.rail_id == rail.rail_id
            ),
            average_used_slots_per_active_cell=1.0,
        )
        for rail in rails.values()
    )
    return NoteBasedStereoRailLayoutPreview(
        total_note_events=len(assignments),
        total_ideal_emitters=len(assignments),
        total_activation_rails=len(rails),
        unchanged_assignments=len(assignments),
        y_movement_assignments=0,
        z_movement_assignments=0,
        failed_assignment_count=0,
        average_movement_cost=0,
        max_movement_cost=0,
        average_used_slots_per_active_rail_cell=1,
        rail_usage_statistics=rail_stats,
        assignments=assignments,
        failed_emitters=(),
        origin=BlockPosition(0, 128, 0),
        track_direction="east",
        tick_spacing=2,
    )


def _assignment(
    rail_id: str,
    rail_offset_y: int,
    rail_offset_lateral: int,
    slot_index: int,
    position: BlockPosition,
    instrument: int = 0,
) -> SlotAssignment:
    rail = ActivationRail(
        rail_id=rail_id,
        offset_y=rail_offset_y,
        offset_lateral=rail_offset_lateral,
        candidate_value=1,
    )
    emitter = NoteEmitter(
        emitter_id=f"emitter_{slot_index}",
        track_id=0,
        layer=0,
        tick=0,
        instrument=instrument,
        key=45,
        final_volume=100,
        final_panning=100,
        ideal_position=position,
        ideal_offset_y=rail_offset_y,
        ideal_offset_lateral=rail_offset_lateral + slot_index,
    )
    slot = ActivationSlot(
        rail_id=rail_id,
        tick=0,
        slot_index=slot_index,
        position=position,
    )
    candidate = EmitterCandidate(
        emitter_id=emitter.emitter_id,
        position=position,
        offset_y=emitter.ideal_offset_y,
        offset_lateral=emitter.ideal_offset_lateral,
        rail_offset_y=rail_offset_y,
        rail_offset_lateral=rail_offset_lateral,
        slot_index=slot_index,
        level=0,
        cost=0,
        y_movement=0,
        lateral_movement=0,
    )
    return SlotAssignment(
        emitter=emitter,
        rail=rail,
        slot=slot,
        candidate=candidate,
    )


if __name__ == "__main__":
    unittest.main()
