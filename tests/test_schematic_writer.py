from pathlib import Path

from nbs2func.layout.geometry import BlockPosition
from nbs2func.output.models import GeneratedBuildPlan, GeneratedCommand, PlacedBlock
from nbs2func.output import schematic_writer
from nbs2func.output.schematic_writer import (
    placed_block_to_block_data,
    resolve_schematic_origin,
    schematic_warnings,
    write_schematic,
)


def test_write_schematic_writes_file(tmp_path: Path) -> None:
    plan = GeneratedBuildPlan(
        blocks=(
            PlacedBlock(100, 64, 100, "minecraft:stone"),
            PlacedBlock(101, 64, 100, "minecraft:repeater[delay=2,facing=west]"),
            PlacedBlock(
                102,
                64,
                100,
                "minecraft:command_block",
                nbt='{Command:"say hi"}',
            ),
        )
    )

    output = write_schematic(
        plan,
        tmp_path / "song.schem",
        version_profile=None,
        minecraft_version="1.16.5",
        schematic_origin=BlockPosition(100, 64, 100),
    )

    assert output == tmp_path / "song.schem"
    assert output.is_file()


def test_coordinate_conversion_and_block_data(monkeypatch, tmp_path: Path) -> None:
    instances = []

    class FakeSchematic:
        def __init__(self) -> None:
            self.blocks = []
            instances.append(self)

        def setBlock(self, position, block_data) -> None:
            self.blocks.append((position, block_data))

        def save(self, output_folder, schem_name, version) -> None:
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            Path(output_folder, f"{schem_name}.schem").write_bytes(b"fake")

    monkeypatch.setattr(schematic_writer.mcschematic, "MCSchematic", FakeSchematic)
    plan = GeneratedBuildPlan(
        blocks=(
            PlacedBlock(100, 64, 100, "minecraft:stone"),
            PlacedBlock(102, 65, 97, "minecraft:repeater[delay=2,facing=west]"),
            PlacedBlock(
                103,
                66,
                98,
                "minecraft:command_block",
                nbt='{Command:"say hi"}',
            ),
        )
    )

    output = write_schematic(
        plan,
        tmp_path,
        minecraft_version="1.16.5",
        schematic_origin=(100, 64, 100),
        schematic_name="coords",
    )

    assert output == tmp_path / "coords.schem"
    assert instances[0].blocks == [
        ((0, 0, 0), "minecraft:stone"),
        ((2, 1, -3), "minecraft:repeater[delay=2,facing=west]"),
        ((3, 2, -2), 'minecraft:command_block{Command:"say hi"}'),
    ]


def test_schematic_origin_modes() -> None:
    plan = GeneratedBuildPlan(
        blocks=(
            PlacedBlock(10, 70, 5, "minecraft:stone"),
            PlacedBlock(8, 72, 9, "minecraft:dirt"),
        )
    )
    generation_origin = BlockPosition(0, 64, 0)

    assert (
        resolve_schematic_origin(plan, "generation_origin", generation_origin)
        == generation_origin
    )
    assert resolve_schematic_origin(
        plan,
        "min_corner",
        generation_origin,
    ) == BlockPosition(8, 70, 5)


def test_schematic_warnings_skip_non_block_commands() -> None:
    plan = GeneratedBuildPlan(
        blocks=(PlacedBlock(0, 0, 0, "minecraft:stone"),),
        commands=(
            GeneratedCommand(
                "summon minecraft:armor_stand 0 0 0",
                source="starter.armor_stand",
                schem_supported=False,
                reason="armor stand marker entity is not included in .schem output",
            ),
        ),
    )

    assert schematic_warnings(plan) == (
        "Schematic output skipped non-block command from starter.armor_stand: "
        "armor stand marker entity is not included in .schem output",
    )


def test_placed_block_to_block_data_supports_inline_and_separate_nbt() -> None:
    assert (
        placed_block_to_block_data(
            PlacedBlock(0, 0, 0, "minecraft:repeater[delay=2,facing=west]")
        )
        == "minecraft:repeater[delay=2,facing=west]"
    )
    assert (
        placed_block_to_block_data(
            PlacedBlock(0, 0, 0, "minecraft:command_block", '{Command:"say hi"}')
        )
        == 'minecraft:command_block{Command:"say hi"}'
    )


def test_schematic_writer_does_not_parse_mcfunction_lines() -> None:
    source = Path(schematic_writer.__file__).read_text(encoding="utf-8")

    assert "command_writer" not in source
    assert "placed_block_to_setblock" not in source
    assert "_generated_plan_lines" not in source
