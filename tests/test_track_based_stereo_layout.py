import unittest

from nbs2func.layout import (
    BlockPosition,
    StereoLayoutConfig,
    TrackBasedStereoLayout,
)
from nbs2func.core.models import NoteEvent, Song, Track


class TrackBasedStereoLayoutTest(unittest.TestCase):
    def test_left_center_right_do_not_collapse_to_same_position(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(max_stereo_angle_degrees=90),
        ).layout_song(_left_center_right_song())

        positions = {
            note.source_track_id: note.note_block_position
            for note in layout.notes
        }

        self.assertNotEqual(positions[0], positions[1])
        self.assertNotEqual(positions[1], positions[2])
        self.assertNotEqual(positions[0], positions[2])
        self.assertLess(positions[0].z, positions[1].z)
        self.assertGreater(positions[2].z, positions[1].z)

    def test_right_stereo_uses_origin_y_with_default_angle(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(),
        ).layout_song(_left_center_right_song())

        positions = {
            note.source_track_id: note.note_block_position
            for note in layout.notes
        }

        self.assertEqual(positions[2].y, 128)

    def test_angle_above_90_is_clamped(self) -> None:
        with self.assertWarns(UserWarning):
            layout = TrackBasedStereoLayout(
                origin=BlockPosition(0, 128, 0),
                track_direction="east",
                config=StereoLayoutConfig(max_stereo_angle_degrees=180),
            ).layout_song(_left_center_right_song())

        positions = {
            note.source_track_id: note.note_block_position
            for note in layout.notes
        }

        self.assertLess(positions[0].z, positions[1].z)
        self.assertGreater(positions[2].z, positions[1].z)

    def test_repeated_collisions_are_grouped_by_track_pair(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                center_split_policy="none",
                enable_collision_resolver=False,
            ),
        ).layout_song(_colliding_song())

        self.assertGreater(len(layout.collisions), 1)
        self.assertEqual(len(layout.collision_summaries), 1)

        summary = layout.collision_summaries[0]
        self.assertEqual(summary.first_track.track_id, "0")
        self.assertEqual(summary.second_track.track_id, "1")
        self.assertEqual(summary.collision_type, "occupied_occupied")
        self.assertGreaterEqual(summary.estimated_cell_count, 2)
        self.assertLessEqual(len(summary.examples), 3)

    def test_collision_resolver_uses_depth_mirror_and_keeps_radius(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(center_split_policy="none"),
        ).layout_song(_colliding_song())

        self.assertEqual(layout.collisions, ())
        self.assertEqual(len(layout.track_layouts), 2)

        first, second = layout.track_layouts
        self.assertEqual(first.fallback, "preferred")
        self.assertEqual(second.fallback, "depth_mirror")
        self.assertEqual(second.radius, second.original_radius)
        self.assertEqual(second.offset_y, -second.original_offset_y)
        self.assertEqual(second.offset_lateral, second.original_offset_lateral)

    def test_radius_relax_changes_radius_only_when_enabled(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                center_split_policy="none",
                enable_depth_mirror_fallback=False,
                enable_radius_relax_fallback=True,
                max_angle_deviation_degrees=0,
            ),
        ).layout_song(_colliding_song())

        self.assertEqual(layout.collisions, ())
        second = layout.track_layouts[1]
        self.assertEqual(second.fallback, "radius_relax")
        self.assertNotEqual(second.radius, second.original_radius)

    def test_collision_resolver_uses_reserved_air_footprint(self) -> None:
        unresolved = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                center_split_policy="none",
                enable_collision_resolver=False,
            ),
        ).layout_song(_reserved_air_collision_song())

        self.assertTrue(
            any(
                collision.collision_type == "occupied_reserved_air"
                for collision in unresolved.collisions
            )
        )

        resolved = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(center_split_policy="none"),
        ).layout_song(_reserved_air_collision_song())

        self.assertEqual(resolved.collisions, ())
        self.assertEqual(resolved.track_layouts[1].fallback, "depth_mirror")

    def test_basic_linear_layout_is_unchanged_by_stereo_resolver(self) -> None:
        from nbs2func.layout import BasicLinearLayout

        layout = BasicLinearLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            selected_track_id=0,
        ).layout_song(_colliding_song())

        positions = [note.note_block_position for note in layout.notes]
        self.assertEqual(positions[0], BlockPosition(-1, 128, 0))
        self.assertEqual(positions[1], BlockPosition(1, 128, 0))

    def test_auto_center_split_splits_later_colliding_center_track(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(),
        ).layout_song(_colliding_song())

        split_tracks = {
            info.track_id: info
            for info in layout.track_layouts
            if info.virtual_role is not None
        }

        self.assertEqual(set(split_tracks), {"1:L", "1:R"})
        self.assertEqual(split_tracks["1:L"].split_reason, "auto_collision")
        self.assertEqual(
            split_tracks["1:L"].split_mode,
            "duplicate_half_volume",
        )
        left_event = next(
            event
            for event in layout.center_split_events
            if event.clone_track_id == "1:L"
        )
        self.assertGreater(left_event.after_radius, left_event.before_radius)
        self.assertEqual(len(layout.center_split_events), 2)

    def test_manual_center_split_only_splits_overridden_center_track(self) -> None:
        layout = TrackBasedStereoLayout(
            origin=BlockPosition(0, 128, 0),
            track_direction="east",
            config=StereoLayoutConfig(
                center_split_policy="manual",
                center_split_overrides={0: "split"},
                center_split_mode="duplicate_half_volume",
            ),
        ).layout_song(_colliding_song())

        track_ids = {info.track_id for info in layout.track_layouts}
        left_clone = next(info for info in layout.track_layouts if info.track_id == "0:L")

        self.assertIn("0:L", track_ids)
        self.assertIn("0:R", track_ids)
        self.assertIn("1", track_ids)
        self.assertEqual(left_clone.split_reason, "manual")
        self.assertEqual(left_clone.split_mode, "duplicate_half_volume")
        left_event = next(
            event
            for event in layout.center_split_events
            if event.clone_track_id == "0:L"
        )
        self.assertGreater(left_event.after_radius, left_event.before_radius)

    def test_manual_split_override_for_non_center_track_warns_and_is_ignored(self) -> None:
        with self.assertWarns(UserWarning):
            layout = TrackBasedStereoLayout(
                origin=BlockPosition(0, 128, 0),
                track_direction="east",
                config=StereoLayoutConfig(
                    center_split_policy="manual",
                    center_split_overrides={2: "split"},
                ),
            ).layout_song(_left_center_right_song())

        track_ids = {info.track_id for info in layout.track_layouts}
        self.assertIn("2", track_ids)
        self.assertNotIn("2:L", track_ids)
        self.assertNotIn("2:R", track_ids)


def _left_center_right_song() -> Song:
    return Song(
        name="Stereo offset test",
        author="tests",
        length=1,
        tracks=(
            _track(0, 0),
            _track(1, 100),
            _track(2, 200),
        ),
    )


def _colliding_song() -> Song:
    return Song(
        name="Collision grouping test",
        author="tests",
        length=2,
        tracks=(
            _multi_note_track(0, 100),
            _multi_note_track(1, 100),
        ),
    )


def _reserved_air_collision_song() -> Song:
    return Song(
        name="Reserved air collision test",
        author="tests",
        length=1,
        tracks=(
            _track_with_volume(0, 100),
            _track_with_volume(1, 97.7272727273),
        ),
    )


def _track(track_id: int, panning: int) -> Track:
    return _track_with_volume(track_id, 100, panning)


def _track_with_volume(track_id: int, volume: float, panning: int = 100) -> Track:
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
        volume=volume,
        panning=panning,
    )


def _multi_note_track(track_id: int, panning: int) -> Track:
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
            NoteEvent(
                tick=1,
                layer=track_id,
                instrument=0,
                key=45,
                final_volume=100,
                final_panning=panning,
            ),
        ),
        volume=100,
        panning=panning,
    )


if __name__ == "__main__":
    unittest.main()
