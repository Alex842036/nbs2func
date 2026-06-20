import unittest
from dataclasses import replace

import nbs2func.layout_note_stereo as note_stereo
from nbs2func.layout_collision import (
    _Footprint,
    _FootprintOccupancy,
    _footprint_collides,
)
from nbs2func.layout_geometry import above, below
from nbs2func.layout import (
    ActivationRail,
    BlockPosition,
    BlockCollision,
    NoteBasedStereoLayout,
    NoteBasedStereoRailLayoutPreview,
    StereoLayoutConfig,
    TrackBasedStereoLayout,
    _RailValidationStats,
    _summarize_block_collisions,
    build_layout_strategy,
)
from nbs2func.layout_spatial_analyzer import (
    LayoutSpatialSegmentHint,
    analyze_layout_spatial,
    build_layout_spatial_hint_index,
)
from nbs2func.layout_models import EmitterCandidate, RailRegistry
from nbs2func.models import NoteEvent, Song, Track


class NoteBasedStereoRailPreviewTest(unittest.TestCase):
    def test_note_based_layout_returns_preview_without_generation_cells(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_three_note_song())

        self.assertEqual(layout.mode, "note_based_stereo_preview")
        self.assertEqual(layout.notes, ())
        self.assertGreater(len(layout.cells), 0)
        self.assertIsInstance(
            layout.note_based_preview,
            NoteBasedStereoRailLayoutPreview,
        )

        preview = layout.note_based_preview
        assert preview is not None
        self.assertEqual(preview.total_note_events, 3)
        self.assertEqual(preview.total_ideal_emitters, 3)
        self.assertEqual(preview.failed_assignment_count, 0)
        self.assertEqual(len(preview.assignments), 3)

    def test_note_based_layout_constructs_without_spatial_hints(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )

        self.assertIsNone(layout._get_layout_spatial_segment_hint(0, 0))

    def test_note_based_layout_can_query_spatial_hints(self) -> None:
        analysis = analyze_layout_spatial(_three_note_song())
        hint_index = build_layout_spatial_hint_index(analysis)
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            spatial_hint_index=hint_index,
        )

        hint = layout._get_layout_spatial_segment_hint(1, 0)

        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint.layer_id, 1)

    def test_default_preview_time_limit_is_600_seconds(self) -> None:
        self.assertEqual(StereoLayoutConfig().preview_time_limit_seconds, 600)

    def test_preview_time_limit_override_is_preserved(self) -> None:
        config = StereoLayoutConfig(preview_time_limit_seconds=42)

        self.assertEqual(config.preview_time_limit_seconds, 42)

    def test_note_based_preview_has_performance_diagnostics(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_three_note_song()).note_based_preview
        assert preview is not None

        numeric_fields = (
            "total_note_based_layout_seconds",
            "ideal_emitter_build_seconds",
            "candidate_generation_seconds",
            "assignment_total_seconds",
            "rail_validation_total_seconds",
            "footprint_collision_total_seconds",
            "rail_center_upgrade_total_seconds",
            "retry_total_seconds",
            "center_split_total_seconds",
            "debug_report_build_seconds",
            "candidate_attempt_count_total",
            "candidate_attempts_on_existing_active_rail",
            "candidate_attempts_requiring_new_rail_validation",
            "candidate_attempts_rejected_before_rail_validation",
            "candidate_attempts_rejected_by_slot_used",
            "candidate_attempts_rejected_by_rail_validation",
            "candidate_attempts_rejected_by_footprint_collision",
            "candidate_attempts_accepted",
            "rail_validation_call_count",
            "rail_validation_elapsed_seconds",
            "rail_validation_accepted_count",
            "rail_validation_rejected_by_activation_overlap",
            "footprint_collision_check_count",
            "average_footprint_collision_seconds",
            "assignment_footprint_collision_elapsed_seconds",
            "rail_footprint_collision_elapsed_seconds",
            "upgrade_footprint_collision_elapsed_seconds",
            "rail_center_upgrade_attempted",
            "rail_center_upgrade_accepted",
            "rail_center_upgrade_rejected",
            "geometry_skeleton_cache_hits",
            "geometry_skeleton_cache_misses",
            "geometry_skeleton_unique_key_count",
            "geometry_skeleton_candidates_generated",
            "geometry_skeleton_candidates_reused",
            "geometry_skeleton_cache_hit_rate",
        )
        tuple_fields = (
            "candidate_attempt_count_by_pass",
            "rail_validation_call_count_by_pass",
            "rail_pairs_checked_by_pass",
            "candidate_count_before_truncation_by_pass",
            "candidate_count_after_truncation_by_pass",
            "candidate_truncation_count_by_pass",
            "mirror_candidate_truncation_count_by_pass",
            "geometry_skeleton_top_key_counts",
        )

        for field in numeric_fields:
            self.assertGreaterEqual(getattr(preview, field), 0)
        for field in tuple_fields:
            self.assertIsInstance(getattr(preview, field), tuple)
        self.assertGreater(preview.candidate_attempt_count_total, 0)
        self.assertGreater(preview.candidate_attempts_accepted, 0)

    def test_geometry_skeleton_cache_preserves_candidate_order(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]

        uncached = layout._emitter_candidates(emitter)
        cache: dict = {}
        perf_stats = note_stereo._PerformanceStats()
        cached = layout._emitter_candidates(
            emitter,
            geometry_skeleton_cache=cache,
            perf_stats=perf_stats,
        )

        self.assertEqual(cached, uncached)
        self.assertEqual(perf_stats.geometry_skeleton_cache_misses, 1)
        self.assertEqual(perf_stats.geometry_skeleton_cache_hits, 0)
        self.assertEqual(len(cache), 1)

    def test_geometry_skeleton_cache_hits_for_repeated_geometry(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitters = layout._ideal_emitters(_two_tick_song())
        cache: dict = {}
        perf_stats = note_stereo._PerformanceStats()

        first = layout._emitter_candidates(
            emitters[0],
            geometry_skeleton_cache=cache,
            perf_stats=perf_stats,
        )
        second = layout._emitter_candidates(
            emitters[1],
            geometry_skeleton_cache=cache,
            perf_stats=perf_stats,
        )

        self.assertEqual(len(cache), 1)
        self.assertEqual(perf_stats.geometry_skeleton_cache_misses, 1)
        self.assertEqual(perf_stats.geometry_skeleton_cache_hits, 1)
        self.assertGreater(perf_stats.geometry_skeleton_candidates_generated, 0)
        self.assertEqual(
            perf_stats.geometry_skeleton_candidates_reused,
            perf_stats.geometry_skeleton_candidates_generated,
        )
        self.assertNotEqual(first[0].position, second[0].position)
        self.assertEqual(first[0].cost, second[0].cost)

    def test_geometry_skeleton_cache_separates_different_pan_zones(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        cache: dict = {}
        perf_stats = note_stereo._PerformanceStats()

        for emitter in layout._ideal_emitters(_pan_zone_song()):
            layout._emitter_candidates(
                emitter,
                geometry_skeleton_cache=cache,
                perf_stats=perf_stats,
            )

        self.assertEqual(len(cache), 3)
        self.assertEqual(perf_stats.geometry_skeleton_cache_misses, 3)
        self.assertEqual(perf_stats.geometry_skeleton_cache_hits, 0)

    def test_geometry_skeleton_cache_does_not_merge_distinct_angles(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        shifted = replace(
            emitter,
            emitter_id=f"{emitter.emitter_id}:shifted",
            target_angle_degrees=emitter.target_angle_degrees + 0.01,
        )
        cache: dict = {}
        perf_stats = note_stereo._PerformanceStats()

        layout._emitter_candidates(
            emitter,
            geometry_skeleton_cache=cache,
            perf_stats=perf_stats,
        )
        layout._emitter_candidates(
            shifted,
            geometry_skeleton_cache=cache,
            perf_stats=perf_stats,
        )

        self.assertEqual(len(cache), 2)
        self.assertEqual(perf_stats.geometry_skeleton_cache_misses, 2)
        self.assertEqual(perf_stats.geometry_skeleton_cache_hits, 0)

    def test_preview_reports_geometry_skeleton_cache_diagnostics(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_three_note_song()).note_based_preview
        assert preview is not None

        self.assertGreaterEqual(preview.geometry_skeleton_cache_hits, 0)
        self.assertGreaterEqual(preview.geometry_skeleton_cache_misses, 0)
        self.assertGreater(preview.geometry_skeleton_unique_key_count, 0)
        self.assertGreater(preview.geometry_skeleton_candidates_generated, 0)
        self.assertGreaterEqual(preview.geometry_skeleton_candidates_reused, 0)
        self.assertGreaterEqual(preview.geometry_skeleton_cache_hit_rate, 0)
        self.assertLessEqual(preview.geometry_skeleton_cache_hit_rate, 1)
        self.assertIsInstance(preview.geometry_skeleton_top_key_counts, tuple)

    def test_pan_normalization_does_not_mutate_raw_song_pans(self) -> None:
        song = _pan_range_song((50, 150))
        raw_pans = [
            note.final_panning
            for track in song.tracks
            for note in track.notes
        ]
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )

        emitters = layout._ideal_emitters(song)

        self.assertEqual(
            [
                note.final_panning
                for track in song.tracks
                for note in track.notes
            ],
            raw_pans,
        )
        self.assertEqual([emitter.final_panning for emitter in emitters], raw_pans)

    def test_pan_normalization_stretches_meaningful_narrow_range(self) -> None:
        scale = note_stereo._pan_normalization_scale((50, 150))

        self.assertEqual(scale, 2.0)
        self.assertEqual(note_stereo._normalize_panning(50, scale), 0.0)
        self.assertEqual(note_stereo._normalize_panning(150, scale), 200.0)

    def test_pan_normalization_preserves_asymmetric_proportion(self) -> None:
        scale = note_stereo._pan_normalization_scale((70, 150))

        self.assertEqual(scale, 2.0)
        self.assertEqual(note_stereo._normalize_panning(70, scale), 40.0)
        self.assertEqual(note_stereo._normalize_panning(150, scale), 200.0)

    def test_pan_normalization_ignores_tiny_center_range(self) -> None:
        scale = note_stereo._pan_normalization_scale((95, 105))

        self.assertEqual(scale, 1.0)
        self.assertEqual(note_stereo._normalize_panning(95, scale), 95.0)
        self.assertEqual(note_stereo._normalize_panning(105, scale), 105.0)

    def test_pan_normalization_scale_is_capped(self) -> None:
        scale = note_stereo._pan_normalization_scale((80, 120))

        self.assertEqual(scale, note_stereo.PAN_NORMALIZE_MAX_SCALE)
        self.assertEqual(note_stereo._normalize_panning(80, scale), 40.0)
        self.assertEqual(note_stereo._normalize_panning(120, scale), 160.0)

    def test_target_angle_uses_normalized_pan_when_enabled(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitters = layout._ideal_emitters(_pan_range_song((50, 150)))

        self.assertEqual(emitters[0].final_panning, 50)
        self.assertEqual(emitters[0].target_angle_degrees, -90.0)
        self.assertEqual(emitters[1].target_angle_degrees, 90.0)

    def test_pan_normalization_does_not_change_candidate_generation_count(self) -> None:
        song = _pan_range_song((50, 150))
        normalized_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        raw_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(enable_pan_normalization=False),
        )

        normalized_counts = [
            len(normalized_layout._emitter_candidates(emitter))
            for emitter in normalized_layout._ideal_emitters(song)
        ]
        raw_counts = [
            len(raw_layout._emitter_candidates(emitter))
            for emitter in raw_layout._ideal_emitters(song)
        ]

        self.assertEqual(normalized_counts, raw_counts)

    def test_dynamic_yz_penalties_match_zero_45_90_degree_endpoints(self) -> None:
        original_y = note_stereo.PAN_ZONE_ORIGINAL_Y_MOVE_PENALTY
        original_z = original_y + StereoLayoutConfig().lateral_step_penalty

        self.assertEqual(
            note_stereo._dynamic_movement_penalties(
                0,
                original_y_penalty=original_y,
                original_z_penalty=original_z,
            ),
            (original_z, original_y),
        )
        self.assertEqual(
            note_stereo._dynamic_movement_penalties(
                45,
                original_y_penalty=original_y,
                original_z_penalty=original_z,
            ),
            ((original_y + original_z) / 2, (original_y + original_z) / 2),
        )
        edge_y, edge_z = note_stereo._dynamic_movement_penalties(
            90,
            original_y_penalty=original_y,
            original_z_penalty=original_z,
        )
        self.assertAlmostEqual(edge_y, original_y)
        self.assertAlmostEqual(edge_z, original_z)

    def test_dynamic_yz_penalties_use_abs_target_angle(self) -> None:
        original_y = 0.3
        original_z = 0.8

        self.assertEqual(
            note_stereo._dynamic_movement_penalties(
                -45,
                original_y_penalty=original_y,
                original_z_penalty=original_z,
            ),
            note_stereo._dynamic_movement_penalties(
                45,
                original_y_penalty=original_y,
                original_z_penalty=original_z,
            ),
        )

    def test_dynamic_yz_penalty_uses_note_target_angle_not_candidate_angle(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        center_angle_candidates: list = []
        edge_angle_candidates: list = []

        layout._add_candidates_for_position(
            center_angle_candidates,
            set(),
            emitter,
            offset_y=emitter.ideal_offset_y + 1,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=1,
            lateral_movement=0,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            y_height_penalty=0,
            chosen_angle_degrees=0,
        )
        layout._add_candidates_for_position(
            edge_angle_candidates,
            set(),
            emitter,
            offset_y=emitter.ideal_offset_y + 1,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=1,
            lateral_movement=0,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            y_height_penalty=0,
            chosen_angle_degrees=90,
        )

        self.assertEqual(
            center_angle_candidates[0].cost,
            edge_angle_candidates[0].cost,
        )

    def test_pan_zone_candidate_sort_uses_cost_before_lateral_movement(self) -> None:
        zero_lateral_higher_cost = _candidate(
            cost=2.0,
            lateral_movement=0,
        )
        lateral_lower_cost = _candidate(
            cost=1.0,
            lateral_movement=3,
        )

        sorted_candidates = note_stereo._sort_pan_zone_candidates(
            [zero_lateral_higher_cost, lateral_lower_cost]
        )

        self.assertIs(sorted_candidates[0], lateral_lower_cost)

    def test_near_center_dynamic_cost_is_not_overridden_by_lateral_movement(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        candidates: list = []
        seen: set = set()

        layout._add_candidates_for_position(
            candidates,
            seen,
            emitter,
            offset_y=emitter.ideal_offset_y + 1,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=1,
            lateral_movement=0,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            y_height_penalty=0,
            chosen_angle_degrees=0,
        )
        layout._add_candidates_for_position(
            candidates,
            seen,
            emitter,
            offset_y=emitter.ideal_offset_y,
            offset_lateral=emitter.ideal_offset_lateral + 1,
            level=1,
            y_movement=0,
            lateral_movement=1,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            y_height_penalty=0,
            chosen_angle_degrees=0,
        )

        sorted_candidates = note_stereo._sort_pan_zone_candidates(candidates)

        self.assertGreater(candidates[0].cost, candidates[1].cost)
        self.assertEqual(sorted_candidates[0].lateral_movement, 1)

    def test_no_spatial_hint_has_no_pan_hint_score(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]

        self.assertEqual(layout._candidate_pan_hint_score(emitter, "L_INNER"), 0.0)

    def test_zero_weight_spatial_hint_keeps_candidate_costs_unchanged(self) -> None:
        base_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(allow_adjacent_pan_zone_fallback=True),
        )
        hint_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(allow_adjacent_pan_zone_fallback=True),
            spatial_hint_index=_StaticSpatialHintIndex(
                _spatial_segment_hint("center_stable", layout_hint_weight=0.0)
            ),
        )
        emitter = base_layout._ideal_emitters(_single_note_song())[0]

        self.assertEqual(
            base_layout._emitter_candidates(emitter),
            hint_layout._emitter_candidates(emitter),
        )

    def test_center_stable_pan_hint_prefers_center_zone(self) -> None:
        emitter = _emitter_for_panning(100)
        hint = _spatial_segment_hint("center_stable")

        center = _pan_hint_score(hint, emitter, "CENTER")
        left_inner = _pan_hint_score(hint, emitter, "L_INNER")
        right_inner = _pan_hint_score(hint, emitter, "R_INNER")

        self.assertEqual(center, 0.0)
        self.assertGreater(left_inner, center)
        self.assertGreater(right_inner, center)

    def test_left_stable_accepts_inner_and_mid_zones(self) -> None:
        emitter = _emitter_for_panning(40)
        hint = _spatial_segment_hint("left_stable")

        self.assertAlmostEqual(_pan_hint_score(hint, emitter, "L_INNER"), 0.0)
        self.assertAlmostEqual(_pan_hint_score(hint, emitter, "L_MID"), 0.0)
        self.assertLess(
            _pan_hint_score(hint, emitter, "L_EDGE"),
            _pan_hint_score(hint, emitter, "R_MID"),
        )

    def test_far_left_stable_uses_angular_distance_not_zone_index(self) -> None:
        emitter = _emitter_for_panning(0)
        hint = _spatial_segment_hint("far_left_stable")

        l_edge = _pan_hint_score(hint, emitter, "L_EDGE")
        l_mid = _pan_hint_score(hint, emitter, "L_MID")
        center = _pan_hint_score(hint, emitter, "CENTER")
        r_mid = _pan_hint_score(hint, emitter, "R_MID")

        self.assertEqual(l_edge, 0.0)
        self.assertGreater(l_mid, l_edge)
        self.assertLess(l_mid, center)
        self.assertLess(l_mid, r_mid)

    def test_right_side_pan_hint_is_symmetric(self) -> None:
        emitter = _emitter_for_panning(200)
        hint = _spatial_segment_hint("far_right_stable")

        self.assertEqual(_pan_hint_score(hint, emitter, "R_EDGE"), 0.0)
        self.assertLess(
            _pan_hint_score(hint, emitter, "R_MID"),
            _pan_hint_score(hint, emitter, "CENTER"),
        )
        self.assertLess(
            _pan_hint_score(hint, emitter, "R_MID"),
            _pan_hint_score(hint, emitter, "L_MID"),
        )

    def test_layout_hint_weight_scales_pan_hint_score(self) -> None:
        emitter = _emitter_for_panning(100)
        high = _spatial_segment_hint("center_stable", layout_hint_weight=1.0)
        low = _spatial_segment_hint("center_stable", layout_hint_weight=0.25)

        self.assertGreater(
            _pan_hint_score(high, emitter, "R_EDGE"),
            _pan_hint_score(low, emitter, "R_EDGE"),
        )

    def test_wide_or_split_uses_reduced_pan_mode_factor(self) -> None:
        emitter = _emitter_for_panning(40)
        stable = _spatial_segment_hint("left_stable")
        wide = _spatial_segment_hint("wide_or_split")

        self.assertAlmostEqual(
            _pan_hint_score(wide, emitter, "R_MID"),
            _pan_hint_score(stable, emitter, "R_MID") * 0.5,
        )

    def test_inactive_and_unknown_pan_hints_do_not_score(self) -> None:
        emitter = _emitter_for_panning(100)

        self.assertEqual(
            _pan_hint_score(_spatial_segment_hint("inactive"), emitter, "R_EDGE"),
            0.0,
        )
        self.assertEqual(
            _pan_hint_score(_spatial_segment_hint("unknown"), emitter, "R_EDGE"),
            0.0,
        )

    def test_insufficient_data_caps_pan_hint_score(self) -> None:
        emitter = _emitter_for_panning(100)
        flat = _spatial_segment_hint("center_stable", volume_contour_mode="flat")
        insufficient = _spatial_segment_hint(
            "center_stable",
            volume_contour_mode="insufficient_data",
        )

        self.assertLess(
            _pan_hint_score(insufficient, emitter, "R_EDGE"),
            _pan_hint_score(flat, emitter, "R_EDGE"),
        )

    def test_spatial_pan_hint_does_not_change_candidate_generation_count(self) -> None:
        config = StereoLayoutConfig(allow_adjacent_pan_zone_fallback=True)
        base_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=config,
        )
        hint_layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=config,
            spatial_hint_index=_StaticSpatialHintIndex(
                _spatial_segment_hint("center_stable")
            ),
        )
        emitter = base_layout._ideal_emitters(_single_note_song())[0]

        self.assertEqual(
            len(base_layout._emitter_candidates(emitter)),
            len(hint_layout._emitter_candidates(emitter)),
        )

    def test_assignments_use_each_rail_slot_once_per_tick(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_three_note_song()).note_based_preview
        assert preview is not None

        used_slots = set()
        for assignment in preview.assignments:
            key = (
                assignment.rail.rail_id,
                assignment.slot.tick,
                assignment.slot.slot_index,
            )
            self.assertNotIn(key, used_slots)
            used_slots.add(key)

    def test_center_target_makes_z_movement_cheaper_than_y_movement(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(enable_pan_zone_layout=False),
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        candidates = layout._emitter_candidates(emitter)

        y_candidate = next(
            candidate
            for candidate in candidates
            if candidate.y_movement == 1 and candidate.lateral_movement == 0
        )
        z_candidate = next(
            candidate
            for candidate in candidates
            if candidate.y_movement == 0 and candidate.lateral_movement == 1
        )

        self.assertLess(z_candidate.cost, y_candidate.cost)

    def test_pan_zone_layout_keeps_candidates_inside_zone_by_default(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        candidates = layout._emitter_candidates(emitter)

        self.assertEqual(emitter.pan_zone, "CENTER")
        self.assertTrue(candidates)
        self.assertLessEqual(len(candidates), 64)
        self.assertTrue(
            all(candidate.pan_zone == "CENTER" for candidate in candidates)
        )

    def test_pan_zone_preview_reports_distribution_and_radius_error(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_pan_zone_song()).note_based_preview
        assert preview is not None

        distribution = {
            stat.zone: stat.emitter_count
            for stat in preview.pan_zone_distribution
        }
        self.assertEqual(distribution["L_EDGE"], 1)
        self.assertEqual(distribution["CENTER"], 1)
        self.assertEqual(distribution["R_EDGE"], 1)
        self.assertEqual(preview.adjacent_zone_fallback_count, 0)
        self.assertGreaterEqual(preview.average_radius_error, 0)
        self.assertGreater(preview.total_candidates_generated, 0)
        self.assertGreater(preview.average_candidates_per_emitter, 0)
        self.assertGreater(preview.max_candidates_for_one_emitter, 0)
        self.assertTrue(preview.stage_timings)

    def test_pan_zone_candidates_use_angle_ranges(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitters = {
            emitter.pan_zone: emitter
            for emitter in layout._ideal_emitters(_pan_zone_song())
        }

        left_candidates = layout._emitter_candidates(emitters["L_EDGE"])
        center_candidates = layout._emitter_candidates(emitters["CENTER"])
        right_candidates = layout._emitter_candidates(emitters["R_EDGE"])

        self.assertTrue(
            all(candidate.chosen_angle_degrees < -40 for candidate in left_candidates)
        )
        self.assertTrue(
            all(-10 <= candidate.chosen_angle_degrees <= 10 for candidate in center_candidates)
        )
        self.assertTrue(
            all(candidate.chosen_angle_degrees > 40 for candidate in right_candidates)
        )
        self.assertLess(emitters["L_EDGE"].allowed_angle_range[1], -40)
        self.assertEqual(emitters["CENTER"].allowed_angle_range, (-10, 10))
        self.assertGreater(emitters["R_EDGE"].allowed_angle_range[0], 40)

    def test_adjacent_pan_zone_fallback_can_be_enabled(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                allow_adjacent_pan_zone_fallback=True,
                max_candidate_y_layers=0,
                max_candidates_per_emitter=256,
                max_candidate_lateral_positions=64,
            ),
        )
        emitter = layout._ideal_emitters(_single_center_quiet_note_song())[0]
        zones = {
            candidate.pan_zone
            for candidate in layout._emitter_candidates(emitter)
        }

        self.assertIn("CENTER", zones)
        self.assertTrue({"L_INNER", "R_INNER"} & zones)

    def test_side_first_rail_center_upgrade_allows_center_assignment(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        context = _AssignmentContext()
        side_candidate = _rail_slot_candidate(layout, slot_index=-1)
        center_candidate = _rail_slot_candidate(layout, slot_index=0)

        side_assignment = _try_assign_candidate(
            layout,
            emitter,
            side_candidate,
            context,
        )
        assert side_assignment is not None
        rail_id = side_assignment.rail.rail_id

        self.assertIs(context.active_rail_cells[rail_id], False)

        center_assignment = _try_assign_candidate(
            layout,
            emitter,
            center_candidate,
            context,
        )

        self.assertIsNotNone(center_assignment)
        self.assertIs(context.active_rail_cells[rail_id], True)
        rail_center = center_candidate.position
        self.assertNotIn("track_block", context.occupancy.occupied[rail_center])
        self.assertIn("note_block", context.occupancy.occupied[rail_center])
        self.assertNotIn("track_block", context.occupancy.occupied[below(rail_center)])
        self.assertIn("instrument_block", context.occupancy.occupied[below(rail_center)])
        self.assertIn("reserved_air", context.occupancy.reserved_air[above(rail_center)])

    def test_center_first_same_rail_side_assignment_still_succeeds(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        context = _AssignmentContext()
        center_candidate = _rail_slot_candidate(layout, slot_index=0)
        side_candidate = _rail_slot_candidate(layout, slot_index=1)

        center_assignment = _try_assign_candidate(
            layout,
            emitter,
            center_candidate,
            context,
        )
        assert center_assignment is not None

        side_assignment = _try_assign_candidate(
            layout,
            emitter,
            side_candidate,
            context,
        )

        self.assertIsNotNone(side_assignment)
        self.assertIs(context.active_rail_cells[center_assignment.rail.rail_id], True)

    def test_side_first_center_upgrade_fails_when_reserved_air_is_blocked(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        context = _AssignmentContext()
        side_candidate = _rail_slot_candidate(layout, slot_index=-1)
        center_candidate = _rail_slot_candidate(layout, slot_index=0)
        side_assignment = _try_assign_candidate(
            layout,
            emitter,
            side_candidate,
            context,
        )
        assert side_assignment is not None
        rail_center = center_candidate.position
        context.occupancy.occupied.setdefault(above(rail_center), []).append(
            "track_block"
        )

        center_assignment = _try_assign_candidate(
            layout,
            emitter,
            center_candidate,
            context,
        )

        self.assertIsNone(center_assignment)
        self.assertIs(context.active_rail_cells[side_assignment.rail.rail_id], False)
        self.assertIn("track_block", context.occupancy.occupied[rail_center])
        self.assertNotIn("note_block", context.occupancy.occupied[rail_center])

    def test_side_first_center_upgrade_fails_with_unrelated_below_occupancy(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        context = _AssignmentContext()
        side_candidate = _rail_slot_candidate(layout, slot_index=-1)
        center_candidate = _rail_slot_candidate(layout, slot_index=0)
        side_assignment = _try_assign_candidate(
            layout,
            emitter,
            side_candidate,
            context,
        )
        assert side_assignment is not None
        rail_center = center_candidate.position
        context.occupancy.occupied[below(rail_center)].append("note_block")

        center_assignment = _try_assign_candidate(
            layout,
            emitter,
            center_candidate,
            context,
        )

        self.assertIsNone(center_assignment)
        self.assertIs(context.active_rail_cells[side_assignment.rail.rail_id], False)
        self.assertIn("track_block", context.occupancy.occupied[below(rail_center)])
        self.assertIn("note_block", context.occupancy.occupied[below(rail_center)])
        self.assertNotIn("instrument_block", context.occupancy.occupied[below(rail_center)])

    def test_second_center_assignment_on_same_rail_is_rejected(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        context = _AssignmentContext()
        center_candidate = _rail_slot_candidate(layout, slot_index=0)
        first = _try_assign_candidate(layout, emitter, center_candidate, context)
        assert first is not None

        second = _try_assign_candidate(layout, emitter, center_candidate, context)

        self.assertIsNone(second)

    def test_track_block_note_block_collision_is_not_globally_allowed(self) -> None:
        position = BlockPosition(0, 128, 0)
        occupancy = _FootprintOccupancy(
            occupied={position: ["track_block"]},
            reserved_air={},
        )
        footprint = _Footprint(occupied=((position, "note_block"),))

        self.assertTrue(_footprint_collides(occupancy, footprint))

    def test_track_block_instrument_block_collision_is_not_globally_allowed(self) -> None:
        position = BlockPosition(0, 127, 0)
        occupancy = _FootprintOccupancy(
            occupied={position: ["track_block"]},
            reserved_air={},
        )
        footprint = _Footprint(occupied=((position, "instrument_block"),))

        self.assertTrue(_footprint_collides(occupancy, footprint))

    def test_overlapping_lateral_range_close_rails_are_rejected(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                min_rail_center_y_gap=4,
                activation_slot_radius=1,
            ),
        )
        existing = ActivationRail("rail_6_-15", 6, -15, 1)
        new = ActivationRail("rail_7_-16", 7, -16, 1)
        existing_footprint = layout._projected_rail_footprint(existing, 0)
        stats = _RailValidationStats()

        valid = layout._validate_new_rail(
            new,
            layout._projected_rail_footprint(new, 0),
            {existing.rail_id: existing},
            {existing.rail_id: existing_footprint},
            _rail_index(layout, existing),
            stats,
            note_stereo._PerformanceStats(),
            "test",
        )

        self.assertFalse(valid)
        self.assertEqual(stats.rejected_by_same_plane_y_gap, 1)
        assert stats.issues is not None
        self.assertEqual(
            stats.issues[0].reason,
            "activation transverse range y gap too small",
        )
        self.assertEqual(stats.issues[0].rail_a_transverse_range, (-16, -14))
        self.assertEqual(stats.issues[0].rail_b_transverse_range, (-17, -15))
        self.assertTrue(stats.issues[0].activation_ranges_overlap)

    def test_non_overlapping_lateral_range_is_not_rejected_by_y_gap(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                min_rail_center_y_gap=4,
                activation_slot_radius=1,
            ),
        )
        existing = ActivationRail("rail_6_-15", 6, -15, 1)
        new = ActivationRail("rail_7_-20", 7, -20, 1)
        existing_footprint = layout._projected_rail_footprint(existing, 0)
        stats = _RailValidationStats()

        valid = layout._validate_new_rail(
            new,
            layout._projected_rail_footprint(new, 0),
            {existing.rail_id: existing},
            {existing.rail_id: existing_footprint},
            _rail_index(layout, existing),
            stats,
            note_stereo._PerformanceStats(),
            "test",
        )

        self.assertTrue(valid)
        self.assertEqual(stats.rejected_by_same_plane_y_gap, 0)

    def test_north_south_uses_transverse_x_range_for_y_gap(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="north",
            config=StereoLayoutConfig(
                min_rail_center_y_gap=4,
                activation_slot_radius=1,
            ),
        )
        existing = ActivationRail("rail_6_-15", 6, -15, 1)
        new = ActivationRail("rail_7_-16", 7, -16, 1)
        existing_footprint = layout._projected_rail_footprint(existing, 0)
        stats = _RailValidationStats()

        valid = layout._validate_new_rail(
            new,
            layout._projected_rail_footprint(new, 0),
            {existing.rail_id: existing},
            {existing.rail_id: existing_footprint},
            _rail_index(layout, existing),
            stats,
            note_stereo._PerformanceStats(),
            "test",
        )

        self.assertFalse(valid)
        self.assertEqual(stats.rejected_by_same_plane_y_gap, 1)
        assert stats.issues is not None
        self.assertEqual(stats.issues[0].direction, "north")
        self.assertEqual(stats.issues[0].rail_a_transverse_range, (-16, -14))
        self.assertEqual(stats.issues[0].rail_b_transverse_range, (-17, -15))
        self.assertTrue(stats.issues[0].activation_ranges_overlap)

    def test_full_rail_footprint_collision_rejects_candidate(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(min_rail_center_y_gap=0),
        )
        existing = ActivationRail("rail_30_32", 30, 32, 1)
        new = ActivationRail("rail_30_32_duplicate", 30, 32, 1)
        existing_footprint = layout._projected_rail_footprint(existing, 0)
        stats = _RailValidationStats()

        valid = layout._validate_new_rail(
            new,
            layout._projected_rail_footprint(new, 0),
            {existing.rail_id: existing},
            {existing.rail_id: existing_footprint},
            _rail_index(layout, existing),
            stats,
            note_stereo._PerformanceStats(),
            "test",
        )

        self.assertFalse(valid)
        self.assertEqual(stats.rejected_by_full_footprint_collision, 1)
        assert stats.issues is not None
        self.assertEqual(stats.issues[0].reason, "rail footprint collision")

    def test_note_based_rail_collisions_are_summarized(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        preview = layout.layout_song(_three_note_song()).note_based_preview
        assert preview is not None
        track_layouts = tuple(layout._rail_track_layouts(preview))
        first = track_layouts[0]
        second = track_layouts[0]
        collision = BlockCollision(
            position=BlockPosition(1, 158, 32),
            first_block_type="repeater",
            first_track_id=first.track_id,
            first_tick=0,
            second_block_type="track_block",
            second_track_id=second.track_id,
            second_tick=0,
            collision_type="occupied_occupied",
        )

        summaries = _summarize_block_collisions((collision,), track_layouts)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].collision_type, "occupied_occupied")

    def test_center_emitters_finish_without_collision(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                enable_depth_mirror_candidates=False,
                max_candidate_y_layers=0,
                max_note_level_center_splits=10,
            ),
        ).layout_song(_three_note_song()).note_based_preview
        assert preview is not None

        self.assertEqual(preview.failed_assignment_count, 0)
        self.assertEqual(preview.center_split_failed_count, 0)
        self.assertEqual(preview.rail_collision_count_after, 0)
        self.assertGreaterEqual(len(preview.assignments), 3)

    def test_depth_mirror_candidate_is_still_generated(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                allow_adjacent_pan_zone_fallback=True,
                max_candidate_y_layers=0,
            ),
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        candidates = layout._emitter_candidates(emitter)

        mirror = next(
            candidate
            for candidate in candidates
            if candidate.offset_y == -emitter.ideal_offset_y
            and candidate.offset_lateral == emitter.ideal_offset_lateral
            and candidate.slot_index == 0
        )
        lateral = next(
            candidate
            for candidate in candidates
            if candidate.offset_y == emitter.ideal_offset_y
            and candidate.offset_lateral != emitter.ideal_offset_lateral
        )

        self.assertTrue(mirror.depth_mirrored)
        self.assertFalse(lateral.depth_mirrored)
        self.assertIn(mirror, candidates)
        self.assertIn(lateral, candidates)

    def test_default_depth_mirror_penalty_is_zero(self) -> None:
        self.assertEqual(StereoLayoutConfig().depth_mirror_penalty, 0.0)

    def test_depth_mirrored_candidate_has_no_intrinsic_cost_penalty(self) -> None:
        layout = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        )
        emitter = layout._ideal_emitters(_single_note_song())[0]
        candidates: list = []

        layout._add_candidates_for_position(
            candidates,
            set(),
            emitter,
            offset_y=emitter.ideal_offset_y,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=0,
            lateral_movement=0,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            movement_distance=0,
            y_height_penalty=0,
            depth_mirrored=False,
            chosen_angle_degrees=0,
        )
        layout._add_candidates_for_position(
            candidates,
            set(),
            emitter,
            offset_y=emitter.ideal_offset_y,
            offset_lateral=emitter.ideal_offset_lateral,
            level=1,
            y_movement=0,
            lateral_movement=0,
            slots=(0,),
            pan_zone="CENTER",
            candidate_panning=100,
            radius_error=0,
            pan_error_inside_zone=0,
            movement_distance=0,
            y_height_penalty=0,
            depth_mirrored=True,
            chosen_angle_degrees=0,
        )

        self.assertFalse(candidates[0].depth_mirrored)
        self.assertTrue(candidates[1].depth_mirrored)
        self.assertEqual(candidates[0].cost, candidates[1].cost)

    def test_preview_reports_negative_depth_usage(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
        ).layout_song(_three_note_song()).note_based_preview
        assert preview is not None

        self.assertGreater(preview.negative_depth_rail_count, 0)
        self.assertGreater(preview.negative_depth_assignments, 0)
        self.assertGreater(preview.mirror_fallback_accepted_count, 0)
        self.assertEqual(preview.failed_assignment_count_by_pan_zone, ())

    def test_non_center_failed_emitters_do_not_use_center_split(self) -> None:
        preview = NoteBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                max_candidate_y_layers=0,
                max_candidates_per_emitter=1,
                max_note_level_center_splits=10,
            ),
        ).layout_song(_left_edge_same_tick_song()).note_based_preview
        assert preview is not None

        self.assertGreater(preview.failed_assignment_count_after_pass1, 0)
        self.assertEqual(preview.failed_assignment_count, 0)
        self.assertGreater(preview.retry_accepted_count, 0)
        self.assertEqual(preview.center_split_attempted_count, 0)

    def test_build_layout_strategy_uses_note_based_preview(self) -> None:
        strategy = build_layout_strategy(
            mode="note_based_stereo",
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            selected_track_id=None,
            stereo_config=StereoLayoutConfig(),
        )

        layout = strategy.layout_song(_single_note_song())

        self.assertEqual(layout.mode, "note_based_stereo_preview")
        self.assertIsNotNone(layout.note_based_preview)

    def test_note_based_cell_geometry_matches_track_based_relative_geometry(self) -> None:
        origin = BlockPosition(0, 128, 0)
        track_based = TrackBasedStereoLayout(
            origin=origin,
            track_direction="east",
            config=StereoLayoutConfig(center_split_policy="none"),
        ).layout_song(_two_tick_song())
        note_based = NoteBasedStereoLayout(
            origin=origin,
            track_direction="east",
        ).layout_song(_two_tick_song())

        track_cell = track_based.cells[0]
        note_cell = note_based.cells[0]

        self.assertEqual(
            _delta(track_cell.note_block_position, track_cell.repeater_position),
            _delta(note_cell.note_block_position, note_cell.repeater_position),
        )
        self.assertEqual(
            _delta(track_cell.repeater_position, track_based.cells[1].repeater_position),
            _delta(note_cell.repeater_position, note_based.cells[1].repeater_position),
        )
        self.assertEqual(
            _delta(track_cell.repeater_position, track_cell.track_block_position),
            _delta(note_cell.repeater_position, note_cell.track_block_position),
        )


def _single_note_song() -> Song:
    return Song(
        name="Single note",
        author="tests",
        length=1,
        tracks=(_track(0, (0,)),),
    )


def _single_center_quiet_note_song() -> Song:
    return Song(
        name="Single quiet center note",
        author="tests",
        length=1,
        tracks=(
            Track(
                id=0,
                name="Track 0",
                source_layer=0,
                notes=(
                    NoteEvent(
                        tick=0,
                        layer=0,
                        instrument=0,
                        key=45,
                        final_volume=0,
                        final_panning=100,
                    ),
                ),
            ),
        ),
    )


def _three_note_song() -> Song:
    return Song(
        name="Three notes",
        author="tests",
        length=1,
        tracks=(
            _track(0, (0,)),
            _track(1, (0,)),
            _track(2, (0,)),
        ),
    )


def _two_tick_song() -> Song:
    return Song(
        name="Two tick geometry",
        author="tests",
        length=2,
        tracks=(_track(0, (0, 1)),),
    )


def _pan_zone_song() -> Song:
    return Song(
        name="Pan zones",
        author="tests",
        length=1,
        tracks=(
            _track_with_panning(0, 0),
            _track_with_panning(1, 100),
            _track_with_panning(2, 200),
        ),
    )


def _pan_range_song(panning_values: tuple[float, ...]) -> Song:
    return Song(
        name="Pan range",
        author="tests",
        length=len(panning_values),
        tracks=tuple(
            _track_with_panning(track_id, panning)
            for track_id, panning in enumerate(panning_values)
        ),
    )


def _left_edge_same_tick_song() -> Song:
    return Song(
        name="Left edge same tick",
        author="tests",
        length=1,
        tracks=(
            _track_with_panning(0, 0),
            _track_with_panning(1, 0),
            _track_with_panning(2, 0),
        ),
    )


def _track(track_id: int, ticks: tuple[int, ...]) -> Track:
    return Track(
        id=track_id,
        name=f"Track {track_id}",
        source_layer=track_id,
        notes=tuple(
            NoteEvent(
                tick=tick,
                layer=track_id,
                instrument=0,
                key=45,
                final_volume=100,
                final_panning=100,
            )
            for tick in ticks
        ),
    )


def _track_with_panning(track_id: int, panning: float) -> Track:
    return Track(
        id=track_id,
        name=f"Track {track_id}",
        source_layer=track_id,
        notes=(
            NoteEvent(
                tick=0,
                layer=track_id,
                instrument=0,
                key=45,
                final_volume=100,
                final_panning=panning,
            ),
        ),
    )


def _rail_index(
    layout: NoteBasedStereoLayout,
    rail: ActivationRail,
) -> dict[int, set[str]]:
    return {
        transverse: {rail.rail_id}
        for transverse in layout._activation_transverse_keys(rail)
    }


class _StaticSpatialHintIndex:
    def __init__(self, segment: LayoutSpatialSegmentHint) -> None:
        self.segment = segment

    def get_segment(
        self,
        layer_id: int,
        tick: int,
    ) -> LayoutSpatialSegmentHint | None:
        if (
            layer_id == self.segment.layer_id
            and self.segment.start_tick <= tick < self.segment.end_tick
        ):
            return self.segment
        return None


class _AssignmentContext:
    def __init__(self) -> None:
        self.registry = RailRegistry(rails={})
        self.candidate_values: dict[tuple[int, int], int] = {}
        self.occupancy = _FootprintOccupancy(occupied={}, reserved_air={})
        self.used_slots: set[tuple[str, int]] = set()
        self.active_rail_cells: dict[str, bool] = {}
        self.active_rails = {}
        self.rail_footprints = {}
        self.rails_by_transverse = {}
        self.rail_stats = _RailValidationStats()
        self.perf_stats = note_stereo._PerformanceStats()


def _try_assign_candidate(
    layout: NoteBasedStereoLayout,
    emitter,
    candidate: EmitterCandidate,
    context: _AssignmentContext,
):
    return layout._try_assign_emitter(
        emitter,
        (candidate,),
        emitter.tick,
        context.registry,
        context.candidate_values,
        context.occupancy,
        context.used_slots,
        context.active_rail_cells,
        context.active_rails,
        context.rail_footprints,
        context.rails_by_transverse,
        context.rail_stats,
        context.perf_stats,
        "test",
    )


def _rail_slot_candidate(
    layout: NoteBasedStereoLayout,
    *,
    slot_index: int,
    tick: int = 0,
    rail_offset_y: int = 12,
    rail_offset_lateral: int = 0,
) -> EmitterCandidate:
    offset_lateral = rail_offset_lateral + slot_index
    return EmitterCandidate(
        emitter_id=f"candidate:{slot_index}",
        position=layout._position_from_offsets(
            tick,
            rail_offset_y,
            offset_lateral,
        ),
        offset_y=rail_offset_y,
        offset_lateral=offset_lateral,
        rail_offset_y=rail_offset_y,
        rail_offset_lateral=rail_offset_lateral,
        slot_index=slot_index,
        level=0,
        cost=0,
        y_movement=0,
        lateral_movement=slot_index,
        pan_zone="CENTER",
    )


def _spatial_segment_hint(
    pan_mode: str,
    *,
    layout_hint_weight: float = 1.0,
    volume_contour_mode: str = "flat",
) -> LayoutSpatialSegmentHint:
    return LayoutSpatialSegmentHint(
        layer_id=0,
        start_tick=0,
        end_tick=1024,
        duration_ticks=1024,
        window_count=1,
        pan_mode=pan_mode,
        pan_contour_mode="flat",
        volume_mode="mid_stable",
        volume_contour_mode=volume_contour_mode,
        volume_contour={},
        radius_layer_hint={"type": "none"},
        lateral_substream_hint={"type": "none"},
        layout_intent={},
        continuity_priority="medium",
        segment_note_count=8,
        layout_hint_weight=layout_hint_weight,
        hint_strength="strong" if layout_hint_weight >= 0.70 else "medium",
    )


def _emitter_for_panning(panning: float):
    layout = NoteBasedStereoLayout(
        origin=BlockPosition(0, 128, 0),
        track_direction="east",
    )
    return layout._ideal_emitters(
        Song(
            name="Emitter",
            author="tests",
            length=1,
            tracks=(_track_with_panning(0, panning),),
        )
    )[0]


def _pan_hint_score(
    hint: LayoutSpatialSegmentHint,
    emitter,
    candidate_pan_zone: str,
) -> float:
    return note_stereo._segment_pan_hint_score(
        hint,
        emitter,
        candidate_pan_zone,
        max_stereo_angle_degrees=90.0,
    )


def _candidate(
    *,
    cost: float,
    lateral_movement: int,
) -> EmitterCandidate:
    return EmitterCandidate(
        emitter_id="candidate",
        position=BlockPosition(0, 0, 0),
        offset_y=0,
        offset_lateral=lateral_movement,
        rail_offset_y=0,
        rail_offset_lateral=lateral_movement,
        slot_index=0,
        level=0,
        cost=cost,
        y_movement=0,
        lateral_movement=lateral_movement,
        pan_zone="CENTER",
    )


def _delta(first: BlockPosition, second: BlockPosition) -> tuple[int, int, int]:
    return (
        second.x - first.x,
        second.y - first.y,
        second.z - first.z,
    )


if __name__ == "__main__":
    unittest.main()
