from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

from .basic import _find_single_track_conflicts, _notes_by_tick_for_notes
from .collision import (
    _Footprint,
    _FootprintOccupancy,
    _detect_block_collisions,
    _footprint_collides,
    _occupy_footprint,
    _summarize_block_collisions,
    _gravity_support_position,
)
from .geometry import (
    DIRECTION_VECTORS,
    BlockPosition,
    LayoutError,
    _right_hand_lateral_vector,
    _scale_vector,
    above,
    add_vector,
    add_y,
    below,
    normalize_direction,
    opposite_direction,
)
from .models import (
    CenterSplitEvent,
    CollisionSummary,
    LayoutCell,
    LayoutResult,
    PlacedNote,
    StereoLayoutConfig,
    TrackLayoutInfo,
    _StereoOffset,
)
from .pan import _clamp_max_stereo_angle
from ..core.models import NoteEvent, Song, Track


@dataclass(frozen=True)
class _StereoTrack:
    track_id: str
    source_track_id: int
    source_layer: int | None
    name: str
    volume: float
    panning: float
    virtual_role: str | None
    split_reason: str | None
    split_mode: str | None
    original_name: str
    original_volume: float
    original_panning: float
    notes: tuple[NoteEvent, ...]


@dataclass(frozen=True)
class _CenterSplitDecision:
    source_track_id: int
    reason: str
    mode: str


@dataclass(frozen=True)
class _ResolvedStereoTrack:
    stereo_track: _StereoTrack
    original_offset: _StereoOffset
    resolved_offset: _StereoOffset
    fallback: str
    attempt_count: int
    unresolved_stage: str | None = None

@dataclass(frozen=True)
class TrackBasedStereoLayout:
    """Stable multi-track layout using fixed offsets from layer stereo data."""

    origin: BlockPosition = BlockPosition(0, 128, 0)
    track_direction: str = "east"
    config: StereoLayoutConfig = StereoLayoutConfig()
    tick_spacing: int = 2

    def layout_song(self, song: Song) -> LayoutResult:
        conflicts = _find_single_track_conflicts(song)
        split_decisions = self._center_split_decisions(song.tracks)
        stereo_tracks = tuple(self._expand_tracks(song.tracks, split_decisions))
        resolved_tracks = tuple(self._resolve_track_offsets(stereo_tracks))
        track_layouts = tuple(
            self._track_layout_info(resolved_track)
            for resolved_track in resolved_tracks
        )
        cells, placed_notes = self._cells_and_notes(resolved_tracks)
        cell_tuple = tuple(cells)
        note_tuple = tuple(placed_notes)
        collision_tuple = tuple(_detect_block_collisions(cell_tuple))

        return LayoutResult(
            mode="track_based_stereo",
            cells=cell_tuple,
            notes=note_tuple,
            conflicts=tuple(conflicts),
            collisions=collision_tuple,
            track_layouts=track_layouts,
            collision_summaries=tuple(
                _summarize_block_collisions(collision_tuple, track_layouts)
            ),
            center_split_events=tuple(self._center_split_events(resolved_tracks)),
        )

    def _cells_and_notes(
        self,
        resolved_tracks: tuple[_ResolvedStereoTrack, ...],
    ) -> tuple[list[LayoutCell], list[PlacedNote]]:
        cells: list[LayoutCell] = []
        placed_notes: list[PlacedNote] = []

        for resolved_track in resolved_tracks:
            stereo_track = resolved_track.stereo_track
            note_by_tick = _notes_by_tick_for_notes(stereo_track.notes)
            if not note_by_tick:
                continue

            max_tick = max(note_by_tick)
            for tick in range(max_tick + 1):
                note = note_by_tick.get(tick)
                cell = self.layout_cell(resolved_track, tick, note)
                cells.append(cell)
                if cell.note is not None:
                    placed_notes.append(cell.note)

        return cells, placed_notes

    def layout_cell(
        self,
        resolved_track: _ResolvedStereoTrack,
        tick: int,
        note: NoteEvent | None,
    ) -> LayoutCell:
        stereo_track = resolved_track.stereo_track
        track_direction = normalize_direction(self.track_direction)
        track_vector = DIRECTION_VECTORS[track_direction]
        note_vector = DIRECTION_VECTORS[opposite_direction(track_direction)]
        lateral_vector = _right_hand_lateral_vector(track_direction)
        offset = resolved_track.resolved_offset

        cell_origin = add_vector(
            self.origin,
            _scale_vector(track_vector, tick * self.tick_spacing),
        )
        repeater_position = add_vector(
            add_y(cell_origin, offset.offset_y),
            _scale_vector(lateral_vector, offset.offset_lateral),
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
                track_id=stereo_track.track_id,
                source_track_id=stereo_track.source_track_id,
                layer=note.layer,
                instrument=note.instrument,
                key=note.key,
                final_volume=note.final_volume,
                final_panning=note.final_panning,
                track_volume=stereo_track.volume,
                track_panning=stereo_track.panning,
                virtual_role=stereo_track.virtual_role,
                note_block_position=note_block_position,
                instrument_block_position=instrument_block_position,
                split_reason=stereo_track.split_reason,
                split_mode=stereo_track.split_mode,
            )

        return LayoutCell(
            tick=tick,
            track_id=stereo_track.track_id,
            source_track_id=stereo_track.source_track_id,
            repeater_position=repeater_position,
            repeater_facing=opposite_direction(track_direction),
            track_block_position=below(repeater_position),
            note_block_position=note_block_position,
            instrument_block_position=instrument_block_position,
            gravity_support_block_position=gravity_support_block_position,
            note=placed_note,
        )

    def _center_split_decisions(
        self,
        tracks: tuple[Track, ...],
    ) -> dict[int, _CenterSplitDecision]:
        policy = self.config.center_split_policy
        if policy not in {
            "none",
            "manual",
            "auto_on_collision",
            "manual_plus_auto",
        }:
            raise LayoutError(f"Unsupported center_split_policy: {policy}")

        manual_splits, manual_no_splits = self._manual_center_split_overrides(tracks)
        if policy == "none":
            return {}
        if policy == "manual":
            return manual_splits
        if policy == "auto_on_collision":
            return self._auto_center_split_decisions(tracks, {}, set())

        return self._auto_center_split_decisions(
            tracks,
            manual_splits,
            manual_no_splits,
        )

    def _manual_center_split_overrides(
        self,
        tracks: tuple[Track, ...],
    ) -> tuple[dict[int, _CenterSplitDecision], set[int]]:
        decisions: dict[int, _CenterSplitDecision] = {}
        no_split: set[int] = set()
        overrides = self.config.center_split_overrides or {}

        for track in tracks:
            if not track.notes:
                continue

            override = _center_split_override_for_track(track, overrides)
            if override is None:
                continue

            normalized = override.strip().lower()
            if normalized not in {"split", "none"}:
                warnings.warn(
                    f"Ignoring unknown center split override for track {track.id}: "
                    f"{override!r}. Expected 'split' or 'none'.",
                    stacklevel=2,
                )
                continue

            if normalized == "none":
                no_split.add(track.id)
                continue

            if not self._is_center_like_track(track):
                warnings.warn(
                    f"Ignoring center split override for non-center-like track "
                    f"{track.id} (layer_stereo={track.panning}).",
                    stacklevel=2,
                )
                continue

            decisions[track.id] = _CenterSplitDecision(
                source_track_id=track.id,
                reason="manual",
                mode=self._center_split_mode(),
            )

        return decisions, no_split

    def _auto_center_split_decisions(
        self,
        tracks: tuple[Track, ...],
        initial_decisions: dict[int, _CenterSplitDecision],
        no_split: set[int],
    ) -> dict[int, _CenterSplitDecision]:
        decisions = dict(initial_decisions)
        max_splits = max(0, self.config.max_auto_center_splits)

        for _ in range(max_splits):
            stereo_tracks = tuple(self._expand_tracks(tracks, decisions))
            preferred_tracks = tuple(self._preferred_track_offsets(stereo_tracks))
            track_layouts = tuple(
                self._track_layout_info(resolved_track)
                for resolved_track in preferred_tracks
            )
            cells, _ = self._cells_and_notes(preferred_tracks)
            collisions = tuple(_detect_block_collisions(tuple(cells)))
            summaries = tuple(_summarize_block_collisions(collisions, track_layouts))
            candidate = self._auto_center_split_candidate(
                summaries,
                tracks,
                decisions,
                no_split,
            )
            if candidate is None:
                break

            decisions[candidate.id] = _CenterSplitDecision(
                source_track_id=candidate.id,
                reason="auto_collision",
                mode="duplicate_half_volume",
            )

        return decisions

    def _auto_center_split_candidate(
        self,
        summaries: tuple[CollisionSummary, ...],
        tracks: tuple[Track, ...],
        decisions: dict[int, _CenterSplitDecision],
        no_split: set[int],
    ) -> Track | None:
        track_by_id = {track.id: track for track in tracks}

        for summary in summaries:
            involved_source_ids = {
                summary.first_track.source_track_id,
                summary.second_track.source_track_id,
            }
            center_like_ids = {
                track_id
                for track_id in involved_source_ids
                if track_id in track_by_id
                and self._is_center_like_track(track_by_id[track_id])
            }
            if len(center_like_ids) < 2:
                continue

            candidates = [
                track_by_id[track_id]
                for track_id in center_like_ids
                if track_id not in decisions and track_id not in no_split
            ]
            if candidates:
                return max(candidates, key=lambda track: track.id)

        return None

    def _is_center_like_track(self, track: Track) -> bool:
        return abs(track.panning - 100) <= self.config.center_threshold

    def _center_split_mode(self) -> str:
        mode = self.config.center_split_mode
        if mode != "duplicate_half_volume":
            raise LayoutError(f"Unsupported center_split_mode: {mode}")
        return mode

    def _expand_tracks(
        self,
        tracks: tuple[Track, ...],
        split_decisions: dict[int, _CenterSplitDecision] | None = None,
    ) -> list[_StereoTrack]:
        stereo_tracks: list[_StereoTrack] = []
        decisions = split_decisions or {}

        for track in tracks:
            if not track.notes:
                continue

            split_decision = decisions.get(track.id)
            if split_decision is not None:
                if split_decision.mode == "duplicate_half_volume":
                    clone_volume = track.volume * 0.5
                else:
                    clone_volume = track.volume
                stereo_tracks.append(
                    _StereoTrack(
                        track_id=f"{track.id}:L",
                        source_track_id=track.id,
                        source_layer=track.source_layer,
                        name=f"{track.name} (left split)",
                        volume=clone_volume,
                        panning=100 - self.config.center_split_pan,
                        virtual_role="left_clone",
                        split_reason=split_decision.reason,
                        split_mode=split_decision.mode,
                        original_name=track.name,
                        original_volume=track.volume,
                        original_panning=track.panning,
                        notes=track.notes,
                    )
                )
                stereo_tracks.append(
                    _StereoTrack(
                        track_id=f"{track.id}:R",
                        source_track_id=track.id,
                        source_layer=track.source_layer,
                        name=f"{track.name} (right split)",
                        volume=clone_volume,
                        panning=100 + self.config.center_split_pan,
                        virtual_role="right_clone",
                        split_reason=split_decision.reason,
                        split_mode=split_decision.mode,
                        original_name=track.name,
                        original_volume=track.volume,
                        original_panning=track.panning,
                        notes=track.notes,
                    )
                )
                continue

            stereo_tracks.append(
                _StereoTrack(
                    track_id=str(track.id),
                    source_track_id=track.id,
                    source_layer=track.source_layer,
                    name=track.name,
                    volume=track.volume,
                    panning=track.panning,
                    virtual_role=None,
                    split_reason=None,
                    split_mode=None,
                    original_name=track.name,
                    original_volume=track.volume,
                    original_panning=track.panning,
                    notes=track.notes,
                )
            )

        return stereo_tracks

    def _resolve_track_offsets(
        self,
        stereo_tracks: tuple[_StereoTrack, ...],
    ) -> list[_ResolvedStereoTrack]:
        occupied = _FootprintOccupancy(occupied={}, reserved_air={})
        resolved_tracks: list[_ResolvedStereoTrack] = []

        for stereo_track in stereo_tracks:
            original = self._track_offset(stereo_track.volume, stereo_track.panning)
            if not self.config.enable_collision_resolver:
                footprint = self._track_footprint(stereo_track, original)
                _occupy_footprint(occupied, footprint)
                resolved_tracks.append(
                    _ResolvedStereoTrack(
                        stereo_track=stereo_track,
                        original_offset=original,
                        resolved_offset=original,
                        fallback="disabled",
                        attempt_count=1,
                        unresolved_stage=None,
                    )
                )
                continue

            selected: _StereoOffset | None = None
            selected_fallback = "unresolved"
            attempt_count = 0

            for candidate, fallback in self._offset_candidates(stereo_track, original):
                attempt_count += 1
                footprint = self._track_footprint(stereo_track, candidate)
                if not self._is_valid_footprint(footprint):
                    continue
                if not _footprint_collides(occupied, footprint):
                    selected = candidate
                    selected_fallback = fallback
                    _occupy_footprint(occupied, footprint)
                    break

            if selected is None:
                selected = original
                _occupy_footprint(occupied, self._track_footprint(stereo_track, selected))
                unresolved_stage = "radius_relax_exhausted"
            else:
                unresolved_stage = None

            resolved_tracks.append(
                _ResolvedStereoTrack(
                    stereo_track=stereo_track,
                    original_offset=original,
                    resolved_offset=selected,
                    fallback=selected_fallback,
                    attempt_count=attempt_count,
                    unresolved_stage=unresolved_stage,
                )
            )

        return resolved_tracks

    def _preferred_track_offsets(
        self,
        stereo_tracks: tuple[_StereoTrack, ...],
    ) -> list[_ResolvedStereoTrack]:
        resolved_tracks: list[_ResolvedStereoTrack] = []

        for stereo_track in stereo_tracks:
            offset = self._track_offset(
                stereo_track.volume,
                stereo_track.panning,
            )
            resolved_tracks.append(
                _ResolvedStereoTrack(
                    stereo_track=stereo_track,
                    original_offset=offset,
                    resolved_offset=offset,
                    fallback="preferred",
                    attempt_count=1,
                    unresolved_stage=None,
                )
            )

        return resolved_tracks

    def _offset_candidates(
        self,
        stereo_track: _StereoTrack,
        original: _StereoOffset,
    ) -> list[tuple[_StereoOffset, str]]:
        candidates: list[tuple[_StereoOffset, str]] = [(original, "preferred")]

        if self.config.enable_depth_mirror_fallback:
            candidates.append((self._mirror_depth(original), "depth_mirror"))

        candidates.extend(
            (candidate, "angle_search")
            for candidate in self._angle_search_candidates(
                stereo_track,
                original.radius,
                original.angle_degrees,
                mirrored_depth=False,
            )
        )

        if self.config.enable_depth_mirror_fallback:
            candidates.extend(
                (candidate, "mirrored_angle_search")
                for candidate in self._angle_search_candidates(
                    stereo_track,
                    original.radius,
                    original.angle_degrees,
                    mirrored_depth=True,
                )
            )

        if self.config.enable_radius_relax_fallback:
            for radius in self._relaxed_radii(original.radius):
                relaxed = self._offset_from_radius_angle(
                    radius,
                    original.angle_degrees,
                    mirrored_depth=False,
                )
                candidates.append((relaxed, "radius_relax"))
                if self.config.enable_depth_mirror_fallback:
                    candidates.append(
                        (self._mirror_depth(relaxed), "radius_relax_depth_mirror")
                    )
                candidates.extend(
                    (candidate, "radius_relax_angle_search")
                    for candidate in self._angle_search_candidates(
                        stereo_track,
                        radius,
                        original.angle_degrees,
                        mirrored_depth=False,
                    )
                )
                if self.config.enable_depth_mirror_fallback:
                    candidates.extend(
                        (candidate, "radius_relax_mirrored_angle_search")
                        for candidate in self._angle_search_candidates(
                            stereo_track,
                            radius,
                            original.angle_degrees,
                            mirrored_depth=True,
                        )
                    )

        return candidates

    def _angle_search_candidates(
        self,
        stereo_track: _StereoTrack,
        radius: float,
        original_angle: float,
        mirrored_depth: bool,
    ) -> list[_StereoOffset]:
        candidates: list[_StereoOffset] = []
        preferred_sign = self._preferred_lateral_sign(stereo_track)

        for deviation in self._angle_deviations():
            for sign in (preferred_sign, -preferred_sign):
                angle = original_angle + sign * deviation
                candidate = self._offset_from_radius_angle(
                    radius,
                    angle,
                    mirrored_depth=mirrored_depth,
                )
                if preferred_sign > 0 and candidate.offset_lateral < 0:
                    continue
                if preferred_sign < 0 and candidate.offset_lateral > 0:
                    continue
                candidates.append(candidate)

        return candidates

    def _preferred_lateral_sign(self, stereo_track: _StereoTrack) -> int:
        if stereo_track.panning > 100:
            return 1
        if stereo_track.panning < 100:
            return -1
        return 1 if stereo_track.source_track_id % 2 == 0 else -1

    def _angle_deviations(self) -> list[float]:
        step = max(0.1, self.config.angle_search_step_degrees)
        max_deviation = max(0.0, self.config.max_angle_deviation_degrees)
        deviations: list[float] = []
        current = step
        while current <= max_deviation + 1e-9:
            deviations.append(current)
            current += step
        return deviations

    def _relaxed_radii(self, original_radius: float) -> list[float]:
        step = max(0.1, self.config.radius_relax_step)
        max_relax = max(0.0, self.config.max_radius_relax)
        radii: list[float] = []
        current = step
        while current <= max_relax + 1e-9:
            radii.append(original_radius + current)
            lowered = original_radius - current
            if lowered >= 0:
                radii.append(lowered)
            current += step
        return radii

    def _track_footprint(
        self,
        stereo_track: _StereoTrack,
        offset: _StereoOffset,
    ) -> _Footprint:
        note_by_tick = _notes_by_tick_for_notes(stereo_track.notes)
        if not note_by_tick:
            return _Footprint(occupied=(), reserved_air=())

        max_tick = max(note_by_tick)
        occupied: list[tuple[BlockPosition, str]] = []
        reserved_air: list[tuple[BlockPosition, str]] = []

        for tick in range(max_tick + 1):
            cell_footprint = self._cell_footprint_for_offset(
                offset,
                tick,
                note_by_tick.get(tick),
            )
            occupied.extend(cell_footprint.occupied)
            reserved_air.extend(cell_footprint.reserved_air)

        return _Footprint(
            occupied=tuple(occupied),
            reserved_air=tuple(reserved_air),
        )

    def _cell_footprint_for_offset(
        self,
        offset: _StereoOffset,
        tick: int,
        note: NoteEvent | None,
    ) -> _Footprint:
        track_direction = normalize_direction(self.track_direction)
        track_vector = DIRECTION_VECTORS[track_direction]
        note_vector = DIRECTION_VECTORS[opposite_direction(track_direction)]
        lateral_vector = _right_hand_lateral_vector(track_direction)
        cell_origin = add_vector(
            self.origin,
            _scale_vector(track_vector, tick * self.tick_spacing),
        )
        repeater_position = add_vector(
            add_y(cell_origin, offset.offset_y),
            _scale_vector(lateral_vector, offset.offset_lateral),
        )
        note_block_position = add_vector(repeater_position, note_vector)
        instrument_block_position = below(note_block_position)
        if note is None:
            note_block_type = "track_block"
            instrument_block_type = "track_block"
        else:
            note_block_type = "note_block"
            instrument_block_type = "instrument_block"

        occupied = [
            (below(repeater_position), "track_block"),
            (repeater_position, "repeater"),
            (note_block_position, note_block_type),
            (instrument_block_position, instrument_block_type),
        ]
        gravity_support = _gravity_support_position(instrument_block_position, note)
        if gravity_support is not None:
            occupied.insert(3, (gravity_support, "gravity_support_block"))

        reserved_air = ()
        if note is not None:
            reserved_air = ((above(note_block_position), "reserved_air"),)

        return _Footprint(occupied=tuple(occupied), reserved_air=reserved_air)

    def _is_valid_footprint(
        self,
        footprint: _Footprint,
    ) -> bool:
        for position, _ in footprint.occupied + footprint.reserved_air:
            if (
                self.config.min_world_y is not None
                and position.y < self.config.min_world_y
            ):
                return False
            if (
                self.config.max_world_y is not None
                and position.y > self.config.max_world_y
            ):
                return False
        return True

    def _mirror_depth(self, offset: _StereoOffset) -> _StereoOffset:
        return _StereoOffset(
            offset_y=-offset.offset_y,
            offset_lateral=offset.offset_lateral,
            radius=offset.radius,
            angle_degrees=offset.angle_degrees,
        )

    def _offset_from_radius_angle(
        self,
        radius: float,
        angle_degrees: float,
        mirrored_depth: bool,
    ) -> _StereoOffset:
        angle = math.radians(angle_degrees)
        offset_y = round(math.cos(angle) * radius)
        if mirrored_depth:
            offset_y = -offset_y
        offset_lateral = round(math.sin(angle) * radius)
        return _StereoOffset(
            offset_y=offset_y,
            offset_lateral=offset_lateral,
            radius=radius,
            angle_degrees=angle_degrees,
        )

    def _track_layout_info(
        self,
        resolved_track: _ResolvedStereoTrack,
    ) -> TrackLayoutInfo:
        stereo_track = resolved_track.stereo_track
        offset = resolved_track.resolved_offset
        original = resolved_track.original_offset
        return TrackLayoutInfo(
            track_id=stereo_track.track_id,
            source_track_id=stereo_track.source_track_id,
            layer_id=stereo_track.source_layer,
            name=stereo_track.name,
            offset_y=offset.offset_y,
            offset_lateral=offset.offset_lateral,
            radius=offset.radius,
            angle_degrees=offset.angle_degrees,
            original_offset_y=original.offset_y,
            original_offset_lateral=original.offset_lateral,
            original_radius=original.radius,
            original_angle_degrees=original.angle_degrees,
            fallback=resolved_track.fallback,
            attempt_count=resolved_track.attempt_count,
            unresolved_stage=resolved_track.unresolved_stage,
            virtual_role=stereo_track.virtual_role,
            split_reason=stereo_track.split_reason,
            split_mode=stereo_track.split_mode,
        )

    def _center_split_events(
        self,
        resolved_tracks: tuple[_ResolvedStereoTrack, ...],
    ) -> list[CenterSplitEvent]:
        events: list[CenterSplitEvent] = []

        for resolved_track in resolved_tracks:
            stereo_track = resolved_track.stereo_track
            if stereo_track.virtual_role is None:
                continue

            before = self._track_offset(
                stereo_track.original_volume,
                stereo_track.original_panning,
            )
            after = resolved_track.resolved_offset
            events.append(
                CenterSplitEvent(
                    original_track_id=stereo_track.source_track_id,
                    original_layer_id=stereo_track.source_layer,
                    original_track_name=stereo_track.original_name,
                    clone_track_id=stereo_track.track_id,
                    clone_side=stereo_track.virtual_role.removesuffix("_clone"),
                    split_reason=stereo_track.split_reason or "unknown",
                    split_mode=stereo_track.split_mode or "unknown",
                    before_offset_y=before.offset_y,
                    before_offset_lateral=before.offset_lateral,
                    before_radius=before.radius,
                    before_angle_degrees=before.angle_degrees,
                    after_offset_y=after.offset_y,
                    after_offset_lateral=after.offset_lateral,
                    after_radius=after.radius,
                    after_angle_degrees=after.angle_degrees,
                )
            )

        return events

    def _track_offset(self, layer_volume: float, layer_stereo: float) -> _StereoOffset:
        volume_norm = max(0.0, min(1.0, layer_volume / 100))
        distance = self.config.min_distance + (
            self.config.max_hearing_distance - self.config.min_distance
        ) * (1 - volume_norm)
        pan_norm = (layer_stereo - 100) / 100
        max_angle_degrees = _clamp_max_stereo_angle(
            self.config.max_stereo_angle_degrees
        )
        angle_degrees = pan_norm * max_angle_degrees
        angle = math.radians(angle_degrees)

        offset_y = round(math.cos(angle) * distance)
        offset_lateral = round(math.sin(angle) * distance)
        return _StereoOffset(
            offset_y=offset_y,
            offset_lateral=offset_lateral,
            radius=distance,
            angle_degrees=angle_degrees,
        )




def _center_split_override_for_track(
    track: Track,
    overrides: dict[int, str],
) -> str | None:
    if track.id in overrides:
        return overrides[track.id]
    if track.source_layer is not None and track.source_layer in overrides:
        return overrides[track.source_layer]
    return None
