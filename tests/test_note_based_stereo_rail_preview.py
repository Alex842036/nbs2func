import unittest

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
    analyze_layout_spatial,
    build_layout_spatial_hint_index,
)
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

    def test_y_movement_cost_is_lower_than_z_movement_cost(self) -> None:
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

        self.assertLess(y_candidate.cost, z_candidate.cost)

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

    def test_depth_mirror_candidate_is_preferred_before_lateral_movement(self) -> None:
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
        self.assertLess(mirror.cost, lateral.cost)
        self.assertLess(candidates.index(mirror), candidates.index(lateral))

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


def _delta(first: BlockPosition, second: BlockPosition) -> tuple[int, int, int]:
    return (
        second.x - first.x,
        second.y - first.y,
        second.z - first.z,
    )


if __name__ == "__main__":
    unittest.main()
