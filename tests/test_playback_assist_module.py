import unittest
from dataclasses import replace

from nbs2func.layout import BlockPosition
from nbs2func.core.minecraft_version import JAVA_1_16_5, MinecraftVersionError
from nbs2func.modules.playback_assist import (
    PlaybackAssistModuleConfig,
    default_vehicle_spawn_position,
    playback_assist_lines,
    playback_assist_debug_info,
)
from nbs2func.core.models import Song
from nbs2func.core.tempo_control import build_tempo_control_report


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

    def test_tempo_report_mode_does_not_change_playback_commands(self) -> None:
        config = PlaybackAssistModuleConfig(enable_playback_assist=True)

        text = "\n".join(playback_assist_lines(config))

        self.assertNotIn("tick rate", text)

    def test_tempo_command_mode_adds_tick_rate_and_reset_commands(self) -> None:
        report = build_tempo_control_report(
            Song(
                name="Tempo Song",
                author="Tester",
                length=1,
                tracks=(),
                nbs_tempo_tps=10,
            ),
            minecraft_version_profile=JAVA_1_16_5,
        )
        config = PlaybackAssistModuleConfig(
            enable_playback_assist=True,
            tempo_control_mode="command",
            tempo_control_report=report,
        )

        text = "\n".join(playback_assist_lines(config))

        self.assertIn("tick rate 40", text)
        self.assertIn("tick rate 20", text)

    def test_playback_assist_rejects_unsupported_profile(self) -> None:
        profile = replace(JAVA_1_16_5, supports_playback_assist=False)
        config = PlaybackAssistModuleConfig(
            enable_playback_assist=True,
            minecraft_version_profile=profile,
        )

        with self.assertRaises(MinecraftVersionError) as context:
            playback_assist_lines(config)

        message = str(context.exception)
        self.assertIn("Playback assist is not supported", message)
        self.assertIn("1.16.5", message)


if __name__ == "__main__":
    unittest.main()
