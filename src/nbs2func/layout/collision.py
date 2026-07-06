from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..core.instrument_mapping import get_instrument_block, is_gravity_block
from .geometry import BlockPosition, above, below
from .models import (
    BlockCollision,
    CollisionExample,
    CollisionSummary,
    LayoutCell,
    TrackLayoutInfo,
)
from ..core.models import NoteEvent


@dataclass(frozen=True)
class _Footprint:
    occupied: tuple[tuple[BlockPosition, str], ...]
    reserved_air: tuple[tuple[BlockPosition, str], ...] = ()


@dataclass
class _FootprintOccupancy:
    occupied: dict[BlockPosition, list[str]]
    reserved_air: dict[BlockPosition, list[str]]


class _CollisionLimitReached(Exception):
    pass


def _detect_block_collisions(cells: tuple[LayoutCell, ...]) -> list[BlockCollision]:
    occupied_entries: list[tuple[BlockPosition, str, str, int]] = []
    reserved_entries: list[tuple[BlockPosition, str, str, int]] = []

    for cell in cells:
        for position, block_type in _cell_occupied_blocks(cell):
            occupied_entries.append((position, block_type, cell.track_id, cell.tick))
        for position, block_type in _cell_reserved_air_blocks(cell):
            reserved_entries.append((position, block_type, cell.track_id, cell.tick))

    return _detect_footprint_entry_collisions(occupied_entries, reserved_entries)


def _detect_footprint_entry_collisions(
    occupied_entries: list[tuple[BlockPosition, str, str, int]],
    reserved_air_entries: list[tuple[BlockPosition, str, str, int]],
) -> list[BlockCollision]:
    collisions, _ = _detect_footprint_entry_collisions_limited(
        occupied_entries,
        reserved_air_entries,
        max_records=None,
        max_total_records_before_abort=None,
    )
    return collisions


def _detect_footprint_entry_collisions_limited(
    occupied_entries: list[tuple[BlockPosition, str, str, int]],
    reserved_air_entries: list[tuple[BlockPosition, str, str, int]],
    max_records: int | None,
    max_total_records_before_abort: int | None,
) -> tuple[list[BlockCollision], int]:
    occupied: dict[BlockPosition, list[tuple[str, str, int]]] = {}
    reserved_air: dict[BlockPosition, list[tuple[str, str, int]]] = {}
    collisions: list[BlockCollision] = []
    skipped = 0
    total_seen = 0

    def append_collision(collision: BlockCollision) -> None:
        nonlocal skipped, total_seen
        total_seen += 1
        if (
            max_total_records_before_abort is not None
            and total_seen > max_total_records_before_abort
        ):
            skipped += 1
            raise _CollisionLimitReached
        if max_records is not None and len(collisions) >= max_records:
            skipped += 1
            return
        collisions.append(collision)

    try:
        for position, block_type, track_id, tick in occupied_entries:
            previous_blocks = occupied.get(position, [])
            compatible = all(
                _can_share_position(previous_block_type, block_type)
                for previous_block_type, _, _ in previous_blocks
            )
            if not compatible:
                previous_block_type, previous_track_id, previous_tick = previous_blocks[0]
                append_collision(
                    BlockCollision(
                        position=position,
                        first_block_type=previous_block_type,
                        first_track_id=previous_track_id,
                        first_tick=previous_tick,
                        second_block_type=block_type,
                        second_track_id=track_id,
                        second_tick=tick,
                        collision_type="occupied_occupied",
                    )
                )
                continue

            for reserved_block_type, reserved_track_id, reserved_tick in reserved_air.get(
                position,
                [],
            ):
                append_collision(
                    BlockCollision(
                        position=position,
                        first_block_type=block_type,
                        first_track_id=track_id,
                        first_tick=tick,
                        second_block_type=reserved_block_type,
                        second_track_id=reserved_track_id,
                        second_tick=reserved_tick,
                        collision_type="occupied_reserved_air",
                    )
                )

            occupied.setdefault(position, []).append((block_type, track_id, tick))

        for position, reserved_block_type, track_id, tick in reserved_air_entries:
            for block_type, block_track_id, block_tick in occupied.get(position, []):
                append_collision(
                    BlockCollision(
                        position=position,
                        first_block_type=block_type,
                        first_track_id=block_track_id,
                        first_tick=block_tick,
                        second_block_type=reserved_block_type,
                        second_track_id=track_id,
                        second_tick=tick,
                        collision_type="occupied_reserved_air",
                    )
                )

            reserved_air.setdefault(position, []).append(
                (reserved_block_type, track_id, tick)
            )
    except _CollisionLimitReached:
        pass

    return collisions, skipped


def _footprint_collides(
    occupied: Any,
    footprint: Any,
) -> bool:
    for position, block_type in footprint.occupied:
        previous_block_types = occupied.occupied.get(position, ())
        if any(
            not _can_share_position(previous_block_type, block_type)
            for previous_block_type in previous_block_types
        ):
            return True
        if position in occupied.reserved_air:
            return True

    for position, _ in footprint.reserved_air:
        if position in occupied.occupied:
            return True

    return False


def _first_footprint_collision(
    first: Any,
    second: Any,
) -> BlockPosition | None:
    second_occupied: dict[BlockPosition, list[str]] = defaultdict(list)
    second_reserved: set[BlockPosition] = set()

    for position, block_type in second.occupied:
        second_occupied[position].append(block_type)
    for position, _ in second.reserved_air:
        second_reserved.add(position)

    for position, block_type in first.occupied:
        if any(
            not _can_share_position(previous_block_type, block_type)
            for previous_block_type in second_occupied.get(position, ())
        ):
            return position
        if position in second_reserved:
            return position

    first_reserved = {position for position, _ in first.reserved_air}
    for position in first_reserved:
        if position in second_occupied:
            return position

    return None


def _occupy_footprint(
    occupied: _FootprintOccupancy,
    footprint: _Footprint,
) -> None:
    for position, block_type in footprint.occupied:
        occupied.occupied.setdefault(position, []).append(block_type)
    for position, block_type in footprint.reserved_air:
        occupied.reserved_air.setdefault(position, []).append(block_type)


def _copy_footprint_occupancy(
    occupancy: _FootprintOccupancy,
) -> _FootprintOccupancy:
    return _FootprintOccupancy(
        occupied={
            position: list(block_types)
            for position, block_types in occupancy.occupied.items()
        },
        reserved_air={
            position: list(block_types)
            for position, block_types in occupancy.reserved_air.items()
        },
    )


def _replace_footprint_occupancy(
    target: _FootprintOccupancy,
    source: _FootprintOccupancy,
) -> None:
    target.occupied.clear()
    target.occupied.update(
        {position: list(block_types) for position, block_types in source.occupied.items()}
    )
    target.reserved_air.clear()
    target.reserved_air.update(
        {
            position: list(block_types)
            for position, block_types in source.reserved_air.items()
        }
    )


def _cell_occupied_blocks(cell: Any) -> tuple[tuple[BlockPosition, str], ...]:
    if cell.note is None:
        note_block_type = "track_block"
        instrument_block_type = "track_block"
    else:
        note_block_type = "note_block"
        instrument_block_type = "instrument_block"

    blocks = [
        (cell.track_block_position, "track_block"),
        (cell.repeater_position, "repeater"),
        (cell.note_block_position, note_block_type),
        (cell.instrument_block_position, instrument_block_type),
    ]
    if cell.gravity_support_block_position is not None:
        blocks.insert(3, (cell.gravity_support_block_position, "gravity_support_block"))

    return tuple(blocks)


def _cell_reserved_air_blocks(cell: Any) -> tuple[tuple[BlockPosition, str], ...]:
    if cell.note is None:
        return ()

    return ((above(cell.note_block_position), "reserved_air"),)


def _can_share_position(first_block_type: str, second_block_type: str) -> bool:
    support_blocks = {"track_block", "gravity_support_block"}
    return first_block_type in support_blocks and second_block_type in support_blocks


def _gravity_support_position(
    instrument_block_position: BlockPosition,
    note: NoteEvent | None,
) -> BlockPosition | None:
    if note is None:
        return None

    instrument_block = get_instrument_block(note.instrument)
    if not is_gravity_block(instrument_block):
        return None

    return below(instrument_block_position)


def _summarize_block_collisions(
    collisions: tuple[BlockCollision, ...],
    track_layouts: tuple[TrackLayoutInfo, ...],
    max_examples: int = 3,
) -> list[CollisionSummary]:
    track_info_by_id = {info.track_id: info for info in track_layouts}
    grouped: dict[tuple[str, str, str], list[BlockCollision]] = defaultdict(list)

    for collision in collisions:
        if collision.collision_type == "occupied_reserved_air":
            first_id = collision.first_track_id
            second_id = collision.second_track_id
        else:
            first_id, second_id = sorted(
                (collision.first_track_id, collision.second_track_id)
            )
        grouped[(first_id, second_id, collision.collision_type)].append(collision)

    summaries: list[CollisionSummary] = []
    for (first_id, second_id, collision_type), group in sorted(grouped.items()):
        first_info = track_info_by_id.get(first_id)
        second_info = track_info_by_id.get(second_id)
        if first_info is None or second_info is None:
            continue

        examples = tuple(
            CollisionExample(
                position=collision.position,
                first_block_type=collision.first_block_type,
                first_tick=collision.first_tick,
                second_block_type=collision.second_block_type,
                second_tick=collision.second_tick,
            )
            for collision in group[: max(0, max_examples)]
        )
        affected_cells = {
            (collision.first_tick, collision.second_tick)
            for collision in group
        }

        summaries.append(
            CollisionSummary(
                first_track=first_info,
                second_track=second_info,
                collision_type=collision_type,
                estimated_cell_count=len(affected_cells),
                examples=examples,
            )
        )

    return summaries
