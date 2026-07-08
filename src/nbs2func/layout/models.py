from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .geometry import BlockPosition
from ..core.models import Song


@dataclass(frozen=True)
class PlacedNote:
    """A note with its final layout coordinates."""

    tick: int
    track_id: str
    source_track_id: int
    layer: int
    instrument: int
    key: int
    final_volume: float
    final_panning: float
    track_volume: float
    track_panning: float
    virtual_role: str | None
    note_block_position: BlockPosition
    instrument_block_position: BlockPosition
    split_reason: str | None = None
    split_mode: str | None = None


@dataclass(frozen=True)
class LayoutCell:
    """A generated time-step cell with all block coordinates resolved."""

    tick: int
    track_id: str
    source_track_id: int
    repeater_position: BlockPosition
    repeater_facing: str
    track_block_position: BlockPosition
    note_block_position: BlockPosition
    instrument_block_position: BlockPosition
    gravity_support_block_position: BlockPosition | None = None
    note: PlacedNote | None = None


@dataclass(frozen=True)
class LayoutConflict:
    """A single-track conflict found before layout placement."""

    tick: int
    track_id: int | str
    note_count: int


@dataclass(frozen=True)
class BlockCollision:
    """A hard layout error in occupied blocks or reserved air space."""

    position: BlockPosition
    first_block_type: str
    first_track_id: str
    first_tick: int
    second_block_type: str
    second_track_id: str
    second_tick: int
    collision_type: str = "occupied_occupied"


@dataclass(frozen=True)
class CollisionExample:
    """One representative coordinate for an aggregated collision summary."""

    position: BlockPosition
    first_block_type: str
    first_tick: int
    second_block_type: str
    second_tick: int


@dataclass(frozen=True)
class TrackLayoutInfo:
    """Diagnostic metadata for a laid out track."""

    track_id: str
    source_track_id: int
    layer_id: int | None
    name: str
    offset_y: int
    offset_lateral: int
    radius: float
    angle_degrees: float
    original_offset_y: int
    original_offset_lateral: int
    original_radius: float
    original_angle_degrees: float
    fallback: str
    attempt_count: int
    unresolved_stage: str | None
    virtual_role: str | None = None
    split_reason: str | None = None
    split_mode: str | None = None


@dataclass(frozen=True)
class CenterSplitEvent:
    """Diagnostic record for one generated center-split clone."""

    original_track_id: int
    original_layer_id: int | None
    original_track_name: str
    clone_track_id: str
    clone_side: str
    split_reason: str
    split_mode: str
    before_offset_y: int
    before_offset_lateral: int
    before_radius: float
    before_angle_degrees: float
    after_offset_y: int
    after_offset_lateral: int
    after_radius: float
    after_angle_degrees: float


@dataclass(frozen=True)
class CollisionSummary:
    """Track-level summary for repeated hard block collisions."""

    first_track: TrackLayoutInfo
    second_track: TrackLayoutInfo
    collision_type: str
    estimated_cell_count: int
    examples: tuple[CollisionExample, ...]


@dataclass(frozen=True)
class ActivationRail:
    """One straight activation rail in the note-based preview."""

    rail_id: str
    offset_y: int
    offset_lateral: int
    candidate_value: int


@dataclass(frozen=True)
class ActivationSlot:
    """One of the three emitter slots a rail can activate at one tick."""

    rail_id: str
    tick: int
    slot_index: int
    position: BlockPosition


@dataclass(frozen=True)
class NoteEmitter:
    """A note event with its ideal note-based emitter position."""

    emitter_id: str
    track_id: int
    layer: int
    tick: int
    instrument: int
    key: int
    final_volume: float
    final_panning: float
    ideal_position: BlockPosition
    ideal_offset_y: int
    ideal_offset_lateral: int
    ideal_radius: float = 0
    pan_zone: str = ""
    note_panning: float = 100
    layer_panning: float = 100
    note_pan_delta: float = 0
    layer_pan_delta: float = 0
    final_pan_delta: float = 0
    target_angle_degrees: float = 0
    target_radius: float = 0
    allowed_angle_range: tuple[float, float] = (0, 0)


@dataclass(frozen=True)
class EmitterCandidate:
    """A candidate rail slot for one emitter."""

    emitter_id: str
    position: BlockPosition
    offset_y: int
    offset_lateral: int
    rail_offset_y: int
    rail_offset_lateral: int
    slot_index: int
    level: int
    cost: float
    y_movement: int
    lateral_movement: int
    pan_zone: str = ""
    candidate_panning: float = 100
    radius_error: float = 0
    pan_error_inside_zone: float = 0
    adjacent_zone_fallback: bool = False
    depth_mirrored: bool = False
    chosen_angle_degrees: float = 0
    chosen_radius: float = 0


@dataclass(frozen=True)
class SlotAssignment:
    """A selected candidate for one emitter."""

    emitter: NoteEmitter
    rail: ActivationRail
    slot: ActivationSlot
    candidate: EmitterCandidate


@dataclass(frozen=True)
class RailUsageStatistic:
    """Usage summary for one activation rail."""

    rail_id: str
    offset_y: int
    offset_lateral: int
    candidate_value: int
    active_cell_count: int
    used_slot_count: int
    average_used_slots_per_active_cell: float


@dataclass(frozen=True)
class PanZoneStatistic:
    """How many emitters and assignments belong to one panning zone."""

    zone: str
    pan_min: float
    pan_max: float
    emitter_count: int
    assignment_count: int
    failed_count: int = 0
    average_target_angle: float = 0
    average_chosen_angle: float = 0
    average_target_radius: float = 0
    average_chosen_radius: float = 0
    allowed_angle_range: tuple[float, float] = (0, 0)


@dataclass(frozen=True)
class RailValidationIssue:
    """One rejected activation rail pair from projected rail validation."""

    rail_a_id: str
    rail_b_id: str
    rail_a_center: BlockPosition
    rail_b_center: BlockPosition
    direction: str
    rail_a_transverse_range: tuple[int, int]
    rail_b_transverse_range: tuple[int, int]
    activation_ranges_overlap: bool
    y_gap: int
    min_rail_center_y_gap: int
    reason: str
    first_collision_position: BlockPosition | None = None


@dataclass(frozen=True)
class StageTiming:
    """Elapsed time for one note-based preview stage."""

    stage: str
    seconds: float


@dataclass(frozen=True)
class NoteLevelCenterSplitExample:
    """One note-level center split fallback attempt."""

    original_emitter_id: str
    tick: int
    layer: int
    left_emitter_id: str
    right_emitter_id: str
    left_pan: float
    right_pan: float
    accepted: bool
    reason: str


@dataclass(frozen=True)
class _StereoOffset:
    offset_y: int
    offset_lateral: int
    radius: float
    angle_degrees: float


@dataclass
class RailRegistry:
    """Registry of activation rails considered by note-based preview."""

    rails: dict[tuple[int, int], ActivationRail]

    def get_or_create(
        self,
        offset_y: int,
        offset_lateral: int,
        candidate_value: int = 0,
    ) -> ActivationRail:
        key = (offset_y, offset_lateral)
        rail = self.rails.get(key)
        if rail is not None:
            return rail

        rail = ActivationRail(
            rail_id=f"rail_{offset_y}_{offset_lateral}",
            offset_y=offset_y,
            offset_lateral=offset_lateral,
            candidate_value=candidate_value,
        )
        self.rails[key] = rail
        return rail


@dataclass(frozen=True)
class NoteBasedStereoRailLayoutPreview:
    """Summary and assignments for traditional redstone note-based preview."""

    total_note_events: int
    total_ideal_emitters: int
    total_activation_rails: int
    unchanged_assignments: int
    y_movement_assignments: int
    z_movement_assignments: int
    failed_assignment_count: int
    average_movement_cost: float
    max_movement_cost: float
    average_used_slots_per_active_rail_cell: float
    rail_usage_statistics: tuple[RailUsageStatistic, ...]
    assignments: tuple[SlotAssignment, ...]
    failed_emitters: tuple[NoteEmitter, ...]
    origin: BlockPosition
    track_direction: str
    tick_spacing: int
    pan_zone_distribution: tuple[PanZoneStatistic, ...] = ()
    pan_zone_unchanged_count: int = 0
    adjacent_zone_fallback_count: int = 0
    average_radius_error: float = 0
    max_radius_error: float = 0
    average_pan_error_inside_zone: float = 0
    rail_collision_count_before: int | None = None
    rail_collision_count_after: int | None = None
    rail_pairs_checked: int = 0
    rail_pairs_rejected_by_same_plane_y_gap: int = 0
    rail_pairs_rejected_by_full_footprint_collision: int = 0
    invalid_rail_pairs: tuple[RailValidationIssue, ...] = ()
    total_candidates_generated: int = 0
    average_candidates_per_emitter: float = 0
    max_candidates_for_one_emitter: int = 0
    average_rails_checked_per_candidate: float = 0
    max_rails_checked_per_candidate: int = 0
    collision_records_stored: int = 0
    collision_records_skipped_due_to_cap: int = 0
    stage_timings: tuple[StageTiming, ...] = ()
    time_limit_exceeded: bool = False
    center_split_attempted_count: int = 0
    center_split_accepted_count: int = 0
    center_split_failed_count: int = 0
    emitters_added_by_center_split: int = 0
    failed_assignment_count_before_split: int = 0
    failed_assignment_count_after_split: int = 0
    center_split_examples: tuple[NoteLevelCenterSplitExample, ...] = ()
    positive_depth_rail_count: int = 0
    negative_depth_rail_count: int = 0
    positive_depth_assignments: int = 0
    negative_depth_assignments: int = 0
    mirror_fallback_accepted_count: int = 0
    mirror_fallback_rejected_count: int = 0
    failed_assignment_count_by_pan_zone: tuple[tuple[str, int], ...] = ()
    failed_assignment_count_by_depth_sign: tuple[tuple[str, int], ...] = ()
    average_positive_depth_assignment_cost: float = 0
    average_negative_depth_assignment_cost: float = 0
    failed_assignment_count_after_pass1: int = 0
    failed_assignment_count_after_pass2: int = 0
    failed_assignment_count_after_pass3: int = 0
    retry_attempted_count: int = 0
    retry_accepted_count: int = 0
    retry_failed_count: int = 0
    adjacent_zone_fallback_attempted_count: int = 0
    adjacent_zone_fallback_accepted_count: int = 0
    adjacent_zone_fallback_failed_count: int = 0
    adjacent_zone_fallback_by_source_zone: tuple[tuple[str, int, int, int], ...] = ()
    pass1_assignment_seconds: float = 0
    pass2_retry_candidate_generation_seconds: float = 0
    pass2_candidate_value_merge_seconds: float = 0
    pass2_assignment_seconds: float = 0
    pass3_retry_candidate_generation_seconds: float = 0
    pass3_candidate_value_merge_seconds: float = 0
    pass3_assignment_seconds: float = 0
    same_side_split_seconds: float = 0
    note_level_center_split_seconds: float = 0
    final_fallback_split_handling_seconds: float = 0
    pass2_retry_emitter_count: int = 0
    pass2_retry_total_candidates_generated: int = 0
    pass2_retry_average_candidates_per_emitter: float = 0
    pass2_retry_max_candidates_for_one_emitter: int = 0
    pass3_retry_emitter_count: int = 0
    pass3_retry_total_candidates_generated: int = 0
    pass3_retry_average_candidates_per_emitter: float = 0
    pass3_retry_max_candidates_for_one_emitter: int = 0
    candidate_truncation_count: int = 0
    mirror_candidate_truncated_count: int = 0
    average_candidate_count_by_pass: tuple[tuple[str, float], ...] = ()
    candidate_count_before_truncation_by_pass: tuple[tuple[str, int], ...] = ()
    candidate_count_after_truncation_by_pass: tuple[tuple[str, int], ...] = ()
    candidate_truncation_count_by_pass: tuple[tuple[str, int], ...] = ()
    mirror_candidate_truncation_count_by_pass: tuple[tuple[str, int], ...] = ()
    total_note_based_layout_seconds: float = 0
    ideal_emitter_build_seconds: float = 0
    candidate_generation_seconds: float = 0
    assignment_total_seconds: float = 0
    rail_validation_total_seconds: float = 0
    footprint_collision_total_seconds: float = 0
    rail_center_upgrade_total_seconds: float = 0
    retry_total_seconds: float = 0
    center_split_total_seconds: float = 0
    debug_report_build_seconds: float = 0
    candidate_attempt_count_total: int = 0
    candidate_attempt_count_by_pass: tuple[tuple[str, int], ...] = ()
    candidate_attempts_on_existing_active_rail: int = 0
    candidate_attempts_requiring_new_rail_validation: int = 0
    candidate_attempts_rejected_before_rail_validation: int = 0
    candidate_attempts_rejected_by_slot_used: int = 0
    candidate_attempts_rejected_by_rail_validation: int = 0
    candidate_attempts_rejected_by_footprint_collision: int = 0
    candidate_attempts_accepted: int = 0
    rail_validation_call_count: int = 0
    rail_validation_call_count_by_pass: tuple[tuple[str, int], ...] = ()
    rail_validation_elapsed_seconds: float = 0
    rail_pairs_checked_by_pass: tuple[tuple[str, int], ...] = ()
    rail_validation_accepted_count: int = 0
    rail_validation_rejected_by_activation_overlap: int = 0
    footprint_collision_check_count: int = 0
    average_footprint_collision_seconds: float = 0
    assignment_footprint_collision_elapsed_seconds: float = 0
    rail_footprint_collision_elapsed_seconds: float = 0
    upgrade_footprint_collision_elapsed_seconds: float = 0
    rail_center_upgrade_attempted: int = 0
    rail_center_upgrade_accepted: int = 0
    rail_center_upgrade_rejected: int = 0
    rail_center_upgrade_rejected_by_missing_track_block: int = 0
    rail_center_upgrade_rejected_by_center_footprint_collision: int = 0
    rail_center_upgrade_rejected_by_reserved_air_collision: int = 0
    rail_center_upgrade_occupancy_copy_count: int = 0
    rail_center_upgrade_local_rollback_count: int = 0
    rail_center_upgrade_local_remove_count: int = 0
    geometry_skeleton_cache_hits: int = 0
    geometry_skeleton_cache_misses: int = 0
    geometry_skeleton_unique_key_count: int = 0
    geometry_skeleton_candidates_generated: int = 0
    geometry_skeleton_candidates_reused: int = 0
    geometry_skeleton_cache_hit_rate: float = 0
    geometry_skeleton_top_key_counts: tuple[tuple[str, int], ...] = ()
    failed_examples_after_pass1: tuple[str, ...] = ()
    failed_examples_after_pass2: tuple[str, ...] = ()
    failed_examples_after_pass3: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayoutResult:
    """Cells, placed notes, and conflicts produced by a layout strategy."""

    mode: str
    cells: tuple[LayoutCell, ...]
    notes: tuple[PlacedNote, ...]
    conflicts: tuple[LayoutConflict, ...]
    collisions: tuple[BlockCollision, ...] = ()
    track_layouts: tuple[TrackLayoutInfo, ...] = ()
    collision_summaries: tuple[CollisionSummary, ...] = ()
    center_split_events: tuple[CenterSplitEvent, ...] = ()
    note_based_preview: NoteBasedStereoRailLayoutPreview | None = None


class LayoutStrategy(Protocol):
    """Interface for replaceable note-to-Minecraft-coordinate strategies."""

    def layout_song(self, song: Song) -> LayoutResult:
        """Convert a song into placed cells and notes."""


SpatialLayoutStrategy = LayoutStrategy


@dataclass(frozen=True)
class LayoutProgressEvent:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    key: str | None = None


@dataclass(frozen=True)
class StereoLayoutConfig:
    """Parameters for stable track-level stereo placement."""

    max_hearing_distance: float = 48
    min_distance: float = 4
    max_stereo_angle_degrees: float = 90
    center_threshold: float = 10
    center_split_policy: str = "auto_on_collision"
    center_split_overrides: dict[int, str] | None = None
    center_split_mode: str = "duplicate_half_volume"
    center_split_pan: float = 50
    max_auto_center_splits: int = 20
    enable_collision_resolver: bool = True
    enable_depth_mirror_fallback: bool = True
    enable_radius_relax_fallback: bool = True
    max_angle_deviation_degrees: float = 30
    angle_search_step_degrees: float = 5
    radius_relax_step: float = 1
    max_radius_relax: float = 3
    min_world_y: int | None = None
    max_world_y: int | None = None
    enable_pan_zone_layout: bool = True
    enable_pan_normalization: bool = True
    allow_adjacent_pan_zone_fallback: bool = False
    pan_zone_search_radius_limit: int = 8
    max_candidates_per_emitter: int = 64
    max_candidate_y_layers: int = 8
    max_candidate_lateral_positions: int = 16
    radius_search_tolerance: float = 4
    max_lateral_distance: int = 48
    pan_zone_reference_radius: float = 48
    min_rail_center_y_gap: int = 4
    activation_slot_radius: int = 1
    max_collision_records: int = 5000
    max_collision_examples_per_group: int = 20
    preview_time_limit_seconds: float = 600
    fail_fast_on_too_many_collisions: bool = True
    max_collision_records_before_abort: int = 50000
    enable_progress_logging: bool = False
    progress_callback: Callable[[LayoutProgressEvent], None] | None = None
    enable_note_level_center_split: bool = True
    center_split_left_pan: float = 75
    center_split_right_pan: float = 125
    center_split_volume_factor: float = 0.5
    max_note_level_center_splits: int = 100
    enable_depth_mirror_candidates: bool = True
    preferred_depth_sign: int = 1
    allow_negative_depth_offsets: bool = True
    depth_mirror_penalty: float = 0.0
    lateral_step_penalty: float = 0.5
    allow_adjacent_pan_zone_fallback_for_failed: bool = True
    adjacent_zone_fallback_only_after_strict_failed: bool = True
    retry_max_candidates_per_emitter: int = 256
    enable_same_side_zone_split_fallback: bool = False
    same_side_split_only_on_failed_assignment: bool = True
    same_side_split_volume_factor: float = 0.5
