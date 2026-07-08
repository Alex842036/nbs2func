import unittest

from nbs2func.core.models import NoteEvent, Song, Track
from nbs2func.layout import BasicLinearLayout, BlockPosition
from nbs2func.layout.models import (
    ActivationRail,
    ActivationSlot,
    EmitterCandidate,
    LayoutResult,
    NoteBasedStereoRailLayoutPreview,
    NoteEmitter,
    RailUsageStatistic,
    SlotAssignment,
)
from nbs2func.output.block_builder import (
    RUNTIME_LOGIC_BUILD_PLAN,
    STRUCTURE_ONLY_BUILD_PLAN,
    STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN,
    build_generated_plan,
    filter_generated_plan,
)
from nbs2func.output.command_writer import (
    BasicMcfunctionWriter,
    CommandWriterConfig,
    placed_block_to_setblock,
)
from nbs2func.output.models import GeneratedBuildPlan, GeneratedCommand, PlacedBlock


class OutputModelsTest(unittest.TestCase):
    def test_output_models_represent_blocks_commands_and_warnings(self) -> None:
        normal = PlacedBlock(1, 2, 3, "minecraft:stone")
        state = PlacedBlock(4, 5, 6, "minecraft:repeater[delay=2,facing=west]")
        command_block = PlacedBlock(
            7,
            8,
            9,
            "minecraft:command_block",
            nbt='{Command:"say hi"}',
            source="test.command_block",
        )
        summon = GeneratedCommand(
            "summon minecraft:armor_stand 0 64 0",
            source="test.entity",
            schem_supported=False,
            reason="entity is not a schematic block",
        )

        plan = GeneratedBuildPlan(
            blocks=(normal, state, command_block),
            commands=(summon,),
            warnings=("entity is not a schematic block",),
        )

        self.assertEqual(plan.blocks[0].block, "minecraft:stone")
        self.assertIn("[delay=2", plan.blocks[1].block)
        self.assertEqual(
            placed_block_to_setblock(command_block),
            'setblock 7 8 9 minecraft:command_block{Command:"say hi"}',
        )
        self.assertEqual(plan.commands[0].command, "summon minecraft:armor_stand 0 64 0")
        self.assertEqual(plan.warnings, ("entity is not a schematic block",))


class BlockBuilderTest(unittest.TestCase):
    def test_basic_layout_generates_note_instrument_repeater_track_and_support(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(3))

        plan = build_generated_plan(
            layout,
            CommandWriterConfig(split_functions=False),
        )

        by_source = {block.source: block for block in plan.blocks}
        self.assertEqual(
            by_source["layout.cell.note_block"].block,
            "minecraft:note_block[note=12,instrument=snare]",
        )
        self.assertEqual(
            by_source["layout.cell.instrument_block"].block,
            "minecraft:sand",
        )
        self.assertEqual(
            by_source["layout.cell.gravity_support_block"].block,
            "minecraft:stone",
        )
        self.assertEqual(by_source["layout.cell.track_block"].block, "minecraft:stone")
        self.assertEqual(
            by_source["layout.cell.repeater"].block,
            "minecraft:repeater[facing=west,delay=2]",
        )

    def test_note_block_instrument_state_matches_base_block(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(7))

        plan = build_generated_plan(
            layout,
            CommandWriterConfig(split_functions=False),
        )

        by_source = {block.source: block for block in plan.blocks}
        self.assertEqual(
            by_source["layout.cell.note_block"].block,
            "minecraft:note_block[note=12,instrument=bell]",
        )
        self.assertEqual(
            by_source["layout.cell.instrument_block"].block,
            "minecraft:gold_block",
        )

    def test_starter_plan_keeps_blocks_and_entity_command_separate(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))

        plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
            ),
        )

        self.assertTrue(any(block.source == "starter.repeater" for block in plan.blocks))
        self.assertTrue(
            any(block.source == "starter.command_block" for block in plan.blocks)
        )
        armor_stand_commands = [
            command
            for command in plan.commands
            if command.source == "starter.armor_stand"
        ]
        self.assertEqual(len(armor_stand_commands), 1)
        self.assertIn("summon minecraft:armor_stand", armor_stand_commands[0].command)
        self.assertIn("entity", armor_stand_commands[0].reason)
        self.assertIn("starter armor stand marker", plan.warnings[0])

    def test_playback_assist_plan_keeps_command_block_nbt(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))

        plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_playback_assist=True,
            ),
        )

        command_blocks = [
            block
            for block in plan.blocks
            if block.source.startswith("playback_assist")
            and "command_block" in block.source
        ]
        self.assertTrue(command_blocks)
        self.assertTrue(any("{Command:" in block.block for block in command_blocks))
        self.assertTrue(
            any(
                block.block.startswith("minecraft:chain_command_block")
                for block in command_blocks
            )
        )
        self.assertTrue(
            any(block.source.endswith("_button") for block in plan.blocks)
        )
        self.assertTrue(
            any(
                command.source == "playback_assist.scoreboard_objective"
                for command in plan.commands
            )
        )

    def test_structure_only_plan_excludes_starter_and_playback_blocks(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))
        full_plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
                enable_playback_assist=True,
            ),
        )

        plan = filter_generated_plan(full_plan, STRUCTURE_ONLY_BUILD_PLAN)

        self.assertTrue(plan.blocks)
        self.assertFalse(
            any(block.source.startswith("starter.") for block in plan.blocks)
        )
        self.assertFalse(
            any(block.source.startswith("playback_assist.") for block in plan.blocks)
        )
        self.assertEqual(plan.commands, ())

    def test_both_mode_schematic_plan_includes_module_command_blocks(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))
        full_plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
                enable_playback_assist=True,
            ),
        )

        plan = filter_generated_plan(full_plan, STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN)

        self.assertTrue(any(block.source.startswith("layout.") for block in plan.blocks))
        self.assertTrue(
            any(
                block.source.startswith("playback_assist.")
                and "command_block" in block.source
                and "{Command:" in block.block
                for block in plan.blocks
            )
        )
        self.assertEqual(plan.commands, ())

    def test_runtime_logic_plan_excludes_all_blocks(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))
        full_plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
                enable_playback_assist=True,
            ),
        )

        plan = filter_generated_plan(full_plan, RUNTIME_LOGIC_BUILD_PLAN)

        self.assertEqual(plan.blocks, ())
        self.assertTrue(
            any(command.source == "starter.armor_stand" for command in plan.commands)
        )
        self.assertTrue(
            any(
                command.source == "playback_assist.scoreboard_objective"
                for command in plan.commands
            )
        )

    def test_command_writer_uses_structured_playback_plan(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))

        text = BasicMcfunctionWriter(
            CommandWriterConfig(
                split_functions=False,
                enable_playback_assist=True,
            )
        ).write_text(layout)

        self.assertIn("summon minecraft:minecart", text)
        self.assertIn("minecraft:command_block{Command:", text)
        self.assertIn("minecraft:chain_command_block", text)
        self.assertIn("minecraft:stone_button[face=floor,facing=east]", text)

    def test_command_writer_runtime_plan_omits_setblock_layer(self) -> None:
        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            selected_track_id=0,
        ).layout_song(_song_with_instrument(0))
        full_plan = build_generated_plan(
            layout,
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
                enable_playback_assist=True,
            ),
        )
        runtime_plan = filter_generated_plan(full_plan, RUNTIME_LOGIC_BUILD_PLAN)

        text = BasicMcfunctionWriter(
            CommandWriterConfig(
                split_functions=False,
                enable_starter_module=True,
                enable_playback_assist=True,
            )
        ).write_text(layout, plan=runtime_plan)

        self.assertNotIn("setblock", text)
        self.assertNotIn("command_block", text)
        self.assertIn("scoreboard objectives add", text)
        self.assertIn("summon minecraft:armor_stand", text)

    def test_note_based_block_plan_progress_uses_rail_tick_cells(self) -> None:
        layout = LayoutResult(
            mode="note_based_stereo",
            cells=(),
            notes=(),
            conflicts=(),
            note_based_preview=_note_based_preview_with_ticks((0, 3)),
        )
        events: list[tuple[int, int]] = []

        build_generated_plan(
            layout,
            CommandWriterConfig(split_functions=False),
            progress_callback=lambda current, total: events.append((current, total)),
        )

        self.assertEqual(events[0], (0, 4))
        self.assertIn((1, 4), events)
        self.assertIn((2, 4), events)
        self.assertIn((3, 4), events)
        self.assertEqual(events[-1], (4, 4))


def _song_with_instrument(instrument: int) -> Song:
    return Song(
        name="Builder test",
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


def _note_based_preview_with_ticks(
    ticks: tuple[int, ...],
) -> NoteBasedStereoRailLayoutPreview:
    assignments = tuple(_note_based_assignment(tick, index) for index, tick in enumerate(ticks))
    rail = assignments[0].rail
    return NoteBasedStereoRailLayoutPreview(
        total_note_events=len(assignments),
        total_ideal_emitters=len(assignments),
        total_activation_rails=1,
        unchanged_assignments=len(assignments),
        y_movement_assignments=0,
        z_movement_assignments=0,
        failed_assignment_count=0,
        average_movement_cost=0,
        max_movement_cost=0,
        average_used_slots_per_active_rail_cell=1,
        rail_usage_statistics=(
            RailUsageStatistic(
                rail_id=rail.rail_id,
                offset_y=rail.offset_y,
                offset_lateral=rail.offset_lateral,
                candidate_value=rail.candidate_value,
                active_cell_count=len(ticks),
                used_slot_count=len(ticks),
                average_used_slots_per_active_cell=1,
            ),
        ),
        assignments=assignments,
        failed_emitters=(),
        origin=BlockPosition(0, 128, 0),
        track_direction="east",
        tick_spacing=2,
    )


def _note_based_assignment(tick: int, slot_index: int) -> SlotAssignment:
    rail = ActivationRail(
        rail_id="rail_0_0",
        offset_y=0,
        offset_lateral=0,
        candidate_value=1,
    )
    position = BlockPosition(tick * 2, 128, slot_index)
    emitter = NoteEmitter(
        emitter_id=f"emitter_{slot_index}",
        track_id=0,
        layer=0,
        tick=tick,
        instrument=0,
        key=45,
        final_volume=100,
        final_panning=100,
        ideal_position=position,
        ideal_offset_y=0,
        ideal_offset_lateral=slot_index,
    )
    slot = ActivationSlot(
        rail_id=rail.rail_id,
        tick=tick,
        slot_index=slot_index,
        position=position,
    )
    candidate = EmitterCandidate(
        emitter_id=emitter.emitter_id,
        position=position,
        offset_y=0,
        offset_lateral=slot_index,
        rail_offset_y=0,
        rail_offset_lateral=0,
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
