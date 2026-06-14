from __future__ import annotations

from dataclasses import dataclass

DIRECTION_VECTORS = {
    "east": (1, 0),
    "west": (-1, 0),
    "south": (0, 1),
    "north": (0, -1),
}

LEGACY_DIRECTIONS = {
    "x+": "east",
    "x-": "west",
    "z+": "south",
    "z-": "north",
}

OPPOSITE_DIRECTIONS = {
    "east": "west",
    "west": "east",
    "south": "north",
    "north": "south",
}


class LayoutError(ValueError):
    """Raised when a layout strategy cannot place a song."""


@dataclass(frozen=True)
class BlockPosition:
    """A Minecraft world block position."""

    x: int
    y: int
    z: int


def normalize_direction(direction: str) -> str:
    normalized = LEGACY_DIRECTIONS.get(direction, direction)
    if normalized not in DIRECTION_VECTORS:
        raise LayoutError(f"Unsupported direction: {direction}")
    return normalized


def opposite_direction(direction: str) -> str:
    normalized = normalize_direction(direction)
    return OPPOSITE_DIRECTIONS[normalized]


def add_vector(
    position: BlockPosition,
    direction_vector: tuple[int, int],
) -> BlockPosition:
    dx, dz = direction_vector
    return BlockPosition(position.x + dx, position.y, position.z + dz)


def add_y(position: BlockPosition, amount: int) -> BlockPosition:
    return BlockPosition(position.x, position.y + amount, position.z)


def below(position: BlockPosition) -> BlockPosition:
    return BlockPosition(position.x, position.y - 1, position.z)


def above(position: BlockPosition) -> BlockPosition:
    return BlockPosition(position.x, position.y + 1, position.z)


def repeater_position_from_note_position(
    note_position: BlockPosition,
    track_direction: str,
) -> BlockPosition:
    """Return the repeater position for the existing two-block cell geometry."""

    return add_vector(note_position, DIRECTION_VECTORS[normalize_direction(track_direction)])


def _scale_vector(vector: tuple[int, int], amount: int) -> tuple[int, int]:
    dx, dz = vector
    return dx * amount, dz * amount


def _right_hand_lateral_vector(track_direction: str) -> tuple[int, int]:
    dx, dz = DIRECTION_VECTORS[track_direction]
    return -dz, dx
