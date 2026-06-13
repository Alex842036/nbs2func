import unittest

from nbs2func.layout import BlockPosition
from nbs2func.playback_assist_module import (
    PlaybackAssistModuleConfig,
    default_vehicle_spawn_position,
    playback_assist_lines,
    playback_assist_debug_info,
)


class PlaybackAssistCoordinateTests(unittest.TestCase):
    def test_default_vehicle_spawn_is_behind_music_start(self) -> None:
        music_start = BlockPosition(0, 128, 0)
        cases = {
            "east": BlockPosition(-10, 128, 0),
            "west": BlockPosition(10, 128, 0),
            "south": BlockPosition(0, 128, -10),
            "north": BlockPosition(0, 128, 10),
        }

        for direction, expected in cases.items():
            with self.subTest(direction=direction):
                self.assertEqual(
                    default_vehicle_spawn_position(music_start, direction, 10),
                    expected,
                )

    def test_west_default_vehicle_spawn_is_valid(self) -> None:
        config = PlaybackAssistModuleConfig(
            enable_playback_assist=True,
            music_start_position=BlockPosition(0, 128, 0),
            track_direction="west",
        )

        debug = playback_assist_debug_info(config)

        self.assertEqual(debug.vehicle_spawn_position, BlockPosition(10, 128, 0))
        self.assertEqual(debug.start_music_count, 10)
        self.assertEqual(debug.yaw, 90)

    def test_playback_assist_uses_minecart_vehicle(self) -> None:
        config = PlaybackAssistModuleConfig(enable_playback_assist=True)

        text = "\n".join(playback_assist_lines(config))

        self.assertIn("summon minecraft:minecart", text)
        self.assertIn("@e[type=minecraft:minecart,tag=playback_vehicle]", text)
        self.assertIn("@e[tag=playback_vehicle,type=minecraft:minecart]", text)
        self.assertNotIn("summon minecraft:pig", text)
        self.assertNotIn("Saddle:1b", text)
        self.assertNotIn("NoAI:1b", text)
        self.assertNotIn("@e[type=minecraft:pig,tag=toolpig]", text)


if __name__ == "__main__":
    unittest.main()
