import unittest

from nbs2func.core.models import NoteEvent, Song, Track
from nbs2func.layout import BasicLinearLayout, BlockPosition
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


if __name__ == "__main__":
    unittest.main()
