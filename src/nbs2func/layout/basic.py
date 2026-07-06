from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .collision import (
    _detect_block_collisions,
    _gravity_support_position,
)
from .geometry import (
    DIRECTION_VECTORS,
    BlockPosition,
    LayoutError,
    _scale_vector,
    add_vector,
    below,
    normalize_direction,
    opposite_direction,
)
from .models import (
    LayoutCell,
    LayoutConflict,
    LayoutResult,
    PlacedNote,
)
from ..core.models import NoteEvent, Song, Track


@dataclass(frozen=True)
class BasicLinearLayout:
    """Single-track linear layout used by the current command writer."""

    origin: BlockPosition = BlockPosition(0, 128, 0)
    track_direction: str = "east"
    selected_track_id: int | None = None
    tick_spacing: int = 2

    def layout_song(self, song: Song) -> LayoutResult:
        track = _select_single_track(song, self.selected_track_id)
        conflicts = _find_single_track_conflicts(song)
        note_by_tick = _notes_by_tick(track)
        max_tick = max(note_by_tick) if note_by_tick else 0

        cells: list[LayoutCell] = []
        placed_notes: list[PlacedNote] = []

        for tick in range(max_tick + 1):
            note = note_by_tick.get(tick)
            cell = self.layout_cell(track, tick, note)
            cells.append(cell)
            if cell.note is not None:
                placed_notes.append(cell.note)

        cell_tuple = tuple(cells)
        note_tuple = tuple(placed_notes)

        return LayoutResult(
            mode="basic_linear",
            cells=cell_tuple,
            notes=note_tuple,
            conflicts=tuple(conflicts),
            collisions=tuple(_detect_block_collisions(cell_tuple)),
        )

    def layout_cell(
        self,
        track: Track,
        tick: int,
        note: NoteEvent | None,
    ) -> LayoutCell:
        track_direction = normalize_direction(self.track_direction)
        track_vector = DIRECTION_VECTORS[track_direction]
        note_vector = DIRECTION_VECTORS[opposite_direction(track_direction)]
        repeater_position = add_vector(
            self.origin,
            _scale_vector(track_vector, tick * self.tick_spacing),
        )
        note_block_position = add_vector(repeater_position, note_vector)
        instrument_block_position = below(note_block_position)
        gravity_support_block_position = _gravity_support_position(
            instrument_block_position,
            note,
        )
        placed_note = None

        if note is not None:
            placed_note = PlacedNote(
                tick=note.tick,
                track_id=str(track.id),
                source_track_id=track.id,
                layer=note.layer,
                instrument=note.instrument,
                key=note.key,
                final_volume=note.final_volume,
                final_panning=note.final_panning,
                track_volume=track.volume,
                track_panning=track.panning,
                virtual_role=None,
                note_block_position=note_block_position,
                instrument_block_position=instrument_block_position,
            )

        return LayoutCell(
            tick=tick,
            track_id=str(track.id),
            source_track_id=track.id,
            repeater_position=repeater_position,
            repeater_facing=opposite_direction(track_direction),
            track_block_position=below(repeater_position),
            note_block_position=note_block_position,
            instrument_block_position=instrument_block_position,
            gravity_support_block_position=gravity_support_block_position,
            note=placed_note,
        )


def _select_single_track(song: Song, selected_track_id: int | None) -> Track:
    tracks_with_notes = tuple(track for track in song.tracks if track.notes)

    if not tracks_with_notes:
        raise LayoutError("No tracks with notes were found.")

    if selected_track_id is None:
        if len(tracks_with_notes) > 1:
            ids = ", ".join(str(track.id) for track in tracks_with_notes)
            raise LayoutError(
                "basic_linear layout can generate one track at a time. "
                f"Choose one with --track-id. Tracks with notes: {ids}"
            )
        return tracks_with_notes[0]

    for track in tracks_with_notes:
        if track.id == selected_track_id:
            return track

    ids = ", ".join(str(track.id) for track in tracks_with_notes)
    raise LayoutError(
        f"Track {selected_track_id} has no notes or does not exist. "
        f"Tracks with notes: {ids}"
    )


def _notes_by_tick(track: Track) -> dict[int, NoteEvent]:
    return _notes_by_tick_for_notes(track.notes)


def _notes_by_tick_for_notes(notes_to_index: tuple[NoteEvent, ...]) -> dict[int, NoteEvent]:
    notes: dict[int, NoteEvent] = {}
    for note in notes_to_index:
        notes.setdefault(note.tick, note)
    return notes


def _find_single_track_conflicts(song: Song) -> list[LayoutConflict]:
    conflicts: list[LayoutConflict] = []

    for track in song.tracks:
        note_count_by_tick: dict[int, int] = defaultdict(int)
        for note in track.notes:
            note_count_by_tick[note.tick] += 1

        for tick, note_count in sorted(note_count_by_tick.items()):
            if note_count > 1:
                conflicts.append(
                    LayoutConflict(
                        tick=tick,
                        track_id=track.id,
                        note_count=note_count,
                    )
                )

    return conflicts
