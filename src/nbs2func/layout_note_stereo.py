from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, replace

from .layout_basic import _find_single_track_conflicts
from .layout_collision import (
    _Footprint,
    _FootprintOccupancy,
    _copy_footprint_occupancy,
    _detect_footprint_entry_collisions_limited,
    _first_footprint_collision,
    _footprint_collides,
    _gravity_support_position,
    _occupy_footprint,
    _replace_footprint_occupancy,
    _summarize_block_collisions,
)
from .layout_geometry import (
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
    repeater_position_from_note_position,
)
from .layout_models import (
    ActivationRail,
    ActivationSlot,
    BlockCollision,
    EmitterCandidate,
    LayoutCell,
    LayoutResult,
    NoteBasedStereoRailLayoutPreview,
    NoteEmitter,
    NoteLevelCenterSplitExample,
    PanZoneStatistic,
    RailRegistry,
    RailUsageStatistic,
    RailValidationIssue,
    SlotAssignment,
    StageTiming,
    StereoLayoutConfig,
    TrackLayoutInfo,
    _StereoOffset,
)
from .layout_spatial_analyzer import (
    LayoutSpatialHintIndex,
    LayoutSpatialSegmentHint,
)
from .layout_pan import (
    PAN_ZONES,
    _angle_error_inside_zone,
    _angle_values_for_pan_zones,
    _candidate_pan_zones,
    _clamp_max_stereo_angle,
    _failed_retry_pan_zones,
    _offset_from_radius_angle_values,
    _pan_error_inside_zone,
    _pan_zone_angle_range,
    _pan_zone_for_angle,
    _pan_zone_for_panning,
    _panning_from_angle,
)
from .models import NoteEvent, Song

PAN_HINT_WEIGHT = 1.0

PAN_MODE_FACTORS = {
    "center_stable": 1.0,
    "left_stable": 1.0,
    "right_stable": 1.0,
    "far_left_stable": 1.0,
    "far_right_stable": 1.0,
    "bimodal_left_right": 0.75,
    "center_plus_side": 0.75,
    "wide_or_split": 0.5,
    "unknown": 0.0,
    "inactive": 0.0,
}

SEGMENT_PAN_TARGET_INTERVALS = {
    "center_stable": (-10.0, 10.0),
    "left_stable": (-40.0, -10.0001),
    "right_stable": (10.0001, 40.0),
    "far_left_stable": (-90.0, -40.0001),
    "far_right_stable": (40.0001, 90.0),
}

@dataclass
class _RailValidationStats:
    rail_pairs_checked: int = 0
    rejected_by_same_plane_y_gap: int = 0
    rejected_by_full_footprint_collision: int = 0
    candidate_validation_count: int = 0
    total_rails_checked_per_candidate: int = 0
    max_rails_checked_per_candidate: int = 0
    issues: list[RailValidationIssue] | None = None

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []


@dataclass
class _NoteLevelCenterSplitStats:
    attempted: int = 0
    accepted: int = 0
    failed: int = 0
    emitters_added: int = 0
    failed_before_split: int = 0
    generated_candidates: int = 0
    examples: list[NoteLevelCenterSplitExample] | None = None

    def __post_init__(self) -> None:
        if self.examples is None:
            self.examples = []


@dataclass
class _CandidateGenerationStats:
    candidate_truncation_count: int = 0
    mirror_candidate_truncated_count: int = 0
    candidate_counts_by_pass: dict[str, list[int]] | None = None

    def __post_init__(self) -> None:
        if self.candidate_counts_by_pass is None:
            self.candidate_counts_by_pass = defaultdict(list)


@dataclass
class _AssignmentRetryStats:
    failed_after_pass1: int = 0
    failed_after_pass2: int = 0
    failed_after_pass3: int = 0
    retry_attempted: int = 0
    retry_accepted: int = 0
    retry_failed: int = 0
    adjacent_attempted: int = 0
    adjacent_accepted: int = 0
    adjacent_failed: int = 0
    adjacent_by_source_zone: dict[str, list[int]] | None = None
    failed_examples_after_pass1: tuple[str, ...] = ()
    failed_examples_after_pass2: tuple[str, ...] = ()
    failed_examples_after_pass3: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.adjacent_by_source_zone is None:
            self.adjacent_by_source_zone = defaultdict(lambda: [0, 0, 0])


@dataclass
class _AssignmentState:
    assignments: list[SlotAssignment]
    occupancy: _FootprintOccupancy
    active_rails: dict[str, ActivationRail]
    rail_footprints: dict[str, _Footprint]
    rails_by_transverse: dict[int, set[str]]
    used_slots_by_tick: dict[int, set[tuple[str, int]]]
    active_rail_cells_by_tick: dict[int, dict[str, bool]]


@dataclass(frozen=True)
class NoteBasedStereoLayout:
    """Preview-only traditional redstone note-based rail layout."""

    origin: BlockPosition = BlockPosition(0, 128, 0)
    track_direction: str = "east"
    config: StereoLayoutConfig = StereoLayoutConfig()
    tick_spacing: int = 2
    spatial_hint_index: LayoutSpatialHintIndex | None = None

    def _log(self, message: str) -> None:
        if self.config.enable_progress_logging:
            print(f"[NoteBasedRail] {message}", flush=True)

    def _get_layout_spatial_segment_hint(
        self,
        layer_id: int,
        tick: int,
    ) -> LayoutSpatialSegmentHint | None:
        if self.spatial_hint_index is None:
            return None
        return self.spatial_hint_index.get_segment(layer_id, tick)

    def _candidate_pan_hint_score(
        self,
        emitter: NoteEmitter,
        candidate_pan_zone: str,
    ) -> float:
        segment = self._get_layout_spatial_segment_hint(emitter.track_id, emitter.tick)
        if segment is None:
            return 0.0
        return _segment_pan_hint_score(
            segment,
            emitter,
            candidate_pan_zone,
            max_stereo_angle_degrees=self.config.max_stereo_angle_degrees,
        )

    def _check_time_limit(self, total_start: float, stage: str) -> None:
        limit = self.config.preview_time_limit_seconds
        if limit <= 0:
            return
        elapsed = time.perf_counter() - total_start
        if elapsed > limit:
            self._log(
                f"preview time limit exceeded at stage={stage} "
                f"elapsed={elapsed:.2f}s limit={limit:.2f}s"
            )
            raise LayoutError(
                "note_based_stereo preview time limit exceeded "
                f"during {stage} after {elapsed:.2f}s. "
                "Try lowering --max-candidates-per-emitter or using "
                "--disable-pan-zone-layout for comparison."
            )

    def layout_song(self, song: Song) -> LayoutResult:
        total_start = time.perf_counter()
        timings: list[StageTiming] = []
        note_count = sum(len(track.notes) for track in song.tracks)
        active_ticks = len(
            {
                note.tick
                for track in song.tracks
                for note in track.notes
            }
        )
        self._log(f"notes={note_count} active_ticks={active_ticks}")

        stage_start = time.perf_counter()
        self._log("stage: computing ideal positions")
        emitters = tuple(self._ideal_emitters(song))
        timings.append(
            StageTiming("ideal position time", time.perf_counter() - stage_start)
        )

        stage_start = time.perf_counter()
        self._log("stage: generating pan zone candidates")
        candidate_cache: dict[str, tuple[EmitterCandidate, ...]] = {}
        candidate_generation_stats = _CandidateGenerationStats()
        candidate_counts: list[int] = []
        for index, emitter in enumerate(emitters, start=1):
            candidates = tuple(
                self._emitter_candidates(
                    emitter,
                    generation_stats=candidate_generation_stats,
                    pass_name="pass1",
                )
            )
            candidate_cache[emitter.emitter_id] = candidates
            candidate_counts.append(len(candidates))
            if index % 1000 == 0 or index == len(emitters):
                self._log(f"generating candidates: {index}/{len(emitters)}")
            self._check_time_limit(total_start, "candidate generation")
        timings.append(
            StageTiming("candidate generation time", time.perf_counter() - stage_start)
        )

        stage_start = time.perf_counter()
        self._log("stage: scoring activation rails")
        candidate_values = self._rail_candidate_values(emitters, candidate_cache)
        registry = RailRegistry(rails={})
        for (offset_y, offset_lateral), value in sorted(
            candidate_values.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            registry.get_or_create(offset_y, offset_lateral, value)
        timings.append(
            StageTiming("rail scoring time", time.perf_counter() - stage_start)
        )

        stage_start = time.perf_counter()
        self._log("stage: assigning emitters to rail slots")
        self._log("stage: validating rails")
        (
            assignments,
            failed_emitters,
            rail_validation_stats,
            center_split_stats,
            retry_stats,
        ) = self._assign_emitters(
            emitters,
            registry,
            candidate_values,
            candidate_cache,
            candidate_generation_stats,
            total_start,
        )
        timings.append(StageTiming("assignment time", time.perf_counter() - stage_start))

        stage_start = time.perf_counter()
        self._log(
            f"rails={len({assignment.rail.rail_id for assignment in assignments})} "
            f"assignments={len(assignments)}"
        )
        rail_stats = tuple(self._rail_usage_statistics(assignments, registry))
        assigned_costs = [assignment.candidate.cost for assignment in assignments]
        radius_errors = [assignment.candidate.radius_error for assignment in assignments]
        pan_errors = [
            assignment.candidate.pan_error_inside_zone
            for assignment in assignments
        ]
        positive_depth_costs = [
            assignment.candidate.cost
            for assignment in assignments
            if assignment.candidate.offset_y >= 0
        ]
        negative_depth_costs = [
            assignment.candidate.cost
            for assignment in assignments
            if assignment.candidate.offset_y < 0
        ]
        mirror_accepted_count = sum(
            1 for assignment in assignments if assignment.candidate.depth_mirrored
        )
        mirror_candidate_count = sum(
            1
            for candidates in candidate_cache.values()
            for candidate in candidates
            if candidate.depth_mirrored
        )
        active_cell_count = sum(stat.active_cell_count for stat in rail_stats)
        used_slot_count = sum(stat.used_slot_count for stat in rail_stats)
        all_candidate_counts = [
            count
            for counts in (candidate_generation_stats.candidate_counts_by_pass or {}).values()
            for count in counts
        ]
        total_candidate_count = (
            sum(all_candidate_counts) + center_split_stats.generated_candidates
        )
        total_candidate_emitters = (
            len(all_candidate_counts) + center_split_stats.emitters_added
        )
        timings.append(
            StageTiming("report generation time", time.perf_counter() - stage_start)
        )

        report = NoteBasedStereoRailLayoutPreview(
            total_note_events=sum(len(track.notes) for track in song.tracks),
            total_ideal_emitters=len(emitters),
            total_activation_rails=len(rail_stats),
            unchanged_assignments=sum(
                1
                for assignment in assignments
                if assignment.candidate.y_movement == 0
                and assignment.candidate.lateral_movement == 0
            ),
            y_movement_assignments=sum(
                1 for assignment in assignments if assignment.candidate.y_movement != 0
            ),
            z_movement_assignments=sum(
                1
                for assignment in assignments
                if assignment.candidate.lateral_movement != 0
            ),
            failed_assignment_count=len(failed_emitters),
            average_movement_cost=(
                sum(assigned_costs) / len(assigned_costs) if assigned_costs else 0
            ),
            max_movement_cost=max(assigned_costs) if assigned_costs else 0,
            average_used_slots_per_active_rail_cell=(
                used_slot_count / active_cell_count if active_cell_count else 0
            ),
            rail_usage_statistics=rail_stats,
            assignments=tuple(assignments),
            failed_emitters=tuple(failed_emitters),
            origin=self.origin,
            track_direction=normalize_direction(self.track_direction),
            tick_spacing=self.tick_spacing,
            pan_zone_distribution=tuple(
                self._pan_zone_distribution(emitters, assignments, failed_emitters)
            ),
            pan_zone_unchanged_count=sum(
                1
                for assignment in assignments
                if assignment.emitter.pan_zone == assignment.candidate.pan_zone
            ),
            adjacent_zone_fallback_count=sum(
                1
                for assignment in assignments
                if assignment.candidate.adjacent_zone_fallback
            ),
            average_radius_error=(
                sum(radius_errors) / len(radius_errors) if radius_errors else 0
            ),
            max_radius_error=max(radius_errors) if radius_errors else 0,
            average_pan_error_inside_zone=(
                sum(pan_errors) / len(pan_errors) if pan_errors else 0
            ),
            rail_collision_count_before=None,
            rail_pairs_checked=rail_validation_stats.rail_pairs_checked,
            rail_pairs_rejected_by_same_plane_y_gap=(
                rail_validation_stats.rejected_by_same_plane_y_gap
            ),
            rail_pairs_rejected_by_full_footprint_collision=(
                rail_validation_stats.rejected_by_full_footprint_collision
            ),
            invalid_rail_pairs=tuple((rail_validation_stats.issues or [])[:20]),
            total_candidates_generated=total_candidate_count,
            average_candidates_per_emitter=(
                total_candidate_count / total_candidate_emitters
                if total_candidate_emitters
                else 0
            ),
            max_candidates_for_one_emitter=(
                max(all_candidate_counts) if all_candidate_counts else 0
            ),
            average_rails_checked_per_candidate=(
                rail_validation_stats.total_rails_checked_per_candidate
                / rail_validation_stats.candidate_validation_count
                if rail_validation_stats.candidate_validation_count
                else 0
            ),
            max_rails_checked_per_candidate=(
                rail_validation_stats.max_rails_checked_per_candidate
            ),
            center_split_attempted_count=center_split_stats.attempted,
            center_split_accepted_count=center_split_stats.accepted,
            center_split_failed_count=center_split_stats.failed,
            emitters_added_by_center_split=center_split_stats.emitters_added,
            failed_assignment_count_before_split=(
                center_split_stats.failed_before_split
            ),
            failed_assignment_count_after_split=len(failed_emitters),
            center_split_examples=tuple((center_split_stats.examples or [])[:20]),
            positive_depth_rail_count=sum(
                1 for stat in rail_stats if stat.offset_y >= 0
            ),
            negative_depth_rail_count=sum(
                1 for stat in rail_stats if stat.offset_y < 0
            ),
            positive_depth_assignments=len(positive_depth_costs),
            negative_depth_assignments=len(negative_depth_costs),
            mirror_fallback_accepted_count=mirror_accepted_count,
            mirror_fallback_rejected_count=max(
                0,
                mirror_candidate_count - mirror_accepted_count,
            ),
            failed_assignment_count_by_pan_zone=tuple(
                _failed_count_by_pan_zone(failed_emitters)
            ),
            failed_assignment_count_by_depth_sign=tuple(
                _failed_count_by_depth_sign(failed_emitters)
            ),
            average_positive_depth_assignment_cost=(
                sum(positive_depth_costs) / len(positive_depth_costs)
                if positive_depth_costs
                else 0
            ),
            average_negative_depth_assignment_cost=(
                sum(negative_depth_costs) / len(negative_depth_costs)
                if negative_depth_costs
                else 0
            ),
            failed_assignment_count_after_pass1=retry_stats.failed_after_pass1,
            failed_assignment_count_after_pass2=retry_stats.failed_after_pass2,
            failed_assignment_count_after_pass3=retry_stats.failed_after_pass3,
            retry_attempted_count=retry_stats.retry_attempted,
            retry_accepted_count=retry_stats.retry_accepted,
            retry_failed_count=retry_stats.retry_failed,
            adjacent_zone_fallback_attempted_count=retry_stats.adjacent_attempted,
            adjacent_zone_fallback_accepted_count=retry_stats.adjacent_accepted,
            adjacent_zone_fallback_failed_count=retry_stats.adjacent_failed,
            adjacent_zone_fallback_by_source_zone=(
                _adjacent_zone_fallback_summary(retry_stats)
            ),
            candidate_truncation_count=(
                candidate_generation_stats.candidate_truncation_count
            ),
            mirror_candidate_truncated_count=(
                candidate_generation_stats.mirror_candidate_truncated_count
            ),
            average_candidate_count_by_pass=(
                _average_candidate_count_by_pass(candidate_generation_stats)
            ),
            failed_examples_after_pass1=retry_stats.failed_examples_after_pass1,
            failed_examples_after_pass2=retry_stats.failed_examples_after_pass2,
            failed_examples_after_pass3=retry_stats.failed_examples_after_pass3,
        )

        stage_start = time.perf_counter()
        self._log("stage: collision check")
        self._log("collision check started")
        collisions_list, skipped_collisions = self._build_collisions(report)
        collisions = tuple(collisions_list)
        timings.append(
            StageTiming("collision check time", time.perf_counter() - stage_start)
        )
        timings.append(StageTiming("total time", time.perf_counter() - total_start))
        report = replace(
            report,
            rail_collision_count_after=len(collisions),
            collision_records_stored=len(collisions),
            collision_records_skipped_due_to_cap=skipped_collisions,
            stage_timings=tuple(timings),
        )
        self._log("stage: writing report / mcfunction")
        cells = tuple(self._preview_cells(report))
        rail_track_layouts = tuple(self._rail_track_layouts(report))

        return LayoutResult(
            mode="note_based_stereo_preview",
            cells=cells,
            notes=(),
            conflicts=tuple(_find_single_track_conflicts(song)),
            collisions=collisions,
            track_layouts=rail_track_layouts,
            collision_summaries=tuple(
                _summarize_block_collisions(
                    collisions,
                    rail_track_layouts,
                    max_examples=self.config.max_collision_examples_per_group,
                )
            ),
            note_based_preview=report,
        )

    def _build_collisions(
        self,
        report: NoteBasedStereoRailLayoutPreview,
    ) -> tuple[list[BlockCollision], int]:
        occupied, reserved_air = _note_based_preview_footprint_entries(report)
        return _detect_footprint_entry_collisions_limited(
            occupied,
            reserved_air,
            max_records=self.config.max_collision_records,
            max_total_records_before_abort=(
                self.config.max_collision_records_before_abort
                if self.config.fail_fast_on_too_many_collisions
                else None
            ),
        )

    def _preview_cells(
        self,
        report: NoteBasedStereoRailLayoutPreview,
    ) -> list[LayoutCell]:
        cells: list[LayoutCell] = []
        assignments_by_rail_tick: dict[tuple[str, int], list[SlotAssignment]] = defaultdict(list)
        rails_by_id = {
            assignment.rail.rail_id: assignment.rail
            for assignment in report.assignments
        }

        for assignment in report.assignments:
            assignments_by_rail_tick[
                (assignment.rail.rail_id, assignment.emitter.tick)
            ].append(assignment)

        for rail_id, rail in sorted(rails_by_id.items()):
            rail_ticks = [
                tick
                for assignment_rail_id, tick in assignments_by_rail_tick
                if assignment_rail_id == rail_id
            ]
            if not rail_ticks:
                continue

            for tick in range(max(rail_ticks) + 1):
                rail_center = _note_based_preview_position(
                    report,
                    tick,
                    rail.offset_y,
                    rail.offset_lateral,
                )
                repeater_position = repeater_position_from_note_position(
                    rail_center,
                    report.track_direction,
                )
                cells.append(
                    LayoutCell(
                        tick=tick,
                        track_id=rail_id,
                        source_track_id=0,
                        repeater_position=repeater_position,
                        repeater_facing=opposite_direction(report.track_direction),
                        track_block_position=below(repeater_position),
                        note_block_position=rail_center,
                        instrument_block_position=below(rail_center),
                    )
                )

        return cells

    def _ideal_emitters(self, song: Song) -> list[NoteEmitter]:
        emitters: list[NoteEmitter] = []

        for track in song.tracks:
            for note_index, note in enumerate(track.notes):
                offset = self._note_offset(note.final_volume, note.final_panning)
                position = self._position_from_offsets(
                    note.tick,
                    offset.offset_y,
                    offset.offset_lateral,
                )
                pan_zone = _pan_zone_for_angle(offset.angle_degrees)
                note_delta = note.panning - 100
                layer_delta = (track.panning - 100) * 0.5
                emitters.append(
                    NoteEmitter(
                        emitter_id=f"{track.id}:{note.tick}:{note_index}",
                        track_id=track.id,
                        layer=note.layer,
                        tick=note.tick,
                        instrument=note.instrument,
                        key=note.key,
                        final_volume=note.final_volume,
                        final_panning=note.final_panning,
                        ideal_position=position,
                        ideal_offset_y=offset.offset_y,
                        ideal_offset_lateral=offset.offset_lateral,
                        ideal_radius=offset.radius,
                        pan_zone=pan_zone,
                        note_panning=note.panning,
                        layer_panning=track.panning,
                        note_pan_delta=note_delta,
                        layer_pan_delta=layer_delta,
                        final_pan_delta=note.final_panning - 100,
                        target_angle_degrees=offset.angle_degrees,
                        target_radius=offset.radius,
                        allowed_angle_range=_pan_zone_angle_range(
                            pan_zone,
                            self.config.max_stereo_angle_degrees,
                        ),
                    )
                )

        return emitters

    def _rail_candidate_values(
        self,
        emitters: tuple[NoteEmitter, ...],
        candidate_cache: dict[str, tuple[EmitterCandidate, ...]],
    ) -> dict[tuple[int, int], int]:
        values: dict[tuple[int, int], int] = defaultdict(int)

        for emitter in emitters:
            for candidate in candidate_cache[emitter.emitter_id]:
                rail_key = (
                    candidate.rail_offset_y,
                    candidate.rail_offset_lateral,
                )
                values[rail_key] += 1

        return values

    def _assign_emitters(
        self,
        emitters: tuple[NoteEmitter, ...],
        registry: RailRegistry,
        candidate_values: dict[tuple[int, int], int],
        candidate_cache: dict[str, tuple[EmitterCandidate, ...]],
        candidate_generation_stats: _CandidateGenerationStats,
        total_start: float,
    ) -> tuple[
        list[SlotAssignment],
        list[NoteEmitter],
        _RailValidationStats,
        _NoteLevelCenterSplitStats,
        _AssignmentRetryStats,
    ]:
        state = _AssignmentState(
            assignments=[],
            occupancy=_FootprintOccupancy(occupied={}, reserved_air={}),
            active_rails={},
            rail_footprints={},
            rails_by_transverse=defaultdict(set),
            used_slots_by_tick=defaultdict(set),
            active_rail_cells_by_tick=defaultdict(dict),
        )
        rail_stats = _RailValidationStats()
        center_split_stats = _NoteLevelCenterSplitStats()
        retry_stats = _AssignmentRetryStats()

        failed_after_pass1 = self._assign_emitter_pass(
            emitters=emitters,
            candidate_cache=candidate_cache,
            registry=registry,
            candidate_values=candidate_values,
            state=state,
            rail_stats=rail_stats,
            center_split_stats=center_split_stats,
            total_start=total_start,
            pass_name="pass1",
            allow_center_split=True,
        )
        retry_stats.failed_after_pass1 = len(failed_after_pass1)
        retry_stats.failed_examples_after_pass1 = _failed_emitter_examples(
            failed_after_pass1
        )

        pass2_cache = self._retry_candidate_cache(
            failed_after_pass1,
            pass_name="pass2",
            allow_adjacent=False,
            candidate_generation_stats=candidate_generation_stats,
        )
        _merge_candidate_values(candidate_values, pass2_cache)
        retry_stats.retry_attempted += len(failed_after_pass1)
        failed_after_pass2 = self._assign_emitter_pass(
            emitters=tuple(failed_after_pass1),
            candidate_cache=pass2_cache,
            registry=registry,
            candidate_values=candidate_values,
            state=state,
            rail_stats=rail_stats,
            center_split_stats=center_split_stats,
            total_start=total_start,
            pass_name="pass2",
            allow_center_split=False,
        )
        retry_stats.failed_after_pass2 = len(failed_after_pass2)
        retry_stats.failed_examples_after_pass2 = _failed_emitter_examples(
            failed_after_pass2
        )
        retry_stats.retry_accepted += len(failed_after_pass1) - len(failed_after_pass2)

        failed_after_pass3 = failed_after_pass2
        if self.config.allow_adjacent_pan_zone_fallback_for_failed:
            pass3_emitters = tuple(
                emitter for emitter in failed_after_pass2 if emitter.pan_zone != "CENTER"
            )
            pass3_cache = self._retry_candidate_cache(
                pass3_emitters,
                pass_name="pass3",
                allow_adjacent=True,
                candidate_generation_stats=candidate_generation_stats,
            )
            _merge_candidate_values(candidate_values, pass3_cache)
            retry_stats.retry_attempted += len(pass3_emitters)
            retry_stats.adjacent_attempted += len(pass3_emitters)
            for emitter in pass3_emitters:
                if retry_stats.adjacent_by_source_zone is not None:
                    retry_stats.adjacent_by_source_zone[emitter.pan_zone][0] += 1
            pass3_failed_non_center = self._assign_emitter_pass(
                emitters=pass3_emitters,
                candidate_cache=pass3_cache,
                registry=registry,
                candidate_values=candidate_values,
                state=state,
                rail_stats=rail_stats,
                center_split_stats=center_split_stats,
                total_start=total_start,
                pass_name="pass3",
                allow_center_split=False,
            )
            accepted_ids = {
                emitter.emitter_id
                for emitter in pass3_emitters
                if emitter not in pass3_failed_non_center
            }
            for emitter in pass3_emitters:
                if retry_stats.adjacent_by_source_zone is None:
                    continue
                if emitter.emitter_id in accepted_ids:
                    retry_stats.adjacent_by_source_zone[emitter.pan_zone][1] += 1
                else:
                    retry_stats.adjacent_by_source_zone[emitter.pan_zone][2] += 1
            retry_stats.adjacent_accepted += len(pass3_emitters) - len(pass3_failed_non_center)
            retry_stats.adjacent_failed += len(pass3_failed_non_center)
            retry_stats.retry_accepted += len(pass3_emitters) - len(pass3_failed_non_center)
            failed_after_pass3 = tuple(
                emitter
                for emitter in failed_after_pass2
                if emitter.pan_zone == "CENTER"
            ) + tuple(pass3_failed_non_center)

        retry_stats.failed_after_pass3 = len(failed_after_pass3)
        retry_stats.failed_examples_after_pass3 = _failed_emitter_examples(
            failed_after_pass3
        )
        retry_stats.retry_failed = len(failed_after_pass3)

        final_failed: list[NoteEmitter] = []
        for emitter in failed_after_pass3:
            if emitter.pan_zone != "CENTER" and self.config.enable_same_side_zone_split_fallback:
                used_slots = state.used_slots_by_tick[emitter.tick]
                active_rail_cells = state.active_rail_cells_by_tick[emitter.tick]
                split_assignments = self._try_same_side_zone_split(
                    emitter,
                    tick=emitter.tick,
                    registry=registry,
                    candidate_values=candidate_values,
                    occupancy=state.occupancy,
                    used_slots=used_slots,
                    active_rail_cells=active_rail_cells,
                    active_rails=state.active_rails,
                    rail_footprints=state.rail_footprints,
                    rails_by_transverse=state.rails_by_transverse,
                    rail_stats=rail_stats,
                    candidate_generation_stats=candidate_generation_stats,
                )
                if split_assignments:
                    state.assignments.extend(split_assignments)
                    continue

            if emitter.pan_zone == "CENTER":
                used_slots = state.used_slots_by_tick[emitter.tick]
                active_rail_cells = state.active_rail_cells_by_tick[emitter.tick]
                center_split_stats.failed_before_split += 1
                split_assignments = self._try_note_level_center_split(
                    emitter,
                    tick=emitter.tick,
                    registry=registry,
                    candidate_values=candidate_values,
                    occupancy=state.occupancy,
                    used_slots=used_slots,
                    active_rail_cells=active_rail_cells,
                    active_rails=state.active_rails,
                    rail_footprints=state.rail_footprints,
                    rails_by_transverse=state.rails_by_transverse,
                    rail_stats=rail_stats,
                    split_stats=center_split_stats,
                )
                if split_assignments:
                    state.assignments.extend(split_assignments)
                    continue
            final_failed.append(emitter)

        return (
            state.assignments,
            final_failed,
            rail_stats,
            center_split_stats,
            retry_stats,
        )

    def _try_same_side_zone_split(
        self,
        emitter: NoteEmitter,
        tick: int,
        registry: RailRegistry,
        candidate_values: dict[tuple[int, int], int],
        occupancy: _FootprintOccupancy,
        used_slots: set[tuple[str, int]],
        active_rail_cells: dict[str, bool],
        active_rails: dict[str, ActivationRail],
        rail_footprints: dict[str, _Footprint],
        rails_by_transverse: dict[int, set[str]],
        rail_stats: _RailValidationStats,
        candidate_generation_stats: _CandidateGenerationStats,
    ) -> list[SlotAssignment] | None:
        split_emitters = self._same_side_split_emitters(emitter)
        if split_emitters is None:
            return None
        first, second = split_emitters
        first_candidates = tuple(
            self._emitter_candidates(
                first,
                candidate_limit=self.config.retry_max_candidates_per_emitter,
                allow_adjacent=False,
                generation_stats=candidate_generation_stats,
                pass_name="same_side_split",
            )
        )
        second_candidates = tuple(
            self._emitter_candidates(
                second,
                candidate_limit=self.config.retry_max_candidates_per_emitter,
                allow_adjacent=False,
                generation_stats=candidate_generation_stats,
                pass_name="same_side_split",
            )
        )

        occupancy_copy = _copy_footprint_occupancy(occupancy)
        used_slots_copy = set(used_slots)
        active_rail_cells_copy = dict(active_rail_cells)
        active_rails_copy = dict(active_rails)
        rail_footprints_copy = dict(rail_footprints)
        rails_by_transverse_copy = _copy_transverse_index(rails_by_transverse)

        first_assignment = self._try_assign_emitter(
            first,
            first_candidates,
            tick,
            registry,
            candidate_values,
            occupancy_copy,
            used_slots_copy,
            active_rail_cells_copy,
            active_rails_copy,
            rail_footprints_copy,
            rails_by_transverse_copy,
            rail_stats,
        )
        second_assignment = None
        if first_assignment is not None:
            second_assignment = self._try_assign_emitter(
                second,
                second_candidates,
                tick,
                registry,
                candidate_values,
                occupancy_copy,
                used_slots_copy,
                active_rail_cells_copy,
                active_rails_copy,
                rail_footprints_copy,
                rails_by_transverse_copy,
                rail_stats,
            )

        if first_assignment is None or second_assignment is None:
            return None

        _replace_footprint_occupancy(occupancy, occupancy_copy)
        _replace_set(used_slots, used_slots_copy)
        _replace_dict(active_rail_cells, active_rail_cells_copy)
        _replace_dict(active_rails, active_rails_copy)
        _replace_dict(rail_footprints, rail_footprints_copy)
        _replace_transverse_index(rails_by_transverse, rails_by_transverse_copy)
        return [first_assignment, second_assignment]

    def _same_side_split_emitters(
        self,
        emitter: NoteEmitter,
    ) -> tuple[NoteEmitter, NoteEmitter] | None:
        if emitter.pan_zone == "L_MID":
            return (
                self._same_side_split_emitter(emitter, "inner", 75),
                self._same_side_split_emitter(emitter, "edge", 25),
            )
        if emitter.pan_zone == "R_MID":
            return (
                self._same_side_split_emitter(emitter, "inner", 125),
                self._same_side_split_emitter(emitter, "edge", 175),
            )
        return None

    def _same_side_split_emitter(
        self,
        emitter: NoteEmitter,
        role: str,
        panning: float,
    ) -> NoteEmitter:
        volume = emitter.final_volume * self.config.same_side_split_volume_factor
        offset = self._note_offset(volume, panning)
        position = self._position_from_offsets(
            emitter.tick,
            offset.offset_y,
            offset.offset_lateral,
        )
        pan_zone = _pan_zone_for_angle(offset.angle_degrees)
        return NoteEmitter(
            emitter_id=f"{emitter.emitter_id}:same_side_split_{role}",
            track_id=emitter.track_id,
            layer=emitter.layer,
            tick=emitter.tick,
            instrument=emitter.instrument,
            key=emitter.key,
            final_volume=volume,
            final_panning=panning,
            ideal_position=position,
            ideal_offset_y=offset.offset_y,
            ideal_offset_lateral=offset.offset_lateral,
            ideal_radius=offset.radius,
            pan_zone=pan_zone,
            note_panning=panning,
            layer_panning=100,
            note_pan_delta=panning - 100,
            layer_pan_delta=0,
            final_pan_delta=panning - 100,
            target_angle_degrees=offset.angle_degrees,
            target_radius=offset.radius,
            allowed_angle_range=_pan_zone_angle_range(
                pan_zone,
                self.config.max_stereo_angle_degrees,
            ),
        )

    def _assign_emitter_pass(
        self,
        emitters: tuple[NoteEmitter, ...],
        candidate_cache: dict[str, tuple[EmitterCandidate, ...]],
        registry: RailRegistry,
        candidate_values: dict[tuple[int, int], int],
        state: _AssignmentState,
        rail_stats: _RailValidationStats,
        center_split_stats: _NoteLevelCenterSplitStats,
        total_start: float,
        pass_name: str,
        allow_center_split: bool,
    ) -> tuple[NoteEmitter, ...]:
        failed_emitters: list[NoteEmitter] = []
        emitters_by_tick: dict[int, list[NoteEmitter]] = defaultdict(list)
        for emitter in emitters:
            emitters_by_tick[emitter.tick].append(emitter)

        sorted_ticks = sorted(emitters_by_tick)
        assigned_or_failed = 0
        for tick_index, tick in enumerate(sorted_ticks, start=1):
            used_slots = state.used_slots_by_tick[tick]
            active_rail_cells = state.active_rail_cells_by_tick[tick]
            tick_emitters = sorted(
                emitters_by_tick[tick],
                key=lambda emitter: (
                    len(candidate_cache.get(emitter.emitter_id, ())),
                    emitter.tick,
                    emitter.emitter_id,
                ),
            )

            for emitter in tick_emitters:
                selected = self._try_assign_emitter(
                    emitter,
                    candidate_cache.get(emitter.emitter_id, ()),
                    tick,
                    registry,
                    candidate_values,
                    state.occupancy,
                    used_slots,
                    active_rail_cells,
                    state.active_rails,
                    state.rail_footprints,
                    state.rails_by_transverse,
                    rail_stats,
                )

                if selected is None and allow_center_split and emitter.pan_zone == "CENTER":
                    center_split_stats.failed_before_split += 1
                    split_assignments = self._try_note_level_center_split(
                        emitter,
                        tick=tick,
                        registry=registry,
                        candidate_values=candidate_values,
                        occupancy=state.occupancy,
                        used_slots=used_slots,
                        active_rail_cells=active_rail_cells,
                        active_rails=state.active_rails,
                        rail_footprints=state.rail_footprints,
                        rails_by_transverse=state.rails_by_transverse,
                        rail_stats=rail_stats,
                        split_stats=center_split_stats,
                    )
                    if split_assignments:
                        state.assignments.extend(split_assignments)
                        selected = split_assignments[0]

                if selected is None:
                    failed_emitters.append(emitter)
                elif not selected.emitter.emitter_id.endswith(":center_split_left"):
                    state.assignments.append(selected)

                assigned_or_failed += 1
                if assigned_or_failed % 1000 == 0:
                    self._log(
                        f"{pass_name} assigning emitters: "
                        f"{assigned_or_failed}/{len(emitters)}"
                    )
                self._check_time_limit(total_start, f"{pass_name} assignment")

            if tick_index % 100 == 0 or tick_index == len(sorted_ticks):
                self._log(
                    f"{pass_name} assigning ticks: {tick_index}/{len(sorted_ticks)}"
                )

        return tuple(failed_emitters)

    def _retry_candidate_cache(
        self,
        emitters: tuple[NoteEmitter, ...],
        pass_name: str,
        allow_adjacent: bool,
        candidate_generation_stats: _CandidateGenerationStats,
    ) -> dict[str, tuple[EmitterCandidate, ...]]:
        cache: dict[str, tuple[EmitterCandidate, ...]] = {}
        for emitter in emitters:
            allowed_zones = (
                _failed_retry_pan_zones(emitter.pan_zone)
                if allow_adjacent
                else (emitter.pan_zone,)
            )
            cache[emitter.emitter_id] = tuple(
                self._emitter_candidates(
                    emitter,
                    candidate_limit=self.config.retry_max_candidates_per_emitter,
                    allow_adjacent=allow_adjacent,
                    y_layers=max(
                        self.config.max_candidate_y_layers * 2,
                        self.config.max_candidate_y_layers + 8,
                    ),
                    lateral_positions=max(
                        self.config.max_candidate_lateral_positions * 2,
                        self.config.max_candidate_lateral_positions + 8,
                    ),
                    radius_tolerance=max(
                        self.config.radius_search_tolerance * 2,
                        self.config.radius_search_tolerance + 4,
                    ),
                    search_radius_limit=max(
                        self.config.pan_zone_search_radius_limit * 2,
                        self.config.pan_zone_search_radius_limit + 8,
                    ),
                    allowed_zones=allowed_zones,
                    generation_stats=candidate_generation_stats,
                    pass_name=pass_name,
                )
            )
        return cache

    def _try_assign_emitter(
        self,
        emitter: NoteEmitter,
        candidates: tuple[EmitterCandidate, ...],
        tick: int,
        registry: RailRegistry,
        candidate_values: dict[tuple[int, int], int],
        occupancy: _FootprintOccupancy,
        used_slots: set[tuple[str, int]],
        active_rail_cells: dict[str, bool],
        active_rails: dict[str, ActivationRail],
        rail_footprints: dict[str, _Footprint],
        rails_by_transverse: dict[int, set[str]],
        rail_stats: _RailValidationStats,
    ) -> SlotAssignment | None:
        for candidate in candidates:
            rail = registry.get_or_create(
                candidate.rail_offset_y,
                candidate.rail_offset_lateral,
                candidate_values.get(
                    (candidate.rail_offset_y, candidate.rail_offset_lateral),
                    0,
                ),
            )
            slot_key = (rail.rail_id, candidate.slot_index)
            if slot_key in used_slots:
                continue

            if rail.rail_id not in active_rails:
                rail_footprint = self._rail_local_footprint(rail)
                if not self._validate_new_rail(
                    rail,
                    rail_footprint,
                    active_rails,
                    rail_footprints,
                    rails_by_transverse,
                    rail_stats,
                ):
                    continue

            rail_has_center_note = active_rail_cells.get(rail.rail_id)
            if rail_has_center_note is False and candidate.slot_index == 0:
                continue

            rail_cell_is_active = rail.rail_id in active_rail_cells
            footprint = self._assignment_footprint(
                emitter,
                candidate,
                rail_cell_is_active=rail_cell_is_active,
            )
            if self._emitter_collides_with_projected_rails(
                self._assignment_local_footprint(
                    emitter,
                    candidate,
                    rail_cell_is_active=rail_cell_is_active,
                ),
                rail.rail_id,
                rail_footprints,
                rails_by_transverse,
            ):
                continue
            if _footprint_collides(occupancy, footprint):
                continue

            slot = ActivationSlot(
                rail_id=rail.rail_id,
                tick=tick,
                slot_index=candidate.slot_index,
                position=candidate.position,
            )
            selected = SlotAssignment(
                emitter=emitter,
                rail=rail,
                slot=slot,
                candidate=candidate,
            )
            _occupy_footprint(occupancy, footprint)
            if rail.rail_id not in active_rails:
                active_rails[rail.rail_id] = rail
                rail_footprints[rail.rail_id] = self._rail_local_footprint(rail)
                for transverse in self._activation_transverse_keys(rail):
                    rails_by_transverse.setdefault(transverse, set()).add(rail.rail_id)
            used_slots.add(slot_key)
            if rail.rail_id not in active_rail_cells:
                active_rail_cells[rail.rail_id] = candidate.slot_index == 0
            elif candidate.slot_index == 0:
                active_rail_cells[rail.rail_id] = True
            return selected

        return None

    def _try_note_level_center_split(
        self,
        emitter: NoteEmitter,
        tick: int,
        registry: RailRegistry,
        candidate_values: dict[tuple[int, int], int],
        occupancy: _FootprintOccupancy,
        used_slots: set[tuple[str, int]],
        active_rail_cells: dict[str, bool],
        active_rails: dict[str, ActivationRail],
        rail_footprints: dict[str, _Footprint],
        rails_by_transverse: dict[int, set[str]],
        rail_stats: _RailValidationStats,
        split_stats: _NoteLevelCenterSplitStats,
    ) -> list[SlotAssignment] | None:
        if not self.config.enable_note_level_center_split:
            return None
        if emitter.pan_zone != "CENTER":
            return None
        if split_stats.attempted >= self.config.max_note_level_center_splits:
            return None

        split_stats.attempted += 1
        left, right = self._center_split_emitters(emitter)
        left_candidates = tuple(self._emitter_candidates(left))
        right_candidates = tuple(self._emitter_candidates(right))
        split_stats.generated_candidates += len(left_candidates) + len(right_candidates)

        occupancy_copy = _copy_footprint_occupancy(occupancy)
        used_slots_copy = set(used_slots)
        active_rail_cells_copy = dict(active_rail_cells)
        active_rails_copy = dict(active_rails)
        rail_footprints_copy = dict(rail_footprints)
        rails_by_transverse_copy = _copy_transverse_index(rails_by_transverse)

        left_assignment = self._try_assign_emitter(
            left,
            left_candidates,
            tick,
            registry,
            candidate_values,
            occupancy_copy,
            used_slots_copy,
            active_rail_cells_copy,
            active_rails_copy,
            rail_footprints_copy,
            rails_by_transverse_copy,
            rail_stats,
        )
        right_assignment = None
        if left_assignment is not None:
            right_assignment = self._try_assign_emitter(
                right,
                right_candidates,
                tick,
                registry,
                candidate_values,
                occupancy_copy,
                used_slots_copy,
                active_rail_cells_copy,
                active_rails_copy,
                rail_footprints_copy,
                rails_by_transverse_copy,
                rail_stats,
            )

        accepted = left_assignment is not None and right_assignment is not None
        reason = "accepted" if accepted else "left_failed"
        if left_assignment is not None and right_assignment is None:
            reason = "right_failed"

        if split_stats.examples is not None and len(split_stats.examples) < 20:
            split_stats.examples.append(
                NoteLevelCenterSplitExample(
                    original_emitter_id=emitter.emitter_id,
                    tick=emitter.tick,
                    layer=emitter.layer,
                    left_emitter_id=left.emitter_id,
                    right_emitter_id=right.emitter_id,
                    left_pan=left.final_panning,
                    right_pan=right.final_panning,
                    accepted=accepted,
                    reason=reason,
                )
            )

        if not accepted:
            split_stats.failed += 1
            return None

        _replace_footprint_occupancy(occupancy, occupancy_copy)
        _replace_set(used_slots, used_slots_copy)
        _replace_dict(active_rail_cells, active_rail_cells_copy)
        _replace_dict(active_rails, active_rails_copy)
        _replace_dict(rail_footprints, rail_footprints_copy)
        _replace_transverse_index(rails_by_transverse, rails_by_transverse_copy)
        split_stats.accepted += 1
        split_stats.emitters_added += 2
        return [left_assignment, right_assignment]

    def _center_split_emitters(
        self,
        emitter: NoteEmitter,
    ) -> tuple[NoteEmitter, NoteEmitter]:
        return (
            self._center_split_emitter(
                emitter,
                side="left",
                panning=self.config.center_split_left_pan,
            ),
            self._center_split_emitter(
                emitter,
                side="right",
                panning=self.config.center_split_right_pan,
            ),
        )

    def _center_split_emitter(
        self,
        emitter: NoteEmitter,
        side: str,
        panning: float,
    ) -> NoteEmitter:
        volume = emitter.final_volume * self.config.center_split_volume_factor
        offset = self._note_offset(volume, panning)
        position = self._position_from_offsets(
            emitter.tick,
            offset.offset_y,
            offset.offset_lateral,
        )
        pan_zone = _pan_zone_for_angle(offset.angle_degrees)
        return NoteEmitter(
            emitter_id=f"{emitter.emitter_id}:center_split_{side}",
            track_id=emitter.track_id,
            layer=emitter.layer,
            tick=emitter.tick,
            instrument=emitter.instrument,
            key=emitter.key,
            final_volume=volume,
            final_panning=panning,
            ideal_position=position,
            ideal_offset_y=offset.offset_y,
            ideal_offset_lateral=offset.offset_lateral,
            ideal_radius=offset.radius,
            pan_zone=pan_zone,
            note_panning=panning,
            layer_panning=100,
            note_pan_delta=panning - 100,
            layer_pan_delta=0,
            final_pan_delta=panning - 100,
            target_angle_degrees=offset.angle_degrees,
            target_radius=offset.radius,
            allowed_angle_range=_pan_zone_angle_range(
                pan_zone,
                self.config.max_stereo_angle_degrees,
            ),
        )

    def _projected_rail_footprint(
        self,
        rail: ActivationRail,
        max_tick: int,
    ) -> _Footprint:
        occupied: list[tuple[BlockPosition, str]] = []
        reserved_air: list[tuple[BlockPosition, str]] = []

        for tick in range(max_tick + 1):
            rail_center = self._position_from_offsets(
                tick,
                rail.offset_y,
                rail.offset_lateral,
            )
            repeater_position = repeater_position_from_note_position(
                rail_center,
                self.track_direction,
            )
            occupied.extend(
                [
                    (rail_center, "track_block"),
                    (below(rail_center), "track_block"),
                    (repeater_position, "repeater"),
                    (below(repeater_position), "track_block"),
                ]
            )
            reserved_air.append((above(rail_center), "reserved_air"))

        return _Footprint(occupied=tuple(occupied), reserved_air=tuple(reserved_air))

    def _rail_local_footprint(self, rail: ActivationRail) -> _Footprint:
        center = BlockPosition(0, rail.offset_y, rail.offset_lateral)
        repeater = BlockPosition(1, rail.offset_y, rail.offset_lateral)
        return _Footprint(
            occupied=(
                (center, "track_block"),
                (below(center), "track_block"),
                (repeater, "repeater"),
                (below(repeater), "track_block"),
            ),
            reserved_air=((above(center), "reserved_air"),),
        )

    def _validate_new_rail(
        self,
        rail: ActivationRail,
        rail_footprint: _Footprint,
        active_rails: dict[str, ActivationRail],
        rail_footprints: dict[str, _Footprint],
        rails_by_transverse: dict[int, set[str]],
        stats: _RailValidationStats,
    ) -> bool:
        rail_center = self._position_from_offsets(
            0,
            rail.offset_y,
            rail.offset_lateral,
        )
        rail_range = self._activation_transverse_range(rail)
        relevant_rail_ids = {
            rail_id
            for transverse in range(rail_range[0], rail_range[1] + 1)
            for rail_id in rails_by_transverse.get(transverse, ())
        }
        stats.candidate_validation_count += 1
        stats.total_rails_checked_per_candidate += len(relevant_rail_ids)
        stats.max_rails_checked_per_candidate = max(
            stats.max_rails_checked_per_candidate,
            len(relevant_rail_ids),
        )
        if stats.candidate_validation_count % 1000 == 0:
            self._log(
                "validating rails: "
                f"candidates={stats.candidate_validation_count} "
                f"rails_checked={stats.rail_pairs_checked}"
            )

        for existing_id in relevant_rail_ids:
            existing = active_rails[existing_id]
            existing_center = self._position_from_offsets(
                0,
                existing.offset_y,
                existing.offset_lateral,
            )
            existing_range = self._activation_transverse_range(existing)
            ranges_overlap = _ranges_overlap(rail_range, existing_range)
            y_gap = abs(rail.offset_y - existing.offset_y)
            stats.rail_pairs_checked += 1

            if ranges_overlap and y_gap < self.config.min_rail_center_y_gap:
                stats.rejected_by_same_plane_y_gap += 1
                self._append_rail_validation_issue(
                    stats,
                    rail,
                    existing,
                    rail_center,
                    existing_center,
                    rail_range,
                    existing_range,
                    ranges_overlap,
                    y_gap,
                    "activation transverse range y gap too small",
                    None,
                )
                return False

            collision_position = _first_footprint_collision(
                rail_footprint,
                rail_footprints[existing.rail_id],
            )
            if collision_position is not None:
                stats.rejected_by_full_footprint_collision += 1
                self._append_rail_validation_issue(
                    stats,
                    rail,
                    existing,
                    rail_center,
                    existing_center,
                    rail_range,
                    existing_range,
                    ranges_overlap,
                    y_gap,
                    "rail footprint collision",
                    collision_position,
                )
                return False

        return True

    def _append_rail_validation_issue(
        self,
        stats: _RailValidationStats,
        rail: ActivationRail,
        existing: ActivationRail,
        rail_center: BlockPosition,
        existing_center: BlockPosition,
        rail_range: tuple[int, int],
        existing_range: tuple[int, int],
        ranges_overlap: bool,
        y_gap: int,
        reason: str,
        collision_position: BlockPosition | None,
    ) -> None:
        if stats.issues is None or len(stats.issues) >= 20:
            return
        stats.issues.append(
            RailValidationIssue(
                rail_a_id=existing.rail_id,
                rail_b_id=rail.rail_id,
                rail_a_center=existing_center,
                rail_b_center=rail_center,
                direction=normalize_direction(self.track_direction),
                rail_a_transverse_range=existing_range,
                rail_b_transverse_range=rail_range,
                activation_ranges_overlap=ranges_overlap,
                y_gap=y_gap,
                min_rail_center_y_gap=self.config.min_rail_center_y_gap,
                reason=reason,
                first_collision_position=collision_position,
            )
        )

    def _activation_transverse_range(
        self,
        rail: ActivationRail,
    ) -> tuple[int, int]:
        radius = max(0, self.config.activation_slot_radius)
        return (rail.offset_lateral - radius, rail.offset_lateral + radius)

    def _activation_transverse_keys(self, rail: ActivationRail) -> range:
        start, end = self._activation_transverse_range(rail)
        return range(start, end + 1)

    def _emitter_collides_with_projected_rails(
        self,
        footprint: _Footprint,
        rail_id: str,
        rail_footprints: dict[str, _Footprint],
        rails_by_transverse: dict[int, set[str]],
    ) -> bool:
        relevant_rail_ids = {
            existing_rail_id
            for position, _ in footprint.occupied
            for existing_rail_id in rails_by_transverse.get(position.z, ())
        } | {
            existing_rail_id
            for position, _ in footprint.reserved_air
            for existing_rail_id in rails_by_transverse.get(position.z, ())
        }
        for existing_rail_id in relevant_rail_ids:
            if existing_rail_id == rail_id:
                continue
            rail_footprint = rail_footprints[existing_rail_id]
            if _first_footprint_collision(footprint, rail_footprint) is not None:
                return True
        return False

    def _assignment_footprint(
        self,
        emitter: NoteEmitter,
        candidate: EmitterCandidate,
        rail_cell_is_active: bool,
    ) -> _Footprint:
        occupied: list[tuple[BlockPosition, str]] = []
        reserved_air: list[tuple[BlockPosition, str]] = []

        if not rail_cell_is_active:
            rail_center = self._position_from_offsets(
                emitter.tick,
                candidate.rail_offset_y,
                candidate.rail_offset_lateral,
            )
            repeater_position = repeater_position_from_note_position(
                rail_center,
                self.track_direction,
            )
            occupied.extend(
                [
                    (below(repeater_position), "track_block"),
                    (repeater_position, "repeater"),
                ]
            )
            if candidate.slot_index != 0:
                occupied.extend(
                    [
                        (rail_center, "track_block"),
                        (below(rail_center), "track_block"),
                    ]
                )

        occupied.extend(
            [
                (candidate.position, "note_block"),
                (below(candidate.position), "instrument_block"),
            ]
        )
        support_position = _gravity_support_position(
            below(candidate.position),
            NoteEvent(
                tick=emitter.tick,
                layer=emitter.layer,
                instrument=emitter.instrument,
                key=emitter.key,
                final_volume=emitter.final_volume,
                final_panning=emitter.final_panning,
            ),
        )
        if support_position is not None:
            occupied.insert(-1, (support_position, "gravity_support_block"))
        reserved_air.append((above(candidate.position), "reserved_air"))

        return _Footprint(occupied=tuple(occupied), reserved_air=tuple(reserved_air))

    def _assignment_local_footprint(
        self,
        emitter: NoteEmitter,
        candidate: EmitterCandidate,
        rail_cell_is_active: bool,
    ) -> _Footprint:
        occupied: list[tuple[BlockPosition, str]] = []
        reserved_air: list[tuple[BlockPosition, str]] = []

        if not rail_cell_is_active:
            rail_center = BlockPosition(
                0,
                candidate.rail_offset_y,
                candidate.rail_offset_lateral,
            )
            repeater_position = BlockPosition(
                1,
                candidate.rail_offset_y,
                candidate.rail_offset_lateral,
            )
            occupied.extend(
                [
                    (below(repeater_position), "track_block"),
                    (repeater_position, "repeater"),
                ]
            )
            if candidate.slot_index != 0:
                occupied.extend(
                    [
                        (rail_center, "track_block"),
                        (below(rail_center), "track_block"),
                    ]
                )

        note_position = BlockPosition(0, candidate.offset_y, candidate.offset_lateral)
        occupied.extend(
            [
                (note_position, "note_block"),
                (below(note_position), "instrument_block"),
            ]
        )
        support_position = _gravity_support_position(
            below(note_position),
            NoteEvent(
                tick=emitter.tick,
                layer=emitter.layer,
                instrument=emitter.instrument,
                key=emitter.key,
                final_volume=emitter.final_volume,
                final_panning=emitter.final_panning,
            ),
        )
        if support_position is not None:
            occupied.insert(-1, (support_position, "gravity_support_block"))
        reserved_air.append((above(note_position), "reserved_air"))

        return _Footprint(occupied=tuple(occupied), reserved_air=tuple(reserved_air))

    def _emitter_candidates(
        self,
        emitter: NoteEmitter,
        candidate_limit: int | None = None,
        allow_adjacent: bool | None = None,
        y_layers: int | None = None,
        lateral_positions: int | None = None,
        radius_tolerance: float | None = None,
        search_radius_limit: int | None = None,
        allowed_zones: tuple[str, ...] | None = None,
        generation_stats: _CandidateGenerationStats | None = None,
        pass_name: str = "pass1",
    ) -> list[EmitterCandidate]:
        if self.config.enable_pan_zone_layout:
            return self._pan_zone_emitter_candidates(
                emitter,
                candidate_limit=candidate_limit,
                allow_adjacent=allow_adjacent,
                y_layers=y_layers,
                lateral_positions=lateral_positions,
                radius_tolerance=radius_tolerance,
                search_radius_limit=search_radius_limit,
                allowed_zones=allowed_zones,
                generation_stats=generation_stats,
                pass_name=pass_name,
            )
        return self._legacy_emitter_candidates(emitter)

    def _legacy_emitter_candidates(self, emitter: NoteEmitter) -> list[EmitterCandidate]:
        candidates: list[EmitterCandidate] = []
        seen: set[tuple[int, int, int]] = set()

        self._add_candidates_for_position(
            candidates,
            seen,
            emitter,
            offset_y=emitter.ideal_offset_y,
            offset_lateral=emitter.ideal_offset_lateral,
            level=0,
            y_movement=0,
            lateral_movement=0,
            slots=(0,),
        )
        self._add_candidates_for_position(
            candidates,
            seen,
            emitter,
            offset_y=emitter.ideal_offset_y,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=0,
            lateral_movement=0,
            slots=(-1, 1),
        )
        for y_movement in (-1, 1):
            self._add_candidates_for_position(
                candidates,
                seen,
                emitter,
                offset_y=emitter.ideal_offset_y + y_movement,
                offset_lateral=emitter.ideal_offset_lateral,
                level=2,
                y_movement=y_movement,
                lateral_movement=0,
            )
        for lateral_movement in (-1, 1):
            self._add_candidates_for_position(
                candidates,
                seen,
                emitter,
                offset_y=emitter.ideal_offset_y,
                offset_lateral=emitter.ideal_offset_lateral + lateral_movement,
                level=3,
                y_movement=0,
                lateral_movement=lateral_movement,
            )
        for y_movement in (-2, 2):
            self._add_candidates_for_position(
                candidates,
                seen,
                emitter,
                offset_y=emitter.ideal_offset_y + y_movement,
                offset_lateral=emitter.ideal_offset_lateral,
                level=4,
                y_movement=y_movement,
                lateral_movement=0,
            )
        for lateral_movement in (-2, 2):
            self._add_candidates_for_position(
                candidates,
                seen,
                emitter,
                offset_y=emitter.ideal_offset_y,
                offset_lateral=emitter.ideal_offset_lateral + lateral_movement,
                level=5,
                y_movement=0,
                lateral_movement=lateral_movement,
            )

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.cost,
                candidate.level,
                abs(candidate.slot_index),
                candidate.slot_index,
            ),
        )

    def _pan_zone_emitter_candidates(
        self,
        emitter: NoteEmitter,
        candidate_limit: int | None = None,
        allow_adjacent: bool | None = None,
        y_layers: int | None = None,
        lateral_positions: int | None = None,
        radius_tolerance: float | None = None,
        search_radius_limit: int | None = None,
        allowed_zones: tuple[str, ...] | None = None,
        generation_stats: _CandidateGenerationStats | None = None,
        pass_name: str = "pass1",
    ) -> list[EmitterCandidate]:
        candidates: list[EmitterCandidate] = []
        seen: set[tuple[int, int, int]] = set()
        max_offset_delta = max(
            0,
            search_radius_limit
            if search_radius_limit is not None
            else self.config.pan_zone_search_radius_limit,
        )
        radius_tolerance_value = max(
            0.0,
            radius_tolerance
            if radius_tolerance is not None
            else self.config.radius_search_tolerance,
        )
        allow_adjacent_value = (
            allow_adjacent
            if allow_adjacent is not None
            else self.config.allow_adjacent_pan_zone_fallback
        )
        allowed_zone_tuple = allowed_zones or _candidate_pan_zones(
            emitter.pan_zone,
            allow_adjacent_value,
        )

        y_radius = min(
            max_offset_delta,
            max(
                0,
                y_layers
                if y_layers is not None
                else self.config.max_candidate_y_layers,
            ),
        )
        lateral_count = max(
            1,
            lateral_positions
            if lateral_positions is not None
            else self.config.max_candidate_lateral_positions,
        )
        ideal_radius = round(emitter.target_radius)
        radius_values = _nearby_values(
            ideal_radius,
            y_radius,
            y_radius * 2 + 1,
            minimum=0,
        )
        angle_values = _angle_values_for_pan_zones(
            allowed_zone_tuple,
            emitter.target_angle_degrees,
            self.config.max_stereo_angle_degrees,
            lateral_count,
        )

        candidate_limit_value = max(
            1,
            candidate_limit
            if candidate_limit is not None
            else self.config.max_candidates_per_emitter,
        )
        generation_limit = candidate_limit_value * 4
        for candidate_angle in angle_values:
            for candidate_radius in radius_values:
                base_y, offset_lateral = _offset_from_radius_angle_values(
                    candidate_radius,
                    candidate_angle,
                )
                for offset_y, depth_mirrored in self._depth_offset_candidates(base_y):
                    if not self.config.allow_negative_depth_offsets and offset_y < 0:
                        continue
                    self._add_pan_zone_candidate_for_offsets(
                        candidates,
                        seen,
                        emitter,
                        offset_y=offset_y,
                        offset_lateral=offset_lateral,
                        depth_mirrored=depth_mirrored,
                        allowed_zones=allowed_zone_tuple,
                        radius_tolerance=radius_tolerance_value,
                        candidate_angle=candidate_angle,
                        candidate_radius=candidate_radius,
                    )
                    if len(candidates) >= generation_limit:
                        break
                if len(candidates) >= generation_limit:
                    break
            if len(candidates) >= generation_limit:
                break

        sorted_candidates = sorted(
            candidates,
            key=lambda candidate: (
                abs(candidate.lateral_movement),
                candidate.cost,
                candidate.radius_error,
                candidate.pan_error_inside_zone,
                candidate.level,
                abs(candidate.slot_index),
                candidate.slot_index,
            ),
        )
        if generation_stats is not None:
            assert generation_stats.candidate_counts_by_pass is not None
            generation_stats.candidate_counts_by_pass[pass_name].append(
                min(len(sorted_candidates), candidate_limit_value)
            )
            if len(sorted_candidates) > candidate_limit_value:
                generation_stats.candidate_truncation_count += 1
                generation_stats.mirror_candidate_truncated_count += sum(
                    1
                    for candidate in sorted_candidates[candidate_limit_value:]
                    if candidate.depth_mirrored
                )

        return sorted_candidates[:candidate_limit_value]

    def _depth_offset_candidates(
        self,
        depth: int,
    ) -> tuple[tuple[int, bool], ...]:
        preferred_sign = 1 if self.config.preferred_depth_sign >= 0 else -1
        preferred = preferred_sign * depth
        if (
            not self.config.enable_depth_mirror_candidates
            or depth == 0
            or not self.config.allow_negative_depth_offsets
        ):
            return ((preferred, False),)

        mirrored = -preferred
        return ((preferred, False), (mirrored, True))

    def _add_pan_zone_candidate_for_offsets(
        self,
        candidates: list[EmitterCandidate],
        seen: set[tuple[int, int, int]],
        emitter: NoteEmitter,
        offset_y: int,
        offset_lateral: int,
        depth_mirrored: bool,
        allowed_zones: tuple[str, ...],
        radius_tolerance: float,
        candidate_angle: float,
        candidate_radius: float,
    ) -> None:
                actual_radius = math.hypot(offset_y, offset_lateral)
                radius_error = abs(actual_radius - emitter.ideal_radius)

                candidate_zone = _pan_zone_for_angle(candidate_angle)
                if candidate_zone not in allowed_zones:
                    return
                candidate_panning = _panning_from_angle(
                    candidate_angle,
                    self.config.max_stereo_angle_degrees,
                )

                pan_error = _angle_error_inside_zone(
                    candidate_angle,
                    candidate_zone,
                    self.config.max_stereo_angle_degrees,
                )
                depth_movement = abs(actual_radius - emitter.target_radius)
                lateral_movement = offset_lateral - emitter.ideal_offset_lateral
                movement_distance = math.hypot(
                    actual_radius - emitter.target_radius,
                    candidate_angle - emitter.target_angle_degrees,
                )
                y_movement = offset_y - emitter.ideal_offset_y
                y_height_penalty = (
                    abs(actual_radius - emitter.target_radius)
                    / max(1.0, self.config.max_hearing_distance)
                )
                adjacent_fallback = candidate_zone != emitter.pan_zone
                level = 0 if movement_distance == 0 else 1
                if depth_mirrored:
                    level = max(level, 1)

                self._add_candidates_for_position(
                    candidates,
                    seen,
                    emitter,
                    offset_y=offset_y,
                    offset_lateral=offset_lateral,
                    level=level,
                    y_movement=y_movement,
                    lateral_movement=lateral_movement,
                    slots=(-1, 0, 1),
                    pan_zone=candidate_zone,
                    candidate_panning=candidate_panning,
                    radius_error=radius_error,
                    pan_error_inside_zone=pan_error,
                    movement_distance=movement_distance,
                    y_height_penalty=y_height_penalty,
                    adjacent_zone_fallback=adjacent_fallback,
                    depth_mirrored=depth_mirrored,
                    chosen_angle_degrees=candidate_angle,
                    chosen_radius=actual_radius,
                )

    def _add_candidates_for_position(
        self,
        candidates: list[EmitterCandidate],
        seen: set[tuple[int, int, int]],
        emitter: NoteEmitter,
        offset_y: int,
        offset_lateral: int,
        level: int,
        y_movement: int,
        lateral_movement: int,
        slots: tuple[int, ...] = (-1, 0, 1),
        pan_zone: str | None = None,
        candidate_panning: float | None = None,
        radius_error: float | None = None,
        pan_error_inside_zone: float | None = None,
        movement_distance: float | None = None,
        y_height_penalty: float = 0,
        adjacent_zone_fallback: bool = False,
        depth_mirrored: bool = False,
        chosen_angle_degrees: float | None = None,
        chosen_radius: float | None = None,
    ) -> None:
        for slot_index in slots:
            key = (offset_y, offset_lateral, slot_index)
            if key in seen:
                continue
            seen.add(key)
            position = self._position_from_offsets(
                emitter.tick,
                offset_y,
                offset_lateral,
            )
            movement = (
                movement_distance
                if movement_distance is not None
                else abs(y_movement) + abs(lateral_movement)
            )
            candidate_radius_error = (
                radius_error
                if radius_error is not None
                else abs(math.hypot(offset_y, offset_lateral) - emitter.ideal_radius)
            )
            candidate_panning_value = (
                candidate_panning
                if candidate_panning is not None
                else self._panning_from_offsets(offset_y, offset_lateral)
            )
            candidate_pan_zone = pan_zone or _pan_zone_for_panning(candidate_panning_value)
            candidate_pan_error = (
                pan_error_inside_zone
                if pan_error_inside_zone is not None
                else _pan_error_inside_zone(
                    emitter.final_panning,
                    candidate_panning_value,
                    emitter.pan_zone,
                )
            )
            candidate_chosen_angle = (
                chosen_angle_degrees
                if chosen_angle_degrees is not None
                else math.degrees(math.atan2(offset_lateral, abs(offset_y)))
            )
            candidate_chosen_radius = (
                chosen_radius
                if chosen_radius is not None
                else math.hypot(offset_y, offset_lateral)
            )
            if self.config.enable_pan_zone_layout:
                lateral_penalty = (
                    abs(lateral_movement) * self.config.lateral_step_penalty
                )
                cost = (
                    candidate_radius_error * 3.0
                    + candidate_pan_error * 0.5
                    + movement * 0.3
                    + lateral_penalty
                    + abs(slot_index) * 0.2
                    + y_height_penalty * 0.2
                )
                cost += self._candidate_pan_hint_score(
                    emitter,
                    candidate_pan_zone,
                )
                if depth_mirrored:
                    cost += self.config.depth_mirror_penalty
                if adjacent_zone_fallback:
                    cost += 10
            else:
                cost = (
                    abs(y_movement)
                    + abs(lateral_movement) * 2
                    + level * 0.01
                    + abs(slot_index) * 0.05
                )
            candidates.append(
                EmitterCandidate(
                    emitter_id=emitter.emitter_id,
                    position=position,
                    offset_y=offset_y,
                    offset_lateral=offset_lateral,
                    rail_offset_y=offset_y,
                    rail_offset_lateral=offset_lateral - slot_index,
                    slot_index=slot_index,
                    level=level,
                    cost=cost,
                    y_movement=y_movement,
                    lateral_movement=lateral_movement,
                    pan_zone=candidate_pan_zone,
                    candidate_panning=candidate_panning_value,
                    radius_error=candidate_radius_error,
                    pan_error_inside_zone=candidate_pan_error,
                    adjacent_zone_fallback=adjacent_zone_fallback,
                    depth_mirrored=depth_mirrored,
                    chosen_angle_degrees=candidate_chosen_angle,
                    chosen_radius=candidate_chosen_radius,
                )
            )

    def _panning_from_offsets(self, offset_y: int, offset_lateral: int) -> float:
        if offset_y == 0 and offset_lateral == 0:
            return 100
        angle_degrees = math.degrees(math.atan2(offset_lateral, offset_y))
        max_angle = _clamp_max_stereo_angle(self.config.max_stereo_angle_degrees)
        if max_angle <= 0:
            return 100
        return max(0.0, min(200.0, 100 + angle_degrees / max_angle * 100))

    def _panning_from_candidate_offsets(
        self,
        offset_y: int,
        offset_lateral: int,
    ) -> float:
        return self._panning_from_offsets(abs(offset_y), offset_lateral)

    def _pan_zone_distribution(
        self,
        emitters: tuple[NoteEmitter, ...],
        assignments: list[SlotAssignment],
        failed_emitters: list[NoteEmitter],
    ) -> list[PanZoneStatistic]:
        emitters_by_zone: dict[str, int] = defaultdict(int)
        assignments_by_zone: dict[str, int] = defaultdict(int)
        failed_by_zone: dict[str, int] = defaultdict(int)
        target_angles_by_zone: dict[str, list[float]] = defaultdict(list)
        chosen_angles_by_zone: dict[str, list[float]] = defaultdict(list)
        target_radii_by_zone: dict[str, list[float]] = defaultdict(list)
        chosen_radii_by_zone: dict[str, list[float]] = defaultdict(list)

        for emitter in emitters:
            emitters_by_zone[emitter.pan_zone] += 1
            target_angles_by_zone[emitter.pan_zone].append(
                emitter.target_angle_degrees
            )
            target_radii_by_zone[emitter.pan_zone].append(emitter.target_radius)
        for assignment in assignments:
            assignments_by_zone[assignment.emitter.pan_zone] += 1
            chosen_angles_by_zone[assignment.emitter.pan_zone].append(
                assignment.candidate.chosen_angle_degrees
            )
            chosen_radii_by_zone[assignment.emitter.pan_zone].append(
                assignment.candidate.chosen_radius
            )
        for emitter in failed_emitters:
            failed_by_zone[emitter.pan_zone] += 1

        stats: list[PanZoneStatistic] = []
        for zone, pan_min, pan_max in PAN_ZONES:
            target_angles = target_angles_by_zone.get(zone, [])
            chosen_angles = chosen_angles_by_zone.get(zone, [])
            target_radii = target_radii_by_zone.get(zone, [])
            chosen_radii = chosen_radii_by_zone.get(zone, [])
            if not (
                emitters_by_zone.get(zone, 0)
                or assignments_by_zone.get(zone, 0)
                or failed_by_zone.get(zone, 0)
            ):
                continue
            stats.append(
                PanZoneStatistic(
                    zone=zone,
                    pan_min=pan_min,
                    pan_max=pan_max,
                    emitter_count=emitters_by_zone.get(zone, 0),
                    assignment_count=assignments_by_zone.get(zone, 0),
                    failed_count=failed_by_zone.get(zone, 0),
                    average_target_angle=(
                        sum(target_angles) / len(target_angles)
                        if target_angles
                        else 0
                    ),
                    average_chosen_angle=(
                        sum(chosen_angles) / len(chosen_angles)
                        if chosen_angles
                        else 0
                    ),
                    average_target_radius=(
                        sum(target_radii) / len(target_radii)
                        if target_radii
                        else 0
                    ),
                    average_chosen_radius=(
                        sum(chosen_radii) / len(chosen_radii)
                        if chosen_radii
                        else 0
                    ),
                    allowed_angle_range=_pan_zone_angle_range(
                        zone,
                        self.config.max_stereo_angle_degrees,
                    ),
                )
            )
        return stats

    def _rail_usage_statistics(
        self,
        assignments: list[SlotAssignment],
        registry: RailRegistry,
    ) -> list[RailUsageStatistic]:
        slots_by_rail_cell: dict[tuple[str, int], set[int]] = defaultdict(set)
        rail_by_id = {rail.rail_id: rail for rail in registry.rails.values()}

        for assignment in assignments:
            slots_by_rail_cell[
                (assignment.rail.rail_id, assignment.slot.tick)
            ].add(assignment.slot.slot_index)

        usage_by_rail: dict[str, list[int]] = defaultdict(list)
        for (rail_id, _), slots in slots_by_rail_cell.items():
            usage_by_rail[rail_id].append(len(slots))

        stats: list[RailUsageStatistic] = []
        for rail_id, slot_counts in sorted(usage_by_rail.items()):
            rail = rail_by_id[rail_id]
            used_slot_count = sum(slot_counts)
            active_cell_count = len(slot_counts)
            stats.append(
                RailUsageStatistic(
                    rail_id=rail.rail_id,
                    offset_y=rail.offset_y,
                    offset_lateral=rail.offset_lateral,
                    candidate_value=rail.candidate_value,
                    active_cell_count=active_cell_count,
                    used_slot_count=used_slot_count,
                    average_used_slots_per_active_cell=(
                        used_slot_count / active_cell_count
                        if active_cell_count
                        else 0
                    ),
                )
            )

        return stats

    def _rail_track_layouts(
        self,
        report: NoteBasedStereoRailLayoutPreview,
    ) -> list[TrackLayoutInfo]:
        rails_by_id = {
            assignment.rail.rail_id: assignment.rail
            for assignment in report.assignments
        }
        infos: list[TrackLayoutInfo] = []

        for rail_id, rail in sorted(rails_by_id.items()):
            radius = math.hypot(rail.offset_y, rail.offset_lateral)
            angle = math.degrees(math.atan2(rail.offset_lateral, rail.offset_y))
            infos.append(
                TrackLayoutInfo(
                    track_id=rail_id,
                    source_track_id=0,
                    layer_id=None,
                    name=rail_id,
                    offset_y=rail.offset_y,
                    offset_lateral=rail.offset_lateral,
                    radius=radius,
                    angle_degrees=angle,
                    original_offset_y=rail.offset_y,
                    original_offset_lateral=rail.offset_lateral,
                    original_radius=radius,
                    original_angle_degrees=angle,
                    fallback="note_based_rail",
                    attempt_count=1,
                    unresolved_stage=None,
                )
            )

        return infos

    def _note_offset(self, final_volume: float, final_panning: float) -> _StereoOffset:
        volume_norm = max(0.0, min(1.0, final_volume / 100))
        distance = self.config.min_distance + (
            self.config.max_hearing_distance - self.config.min_distance
        ) * (1 - volume_norm)
        pan_norm = (final_panning - 100) / 100
        max_angle_degrees = _clamp_max_stereo_angle(
            self.config.max_stereo_angle_degrees
        )
        angle_degrees = pan_norm * max_angle_degrees
        return self._offset_from_radius_angle(distance, angle_degrees)

    def _offset_from_radius_angle(
        self,
        radius: float,
        angle_degrees: float,
    ) -> _StereoOffset:
        angle = math.radians(angle_degrees)
        return _StereoOffset(
            offset_y=round(math.cos(angle) * radius),
            offset_lateral=round(math.sin(angle) * radius),
            radius=radius,
            angle_degrees=angle_degrees,
        )

    def _position_from_offsets(
        self,
        tick: int,
        offset_y: int,
        offset_lateral: int,
    ) -> BlockPosition:
        track_direction = normalize_direction(self.track_direction)
        track_vector = DIRECTION_VECTORS[track_direction]
        lateral_vector = _right_hand_lateral_vector(track_direction)
        cell_origin = add_vector(
            self.origin,
            _scale_vector(track_vector, tick * self.tick_spacing),
        )
        return add_vector(
            add_y(cell_origin, offset_y),
            _scale_vector(lateral_vector, offset_lateral),
        )

# Note-based preview helpers.

def _merge_candidate_values(
    candidate_values: dict[tuple[int, int], int],
    candidate_cache: dict[str, tuple[EmitterCandidate, ...]],
) -> None:
    for candidates in candidate_cache.values():
        for candidate in candidates:
            key = (candidate.rail_offset_y, candidate.rail_offset_lateral)
            candidate_values[key] = candidate_values.get(key, 0) + 1


def _segment_pan_hint_score(
    segment: LayoutSpatialSegmentHint,
    emitter: NoteEmitter,
    candidate_pan_zone: str,
    *,
    max_stereo_angle_degrees: float,
) -> float:
    pan_mode_factor = PAN_MODE_FACTORS.get(segment.pan_mode, 0.0)
    if pan_mode_factor <= 0.0 or segment.layout_hint_weight <= 0.0:
        return 0.0

    target_interval = _segment_pan_target_interval(
        segment.pan_mode,
        emitter,
        max_stereo_angle_degrees=max_stereo_angle_degrees,
    )
    if target_interval is None:
        return 0.0

    effective_weight = segment.layout_hint_weight
    if segment.volume_contour_mode == "insufficient_data":
        effective_weight = min(effective_weight, 0.15)

    candidate_interval = _pan_zone_angle_range(
        candidate_pan_zone,
        max_stereo_angle_degrees,
    )
    angular_distance = _interval_distance(candidate_interval, target_interval)
    angular_pan_penalty = _clamp_unit(angular_distance / 90.0)
    return (
        effective_weight
        * pan_mode_factor
        * PAN_HINT_WEIGHT
        * angular_pan_penalty
    )


def _segment_pan_target_interval(
    pan_mode: str,
    emitter: NoteEmitter,
    *,
    max_stereo_angle_degrees: float,
) -> tuple[float, float] | None:
    if pan_mode in SEGMENT_PAN_TARGET_INTERVALS:
        return SEGMENT_PAN_TARGET_INTERVALS[pan_mode]
    if pan_mode == "bimodal_left_right":
        if emitter.final_panning < 100:
            return _side_pan_target_interval("left", max_stereo_angle_degrees)
        if emitter.final_panning > 100:
            return _side_pan_target_interval("right", max_stereo_angle_degrees)
        return None
    if pan_mode == "center_plus_side":
        note_zone = _pan_zone_for_panning(emitter.final_panning)
        if note_zone == "CENTER":
            return SEGMENT_PAN_TARGET_INTERVALS["center_stable"]
        if emitter.final_panning < 100:
            return SEGMENT_PAN_TARGET_INTERVALS["left_stable"]
        if emitter.final_panning > 100:
            return SEGMENT_PAN_TARGET_INTERVALS["right_stable"]
        return None
    if pan_mode == "wide_or_split":
        if emitter.final_panning < 100:
            return _side_pan_target_interval("left", max_stereo_angle_degrees)
        if emitter.final_panning > 100:
            return _side_pan_target_interval("right", max_stereo_angle_degrees)
        return SEGMENT_PAN_TARGET_INTERVALS["center_stable"]
    return None


def _side_pan_target_interval(
    side: str,
    max_stereo_angle_degrees: float,
) -> tuple[float, float]:
    if side == "left":
        edge_start = _pan_zone_angle_range("L_EDGE", max_stereo_angle_degrees)[0]
        inner_end = _pan_zone_angle_range("L_INNER", max_stereo_angle_degrees)[1]
        return (edge_start, inner_end)
    inner_start = _pan_zone_angle_range("R_INNER", max_stereo_angle_degrees)[0]
    edge_end = _pan_zone_angle_range("R_EDGE", max_stereo_angle_degrees)[1]
    return (inner_start, edge_end)


def _interval_distance(
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    a_min, a_max = a
    b_min, b_max = b
    if a_max < b_min:
        return b_min - a_max
    if b_max < a_min:
        return a_min - b_max
    return 0.0


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _failed_emitter_examples(
    failed_emitters: tuple[NoteEmitter, ...] | list[NoteEmitter],
    limit: int = 20,
) -> tuple[str, ...]:
    return tuple(
        f"{emitter.emitter_id} tick={emitter.tick} zone={emitter.pan_zone} "
        f"note_pan={emitter.note_panning:.1f} "
        f"layer_pan={emitter.layer_panning:.1f} "
        f"note_delta={emitter.note_pan_delta:.1f} "
        f"layer_delta={emitter.layer_pan_delta:.1f} "
        f"final_pan_delta={emitter.final_pan_delta:.1f} "
        f"final_pan={emitter.final_panning:.1f} "
        f"target_angle={emitter.target_angle_degrees:.1f} "
        f"target_radius={emitter.target_radius:.1f} "
        f"allowed_angle_range={emitter.allowed_angle_range} "
        f"volume={emitter.final_volume:.1f}"
        for emitter in list(failed_emitters)[:limit]
    )


def _average_candidate_count_by_pass(
    stats: _CandidateGenerationStats,
) -> tuple[tuple[str, float], ...]:
    if stats.candidate_counts_by_pass is None:
        return ()
    return tuple(
        (pass_name, sum(counts) / len(counts) if counts else 0)
        for pass_name, counts in sorted(stats.candidate_counts_by_pass.items())
    )


def _adjacent_zone_fallback_summary(
    stats: _AssignmentRetryStats,
) -> tuple[tuple[str, int, int, int], ...]:
    if stats.adjacent_by_source_zone is None:
        return ()
    return tuple(
        (zone, values[0], values[1], values[2])
        for zone, values in sorted(stats.adjacent_by_source_zone.items())
        if any(values)
    )


def _failed_count_by_pan_zone(
    failed_emitters: list[NoteEmitter],
) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for emitter in failed_emitters:
        counts[emitter.pan_zone] += 1
    return [
        (zone, counts[zone])
        for zone, _, _ in PAN_ZONES
        if counts.get(zone, 0)
    ]


def _failed_count_by_depth_sign(
    failed_emitters: list[NoteEmitter],
) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for emitter in failed_emitters:
        counts[_depth_sign_name(emitter.ideal_offset_y)] += 1
    return [
        (sign, counts[sign])
        for sign in ("positive", "zero", "negative")
        if counts.get(sign, 0)
    ]


def _depth_sign_name(offset_y: int) -> str:
    if offset_y > 0:
        return "positive"
    if offset_y < 0:
        return "negative"
    return "zero"


def _ranges_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return not (first[1] < second[0] or second[1] < first[0])


def _nearby_values(
    center: int,
    radius: int,
    max_count: int,
    minimum: int | None = None,
) -> tuple[int, ...]:
    values: list[int] = []
    for delta in _nearby_deltas(radius):
        value = center + delta
        if minimum is not None and value < minimum:
            continue
        values.append(value)
        if len(values) >= max_count:
            break
    return tuple(values)


def _nearby_deltas(radius: int) -> tuple[int, ...]:
    deltas = [0]
    for amount in range(1, radius + 1):
        deltas.extend((-amount, amount))
    return tuple(deltas)


def _copy_transverse_index(
    index: dict[int, set[str]],
) -> dict[int, set[str]]:
    return {key: set(value) for key, value in index.items()}


def _replace_transverse_index(
    target: dict[int, set[str]],
    source: dict[int, set[str]],
) -> None:
    target.clear()
    target.update({key: set(value) for key, value in source.items()})


def _replace_dict(target: dict, source: dict) -> None:
    target.clear()
    target.update(source)


def _replace_set(target: set, source: set) -> None:
    target.clear()
    target.update(source)


def _note_based_preview_footprint_entries(
    report: NoteBasedStereoRailLayoutPreview,
) -> tuple[
    list[tuple[BlockPosition, str, str, int]],
    list[tuple[BlockPosition, str, str, int]],
]:
    occupied: list[tuple[BlockPosition, str, str, int]] = []
    reserved_air: list[tuple[BlockPosition, str, str, int]] = []
    assignments_by_rail_tick: dict[tuple[str, int], list[SlotAssignment]] = defaultdict(list)
    rails_by_id = {
        assignment.rail.rail_id: assignment.rail
        for assignment in report.assignments
    }

    for assignment in report.assignments:
        assignments_by_rail_tick[
            (assignment.rail.rail_id, assignment.emitter.tick)
        ].append(assignment)

    for rail_id, rail in sorted(rails_by_id.items()):
        rail_ticks = [
            tick
            for assignment_rail_id, tick in assignments_by_rail_tick
            if assignment_rail_id == rail_id
        ]
        if not rail_ticks:
            continue

        for tick in range(max(rail_ticks) + 1):
            cell_assignments = assignments_by_rail_tick.get((rail_id, tick), [])
            center_assignment = next(
                (
                    assignment
                    for assignment in cell_assignments
                    if assignment.slot.slot_index == 0
                ),
                None,
            )
            rail_center = _note_based_preview_position(
                report,
                tick,
                rail.offset_y,
                rail.offset_lateral,
            )
            repeater_position = repeater_position_from_note_position(
                rail_center,
                report.track_direction,
            )

            if center_assignment is None:
                occupied.extend(
                    [
                        (below(repeater_position), "track_block", rail_id, tick),
                        (repeater_position, "repeater", rail_id, tick),
                        (rail_center, "track_block", rail_id, tick),
                        (below(rail_center), "track_block", rail_id, tick),
                    ]
                )
            else:
                occupied.extend(
                    [
                        (below(repeater_position), "track_block", rail_id, tick),
                        (repeater_position, "repeater", rail_id, tick),
                    ]
                )
                _append_note_based_emitter_footprint(
                    occupied,
                    reserved_air,
                    center_assignment,
                    owner_id=rail_id,
                )

            for assignment in cell_assignments:
                if assignment.slot.slot_index == 0:
                    continue
                _append_note_based_emitter_footprint(
                    occupied,
                    reserved_air,
                    assignment,
                    owner_id=rail_id,
                )

    return occupied, reserved_air


def _append_note_based_emitter_footprint(
    occupied: list[tuple[BlockPosition, str, str, int]],
    reserved_air: list[tuple[BlockPosition, str, str, int]],
    assignment: SlotAssignment,
    owner_id: str,
) -> None:
    position = assignment.slot.position
    tick = assignment.emitter.tick
    instrument_position = below(position)
    support_position = _gravity_support_position(
        instrument_position,
        NoteEvent(
            tick=tick,
            layer=assignment.emitter.layer,
            instrument=assignment.emitter.instrument,
            key=assignment.emitter.key,
            final_volume=assignment.emitter.final_volume,
            final_panning=assignment.emitter.final_panning,
        ),
    )
    if support_position is not None:
        occupied.append((support_position, "gravity_support_block", owner_id, tick))
    occupied.extend(
        [
            (instrument_position, "instrument_block", owner_id, tick),
            (position, "note_block", owner_id, tick),
        ]
    )
    reserved_air.append((above(position), "reserved_air", owner_id, tick))


def _note_based_preview_position(
    report: NoteBasedStereoRailLayoutPreview,
    tick: int,
    offset_y: int,
    offset_lateral: int,
) -> BlockPosition:
    track_direction = normalize_direction(report.track_direction)
    track_vector = DIRECTION_VECTORS[track_direction]
    lateral_vector = _right_hand_lateral_vector(track_direction)
    cell_origin = add_vector(
        report.origin,
        _scale_vector(track_vector, tick * report.tick_spacing),
    )
    return add_vector(
        add_y(cell_origin, offset_y),
        _scale_vector(lateral_vector, offset_lateral),
    )

NoteBasedStereoRailLayout = NoteBasedStereoLayout
