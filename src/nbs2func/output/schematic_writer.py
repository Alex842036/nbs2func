from __future__ import annotations

from pathlib import Path

import mcschematic

from ..core.minecraft_version import (
    DEFAULT_MINECRAFT_VERSION_PROFILE,
    MinecraftVersionProfile,
    get_minecraft_version_profile,
)
from ..layout.geometry import BlockPosition
from .models import GeneratedBuildPlan, PlacedBlock


def write_schematic(
    plan: GeneratedBuildPlan,
    output_path: str | Path,
    *,
    minecraft_version: str | None = None,
    schematic_origin: BlockPosition | tuple[int, int, int] | None = None,
    version_profile: MinecraftVersionProfile | None = None,
    schematic_name: str | None = None,
) -> Path:
    """Write structured block placements to a Sponge .schem file."""

    if version_profile is not None:
        profile = version_profile
    elif minecraft_version is not None:
        profile = get_minecraft_version_profile(minecraft_version)
    else:
        profile = DEFAULT_MINECRAFT_VERSION_PROFILE
    version = _mcschematic_version(profile)
    origin = _as_block_position(schematic_origin or BlockPosition(0, 0, 0))
    output_dir, name = _schematic_output_target(output_path, schematic_name)

    schematic = mcschematic.MCSchematic()
    for block in plan.blocks:
        schematic.setBlock(
            (block.x - origin.x, block.y - origin.y, block.z - origin.z),
            placed_block_to_block_data(block),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    schematic.save(str(output_dir), name, version)
    return output_dir / f"{name}.schem"


def placed_block_to_block_data(block: PlacedBlock) -> str:
    if block.nbt:
        return f"{block.block}{block.nbt}"
    return block.block


def schematic_warnings(plan: GeneratedBuildPlan) -> tuple[str, ...]:
    command_warnings = tuple(
        (
            f"Schematic output skipped non-block command from {command.source}: "
            f"{command.reason}"
        )
        for command in plan.commands
        if not command.schem_supported
    )
    return (*plan.warnings, *command_warnings)


def resolve_schematic_origin(
    plan: GeneratedBuildPlan,
    mode: str,
    generation_origin: BlockPosition,
) -> BlockPosition:
    if mode == "generation_origin":
        return generation_origin
    if mode == "min_corner":
        if not plan.blocks:
            return generation_origin
        return BlockPosition(
            min(block.x for block in plan.blocks),
            min(block.y for block in plan.blocks),
            min(block.z for block in plan.blocks),
        )
    raise ValueError(
        "Unsupported schematic_origin_mode: "
        f"{mode!r}. Expected generation_origin or min_corner."
    )


def _mcschematic_version(profile: MinecraftVersionProfile) -> mcschematic.Version:
    try:
        return getattr(mcschematic.Version, profile.mcschematic_version)
    except AttributeError as exc:
        raise ValueError(
            "mcschematic does not support configured Minecraft version enum "
            f"{profile.mcschematic_version!r} for profile {profile.version_id}."
        ) from exc


def _as_block_position(position: BlockPosition | tuple[int, int, int]) -> BlockPosition:
    if isinstance(position, BlockPosition):
        return position
    x, y, z = position
    return BlockPosition(x, y, z)


def _schematic_output_target(
    output_path: str | Path,
    schematic_name: str | None,
) -> tuple[Path, str]:
    path = Path(output_path)
    if path.suffix.lower() == ".schem":
        return path.parent, _schem_name(schematic_name or path.stem)
    return path, _schem_name(schematic_name or path.name or "nbs_song")


def _schem_name(name: str) -> str:
    raw = name[:-6] if name.lower().endswith(".schem") else name
    return raw or "nbs_song"
