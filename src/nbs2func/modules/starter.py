from __future__ import annotations

from dataclasses import dataclass

from ..layout.geometry import (
    DIRECTION_VECTORS,
    BlockPosition,
    below,
    opposite_direction,
)
from ..layout.models import LayoutCell, LayoutResult
from ..core.minecraft_version import (
    DEFAULT_MINECRAFT_VERSION_PROFILE,
    MinecraftVersionError,
    MinecraftVersionProfile,
)


@dataclass(frozen=True)
class StarterModuleConfig:
    """Optional commands for starting every generated track at the same time."""

    enable_starter_module: bool = False
    emit_command_block: bool = True
    command_block_position: BlockPosition = BlockPosition(-10, 128, 0)
    starter_tag: str = "nbs_starter"
    starter_track_block: str | None = None
    starter_cell_offset: int = -1
    minecraft_version_profile: MinecraftVersionProfile = (
        DEFAULT_MINECRAFT_VERSION_PROFILE
    )


@dataclass(frozen=True)
class StarterCell:
    """A non-musical cell placed before a track's first normal layout cell."""

    track_id: str
    source_track_id: int
    repeater_position: BlockPosition
    repeater_facing: str
    track_block_position: BlockPosition
    starter_power_position: BlockPosition
    starter_track_block_position: BlockPosition


def starter_module_lines(
    layout: LayoutResult,
    config: StarterModuleConfig,
    default_track_block: str,
    repeater_block: str,
) -> list[str]:
    """Return mcfunction lines for the optional starter module."""

    if not config.enable_starter_module:
        return []
    if not config.minecraft_version_profile.supports_starter_module:
        raise MinecraftVersionError(
            "Starter module is not supported for Minecraft Java "
            f"{config.minecraft_version_profile.version_id} by the current "
            "version profile. Disable starter module or choose a supported "
            "target version."
        )

    starter_track_block = config.starter_track_block or default_track_block
    cells = _starter_cells(layout, config)
    if not cells:
        return []

    lines = [
        "# Starter module",
        "# Places one starter marker per track and a command block that powers all markers.",
    ]

    for cell in cells:
        lines.extend(
            [
                f"# starter track={cell.track_id}",
                _setblock(cell.track_block_position, starter_track_block),
                _setblock(
                    cell.repeater_position,
                    f"{repeater_block}[facing={cell.repeater_facing},delay=2]",
                ),
                _setblock(cell.starter_track_block_position, starter_track_block),
                _summon_starter_armor_stand(
                    cell.starter_power_position,
                    config.starter_tag,
                ),
                "",
            ]
        )

    if config.emit_command_block:
        starter_command = (
            "execute as "
            f"@e[type=minecraft:armor_stand,tag={config.starter_tag}] "
            "at @s run setblock ~ ~ ~ minecraft:redstone_block"
        )
        lines.extend(
            [
                "# starter command block",
                _setblock(
                    config.command_block_position,
                    f"command_block{{Command:{_nbt_string(starter_command)}}}",
                ),
                "",
            ]
        )
    return lines


def _starter_cells(
    layout: LayoutResult,
    config: StarterModuleConfig,
) -> tuple[StarterCell, ...]:
    cells_by_track: dict[str, list[LayoutCell]] = {}
    for cell in layout.cells:
        cells_by_track.setdefault(cell.track_id, []).append(cell)

    starter_cells: list[StarterCell] = []
    for track_cells in cells_by_track.values():
        sorted_cells = sorted(track_cells, key=lambda cell: cell.tick)
        first_cell = sorted_cells[0]
        step = _cell_step(sorted_cells)
        offset = _scale_3d_vector(step, config.starter_cell_offset)

        repeater_position = _shift_position(first_cell.repeater_position, offset)
        starter_power_position = _shift_position(
            first_cell.note_block_position,
            offset,
        )

        starter_cells.append(
            StarterCell(
                track_id=first_cell.track_id,
                source_track_id=first_cell.source_track_id,
                repeater_position=repeater_position,
                repeater_facing=first_cell.repeater_facing,
                track_block_position=below(repeater_position),
                starter_power_position=starter_power_position,
                starter_track_block_position=below(starter_power_position),
            )
        )

    return tuple(starter_cells)


def _cell_step(cells: list[LayoutCell]) -> tuple[int, int, int]:
    if len(cells) >= 2:
        first = cells[0].repeater_position
        second = cells[1].repeater_position
        return second.x - first.x, second.y - first.y, second.z - first.z

    track_direction = opposite_direction(cells[0].repeater_facing)
    dx, dz = DIRECTION_VECTORS[track_direction]
    return dx * 2, 0, dz * 2


def _shift_position(
    position: BlockPosition,
    offset: tuple[int, int, int],
) -> BlockPosition:
    dx, dy, dz = offset
    return BlockPosition(position.x + dx, position.y + dy, position.z + dz)


def _scale_3d_vector(
    vector: tuple[int, int, int],
    amount: int,
) -> tuple[int, int, int]:
    dx, dy, dz = vector
    return dx * amount, dy * amount, dz * amount


def _summon_starter_armor_stand(position: BlockPosition, tag: str) -> str:
    return (
        "summon minecraft:armor_stand "
        f"{position.x} {position.y} {position.z} "
        f"{{Tags:[{_nbt_string(tag)}],Invisible:1b,Marker:1b,NoGravity:1b}}"
    )


def _setblock(position: BlockPosition, block: str) -> str:
    return f"setblock {position.x} {position.y} {position.z} {_block_id(block)}"


def _block_id(block: str) -> str:
    if block.startswith("minecraft:"):
        return block
    return f"minecraft:{block}"


def _nbt_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
