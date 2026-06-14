from __future__ import annotations

import math
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, replace

from .layout_basic import (
    BasicLinearLayout,
    _find_single_track_conflicts,
    _notes_by_tick_for_notes,
)
from .layout_collision import (
    _Footprint,
    _FootprintOccupancy,
    _can_share_position,
    _cell_occupied_blocks,
    _cell_reserved_air_blocks,
    _copy_footprint_occupancy,
    _detect_block_collisions,
    _detect_footprint_entry_collisions,
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
    LEGACY_DIRECTIONS,
    OPPOSITE_DIRECTIONS,
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
    CenterSplitEvent,
    CollisionExample,
    CollisionSummary,
    EmitterCandidate,
    LayoutCell,
    LayoutConflict,
    LayoutResult,
    LayoutStrategy,
    NoteBasedStereoRailLayoutPreview,
    NoteEmitter,
    NoteLevelCenterSplitExample,
    PanZoneStatistic,
    PlacedNote,
    RailRegistry,
    RailUsageStatistic,
    RailValidationIssue,
    SlotAssignment,
    SpatialLayoutStrategy,
    StageTiming,
    StereoLayoutConfig,
    TrackLayoutInfo,
    _StereoOffset,
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
    _pan_zone_for_lateral,
    _pan_zone_for_panning,
    _pan_zone_lateral_range,
    _panning_from_angle,
    _representative_angle_for_zone,
    _representative_lateral_for_zone,
    _representative_panning_for_zone,
    _lateral_error_inside_zone,
    _lateral_values_for_pan_zones,
)
from .layout_note_stereo import (
    NoteBasedStereoLayout,
    NoteBasedStereoRailLayout,
    _AssignmentRetryStats,
    _AssignmentState,
    _CandidateGenerationStats,
    _NoteLevelCenterSplitStats,
    _RailValidationStats,
)
from .layout_track_stereo import TrackBasedStereoLayout
from .models import NoteEvent, Song, Track


SingleTrackLayout = BasicLinearLayout


def layout_song(
    song: Song,
    layout: LayoutStrategy | None = None,
) -> LayoutResult:
    """Place a song using the current default layout strategy."""

    strategy = layout or BasicLinearLayout()
    return strategy.layout_song(song)


def build_layout_strategy(
    mode: str,
    origin: BlockPosition,
    track_direction: str,
    selected_track_id: int | None,
    stereo_config: StereoLayoutConfig | None = None,
) -> LayoutStrategy:
    if mode == "basic_linear":
        return BasicLinearLayout(
            origin=origin,
            track_direction=track_direction,
            selected_track_id=selected_track_id,
        )
    if mode == "track_based_stereo":
        return TrackBasedStereoLayout(
            origin=origin,
            track_direction=track_direction,
            config=stereo_config or StereoLayoutConfig(),
        )
    if mode == "note_based_stereo":
        return NoteBasedStereoLayout(
            origin=origin,
            track_direction=track_direction,
            config=stereo_config or StereoLayoutConfig(),
        )
    raise LayoutError(f"Unsupported layout mode: {mode}")
