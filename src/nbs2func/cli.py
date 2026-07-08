from __future__ import annotations

import argparse
import cProfile
import io
import json
from pathlib import Path
import pstats
import re
import sys

from .output.block_builder import (
    RUNTIME_LOGIC_BUILD_PLAN,
    STRUCTURE_ONLY_BUILD_PLAN,
    STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN,
    build_generated_plan,
    filter_generated_plan,
)
from .output.command_writer import CommandWriterConfig, write_mcfunction
from .output.schematic_writer import (
    resolve_schematic_origin,
    schematic_warnings,
    write_schematic,
)
from .config import (
    Nbs2FuncConfig,
    config_from_dict,
    config_to_dict,
    default_config,
    load_config,
    save_config,
)
from .generation import (
    GenerationEvent,
    generate_from_config,
    sanitize_datapack_name,
)
from .core.instrument_mapping import validate_song_instruments_for_version
from .layout import build_layout_strategy, layout_song
from .layout.geometry import BlockPosition, LayoutError
from .layout.models import StereoLayoutConfig
from .analysis.spatial_analyzer import (
    analysis_report_to_jsonable,
    analyze_layout_spatial,
)
from .core.minecraft_version import (
    DEFAULT_MINECRAFT_VERSION,
    MinecraftVersionError,
    get_minecraft_version_profile,
    write_pack_mcmeta,
)
from .core.nbs_reader import read_nbs
from .modules.playback_assist import (
    PlaybackAssistModuleConfig,
    playback_assist_debug_info,
    total_track_length_from_layout,
)
from .core.tempo_control import (
    TempoControlError,
    build_tempo_control_report,
    tempo_report_lines,
)

DEFAULT_NBS_PATH = Path("examples/demo.nbs")
DEFAULT_OUTPUT_PATH = Path("output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Note Block Studio .nbs files into Minecraft functions."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Load generation config JSON before applying explicit CLI overrides.",
    )
    parser.add_argument(
        "--save-config",
        default=None,
        help="Save the final effective generation config JSON.",
    )
    parser.add_argument(
        "--dump-default-config",
        action="store_true",
        help="Print the default generation config JSON and exit.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=str(DEFAULT_NBS_PATH),
        help="Path to a Note Block Studio .nbs file. Defaults to examples/demo.nbs.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Parent directory for the generated datapack. Defaults to output.",
    )
    parser.add_argument(
        "--output-format",
        choices=("datapack", "schem", "both"),
        default="datapack",
        help="Output format to generate. Defaults to datapack.",
    )
    parser.add_argument(
        "--schematic-origin-mode",
        choices=("generation_origin", "min_corner"),
        default="generation_origin",
        help="Origin for schematic relative coordinates. Defaults to generation_origin.",
    )
    parser.add_argument(
        "--schematic-output",
        default=None,
        help="Optional .schem output path or folder. Defaults under --output.",
    )
    parser.add_argument(
        "--schematic-name",
        default=None,
        help="Optional schematic file name without .schem extension.",
    )
    parser.add_argument(
        "--analyze-stereo",
        action="store_true",
        help="Removed. Use --analyze-layout-spatial instead.",
    )
    parser.add_argument(
        "--analyze-layout-spatial",
        action="store_true",
        help="Analyze layer-local layout spatial features and output JSON without building.",
    )
    parser.add_argument(
        "--group-config",
        default=None,
        help="Removed for layout spatial analysis. Group configs are not consumed.",
    )
    parser.add_argument(
        "--analysis-output",
        default=None,
        help="Optional output path for the analysis JSON report.",
    )
    parser.add_argument(
        "--analysis-window-size",
        type=int,
        default=128,
        help="Window size in ticks for layout spatial analysis. Defaults to 128.",
    )
    parser.add_argument(
        "--analysis-hop-size",
        type=int,
        default=32,
        help="Hop size in ticks for layout spatial analysis. Defaults to 32.",
    )
    parser.add_argument(
        "--analysis-detail",
        choices=("summary", "full"),
        default="summary",
        help="Analysis output detail for layout spatial analysis. Defaults to summary.",
    )
    parser.add_argument("--origin-x", type=int, default=0, help="World origin X.")
    parser.add_argument("--origin-y", type=int, default=128, help="World origin Y.")
    parser.add_argument("--origin-z", type=int, default=0, help="World origin Z.")
    parser.add_argument(
        "--layout-mode",
        choices=("basic_linear", "track_based_stereo", "note_based_stereo"),
        default="note_based_stereo",
        help="Layout strategy to use. Defaults to note_based_stereo.",
    )
    parser.add_argument(
        "--track-id",
        type=int,
        default=None,
        help="Track id to generate in basic_linear mode when multiple tracks have notes.",
    )
    parser.add_argument(
        "--direction",
        choices=("east", "west", "south", "north", "x+", "x-", "z+", "z-"),
        default="east",
        help="Track direction for the generated structure. Defaults to east.",
    )
    parser.add_argument(
        "--max-hearing-distance",
        type=float,
        default=48,
        help="Maximum stereo layout hearing distance. Defaults to 48.",
    )
    parser.add_argument(
        "--min-distance",
        type=float,
        default=4,
        help="Minimum stereo layout distance. Defaults to 4.",
    )
    parser.add_argument(
        "--max-stereo-angle-degrees",
        type=float,
        default=90,
        help="Maximum stereo angle in degrees. Defaults to 90. Values above 90 are clamped.",
    )
    parser.add_argument(
        "--center-threshold",
        type=float,
        default=10,
        help="Stereo distance from center eligible for center split. Defaults to 10.",
    )
    parser.add_argument(
        "--center-split-policy",
        choices=("none", "manual", "auto_on_collision", "manual_plus_auto"),
        default="auto_on_collision",
        help="Per-track center split policy. Defaults to auto_on_collision.",
    )
    parser.add_argument(
        "--center-split-mode",
        choices=("duplicate_half_volume",),
        default="duplicate_half_volume",
        help="How split clones keep volume/radius. Defaults to duplicate_half_volume.",
    )
    parser.add_argument(
        "--center-split-override",
        action="append",
        default=[],
        metavar="TRACK_ID=split|none",
        help="Manual per-track center split override. Can be repeated.",
    )
    parser.add_argument(
        "--center-split-pan",
        type=float,
        default=50,
        help="Pan offset used for center split clones. Defaults to 50.",
    )
    parser.add_argument(
        "--max-auto-center-splits",
        type=int,
        default=20,
        help="Maximum automatic center splits before falling back to resolver. Defaults to 20.",
    )
    parser.add_argument(
        "--disable-collision-resolver",
        action="store_true",
        help="Disable whole-track collision resolution for track_based_stereo.",
    )
    parser.add_argument(
        "--disable-depth-mirror-fallback",
        action="store_true",
        help="Disable depth mirror fallback in the track collision resolver.",
    )
    parser.add_argument(
        "--disable-radius-relax-fallback",
        action="store_true",
        help="Disable radius relax fallback in the track collision resolver.",
    )
    parser.add_argument(
        "--max-angle-deviation-degrees",
        type=float,
        default=30,
        help="Maximum angle deviation for collision resolution. Defaults to 30.",
    )
    parser.add_argument(
        "--angle-search-step-degrees",
        type=float,
        default=5,
        help="Angle search step for collision resolution. Defaults to 5.",
    )
    parser.add_argument(
        "--radius-relax-step",
        type=float,
        default=1,
        help="Radius relax step for collision resolution. Defaults to 1.",
    )
    parser.add_argument(
        "--max-radius-relax",
        type=float,
        default=3,
        help="Maximum radius relax distance. Defaults to 3.",
    )
    parser.add_argument(
        "--min-world-y",
        type=int,
        default=None,
        help="Optional minimum world Y for track collision resolver candidates.",
    )
    parser.add_argument(
        "--max-world-y",
        type=int,
        default=None,
        help="Optional maximum world Y for track collision resolver candidates.",
    )
    parser.add_argument(
        "--disable-pan-zone-layout",
        action="store_true",
        help="Advanced debug option: disable pan-zone candidate generation.",
    )
    parser.add_argument(
        "--allow-adjacent-pan-zone-fallback",
        action="store_true",
        help="Allow note_based_stereo candidates in adjacent pan zones.",
    )
    parser.add_argument(
        "--pan-zone-search-radius-limit",
        type=int,
        default=8,
        help="Offset search radius for note_based_stereo pan zones. Defaults to 8.",
    )
    parser.add_argument(
        "--max-candidates-per-emitter",
        type=int,
        default=64,
        help="Maximum note_based_stereo candidates per emitter. Defaults to 64.",
    )
    parser.add_argument(
        "--max-candidate-y-layers",
        type=int,
        default=8,
        help="Maximum Y layers scanned per emitter candidate set. Defaults to 8.",
    )
    parser.add_argument(
        "--max-candidate-lateral-positions",
        type=int,
        default=16,
        help="Maximum lateral positions scanned per emitter candidate set. Defaults to 16.",
    )
    parser.add_argument(
        "--radius-search-tolerance",
        type=float,
        default=4,
        help="Allowed radius error for note_based_stereo candidates. Defaults to 4.",
    )
    parser.add_argument(
        "--max-lateral-distance",
        type=int,
        default=48,
        help="Legacy fixed-lateral zone setting. Angle-based note layout no longer uses it.",
    )
    parser.add_argument(
        "--pan-zone-reference-radius",
        type=float,
        default=48,
        help="Reference radius used to document pan-zone angle thresholds. Defaults to 48.",
    )
    parser.add_argument(
        "--disable-depth-mirror-candidates",
        action="store_true",
        help="Disable -Y mirror candidates for note_based_stereo emitter placement.",
    )
    parser.add_argument(
        "--preferred-depth-sign",
        type=int,
        choices=(-1, 1),
        default=1,
        help="Preferred note_based_stereo depth sign before mirror fallback. Defaults to 1.",
    )
    parser.add_argument(
        "--disallow-negative-depth-offsets",
        action="store_true",
        help="Do not generate negative depth offsets in note_based_stereo candidates.",
    )
    parser.add_argument(
        "--depth-mirror-penalty",
        type=float,
        default=0.0,
        help="Extra cost for -Y mirror candidates. Defaults to 0.0.",
    )
    parser.add_argument(
        "--lateral-step-penalty",
        type=float,
        default=0.5,
        help="Cost per lateral step in note_based_stereo candidates. Defaults to 0.5.",
    )
    parser.add_argument(
        "--disable-adjacent-pan-zone-fallback-for-failed",
        action="store_true",
        help="Disable failed-only same-side adjacent pan-zone retry.",
    )
    parser.add_argument(
        "--retry-max-candidates-per-emitter",
        type=int,
        default=256,
        help="Maximum retry candidates for failed note_based_stereo emitters. Defaults to 256.",
    )
    parser.add_argument(
        "--enable-same-side-zone-split-fallback",
        action="store_true",
        help="Enable experimental same-side zone split fallback for failed L/R emitters.",
    )
    parser.add_argument(
        "--same-side-split-volume-factor",
        type=float,
        default=0.5,
        help="Volume factor for same-side zone split fallback. Defaults to 0.5.",
    )
    parser.add_argument(
        "--min-rail-center-y-gap",
        type=int,
        default=4,
        help="Minimum center Y gap for rails with overlapping activation ranges. Defaults to 4.",
    )
    parser.add_argument(
        "--activation-slot-radius",
        type=int,
        default=1,
        help="Side-slot radius used for note_based_stereo rail spacing. Defaults to 1.",
    )
    parser.add_argument(
        "--max-collision-records",
        type=int,
        default=5000,
        help="Maximum stored note_based_stereo collision records. Defaults to 5000.",
    )
    parser.add_argument(
        "--max-collision-examples-per-group",
        type=int,
        default=20,
        help="Maximum collision examples per summary group. Defaults to 20.",
    )
    parser.add_argument(
        "--preview-time-limit-seconds",
        type=float,
        default=1200,
        help="Time limit for note_based_stereo preview. Defaults to 600 seconds.",
    )
    parser.add_argument(
        "--no-fail-fast-on-too-many-collisions",
        action="store_true",
        help="Continue storing collision stats instead of fail-fast behavior.",
    )
    parser.add_argument(
        "--max-collision-records-before-abort",
        type=int,
        default=50000,
        help="Collision record threshold for abort decisions. Defaults to 50000.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Print cProfile cumulative-time report for layout generation.",
    )
    parser.add_argument(
        "--disable-note-level-center-split",
        action="store_true",
        help="Disable failed CENTER emitter split fallback in note_based_stereo.",
    )
    parser.add_argument(
        "--center-split-left-pan",
        type=float,
        default=75,
        help="Left pan for note-level center split fallback. Defaults to 75.",
    )
    parser.add_argument(
        "--center-split-right-pan",
        type=float,
        default=125,
        help="Right pan for note-level center split fallback. Defaults to 125.",
    )
    parser.add_argument(
        "--center-split-volume-factor",
        type=float,
        default=0.5,
        help="Volume factor for each note-level center split clone. Defaults to 0.5.",
    )
    parser.add_argument(
        "--max-note-level-center-splits",
        type=int,
        default=100,
        help="Maximum note-level center split fallback attempts. Defaults to 100.",
    )
    parser.add_argument(
        "--enable-starter-module",
        action="store_true",
        help="Generate starter cells and a command block to start all tracks together.",
    )
    parser.add_argument(
        "--command-block-x",
        type=int,
        default=-10,
        help="Starter command block X position. Defaults to -10.",
    )
    parser.add_argument(
        "--command-block-y",
        type=int,
        default=128,
        help="Starter command block Y position. Defaults to 128.",
    )
    parser.add_argument(
        "--command-block-z",
        type=int,
        default=0,
        help="Starter command block Z position. Defaults to 0.",
    )
    parser.add_argument(
        "--starter-tag",
        default="nbs_starter",
        help="Armor stand tag used by the starter module. Defaults to nbs_starter.",
    )
    parser.add_argument(
        "--starter-track-block",
        default=None,
        help="Block under starter power markers. Defaults to the normal track block.",
    )
    parser.add_argument(
        "--starter-cell-offset",
        type=int,
        default=-1,
        help="Starter cell offset in cells from the first normal cell. Defaults to -1.",
    )
    parser.add_argument(
        "--enable-playback-assist",
        action="store_true",
        help="Generate minecart playback assist command blocks.",
    )
    parser.add_argument(
        "--playback-player-name",
        default="Alex842036",
        help="Player scoreboard name for playback assist. Defaults to Alex842036.",
    )
    parser.add_argument(
        "--playback-vehicle-tag",
        default="playback_vehicle",
        help="Minecart entity tag for playback assist. Defaults to playback_vehicle.",
    )
    parser.add_argument(
        "--count-objective",
        default="count",
        help="Scoreboard objective for playback assist. Defaults to count.",
    )
    parser.add_argument(
        "--vehicle-spawn-x",
        type=int,
        default=None,
        help="Optional playback minecart spawn X position. Defaults behind music start.",
    )
    parser.add_argument(
        "--vehicle-spawn-y",
        type=int,
        default=None,
        help="Optional playback minecart spawn Y position. Defaults to music start Y.",
    )
    parser.add_argument(
        "--vehicle-spawn-z",
        type=int,
        default=None,
        help="Optional playback minecart spawn Z position. Defaults behind music start.",
    )
    parser.add_argument(
        "--music-start-x",
        type=int,
        default=0,
        help="Playback music start X position. Defaults to 0.",
    )
    parser.add_argument(
        "--music-start-y",
        type=int,
        default=128,
        help="Playback music start Y position. Defaults to 128.",
    )
    parser.add_argument(
        "--music-start-z",
        type=int,
        default=0,
        help="Playback music start Z position. Defaults to 0.",
    )
    parser.add_argument(
        "--command-module-origin-x",
        type=int,
        default=None,
        help="Playback command module origin X position. Defaults to 15 blocks behind music start.",
    )
    parser.add_argument(
        "--command-module-origin-y",
        type=int,
        default=None,
        help="Playback command module origin Y position. Defaults to music start Y.",
    )
    parser.add_argument(
        "--command-module-origin-z",
        type=int,
        default=None,
        help="Playback command module origin Z position. Defaults to 15 blocks behind music start.",
    )
    parser.add_argument(
        "--no-playback-buttons",
        action="store_true",
        help="Do not generate Prepare and Start buttons for playback assist.",
    )
    parser.add_argument(
        "--playback-button-block",
        default="minecraft:stone_button",
        help="Button block used for playback assist. Defaults to minecraft:stone_button.",
    )
    parser.add_argument(
        "--prepare-button-x",
        type=int,
        default=None,
        help="Optional Prepare button X position. Defaults to above the Prepare command block.",
    )
    parser.add_argument(
        "--prepare-button-y",
        type=int,
        default=None,
        help="Optional Prepare button Y position. Defaults to above the Prepare command block.",
    )
    parser.add_argument(
        "--prepare-button-z",
        type=int,
        default=None,
        help="Optional Prepare button Z position. Defaults to above the Prepare command block.",
    )
    parser.add_argument(
        "--start-button-x",
        type=int,
        default=None,
        help="Optional Start button X position. Defaults to above the Start command block.",
    )
    parser.add_argument(
        "--start-button-y",
        type=int,
        default=None,
        help="Optional Start button Y position. Defaults to above the Start command block.",
    )
    parser.add_argument(
        "--start-button-z",
        type=int,
        default=None,
        help="Optional Start button Z position. Defaults to above the Start command block.",
    )
    parser.add_argument(
        "--no-split-functions",
        action="store_true",
        help="Write one .mcfunction file instead of splitting large builds.",
    )
    parser.add_argument(
        "--max-commands-per-build-part",
        type=int,
        default=500,
        help="Maximum commands in each player-tp build part. Defaults to 500.",
    )
    parser.add_argument(
        "--schedule-delay-ticks-between-parts",
        type=int,
        default=10,
        help="Delay between player-tp build parts. Defaults to 10 ticks.",
    )
    parser.add_argument(
        "--build-player-name",
        default="Alex842036",
        help="Player to teleport for player-tp build loading. Defaults to Alex842036.",
    )
    parser.add_argument(
        "--player-load-radius-chunks",
        type=int,
        default=6,
        help="Assumed reliable chunk loading radius around the player. Defaults to 6.",
    )
    parser.add_argument(
        "--player-tp-chunk-load-wait-ticks",
        type=int,
        default=100,
        help="Wait after teleporting before building a window. Defaults to 100 ticks.",
    )
    parser.add_argument(
        "--player-tp-after-build-wait-ticks",
        type=int,
        default=20,
        help="Wait after finishing a window before the next teleport. Defaults to 20 ticks.",
    )
    parser.add_argument(
        "--player-tp-window-length-blocks",
        type=int,
        default=192,
        help="Main-axis block length for each player-tp build window. Defaults to 192.",
    )
    parser.add_argument(
        "--player-tp-window-lateral-width-blocks",
        type=int,
        default=192,
        help="Lateral block width for each player-tp build window. Defaults to 192.",
    )
    parser.add_argument(
        "--build-tp-y",
        type=int,
        default=None,
        help="Optional fixed Y coordinate for player-tp build window centers.",
    )
    parser.add_argument(
        "--build-finish-tp-x",
        type=int,
        default=None,
        help="Optional X coordinate to teleport the build player to after completion.",
    )
    parser.add_argument(
        "--build-finish-tp-y",
        type=int,
        default=None,
        help="Optional Y coordinate to teleport the build player to after completion.",
    )
    parser.add_argument(
        "--build-finish-tp-z",
        type=int,
        default=None,
        help="Optional Z coordinate to teleport the build player to after completion.",
    )
    parser.add_argument(
        "--function-namespace",
        default="nbs",
        help="Function namespace for split output. Defaults to nbs.",
    )
    parser.add_argument(
        "--build-function-dir",
        default="build",
        help="Function directory for split output. Defaults to build.",
    )
    parser.add_argument(
        "--minecraft-version",
        default=DEFAULT_MINECRAFT_VERSION,
        help=(
            "Target Minecraft Java Edition profile. Defaults to 1.16.5. "
            "Aliases such as 1.16 select a specific profile, not a full "
            "minor-version series."
        ),
    )
    parser.add_argument(
        "--tempo-control-mode",
        choices=("none", "report", "command"),
        default="report",
        help=(
            "Tempo control mode. Defaults to report, which prints a recommendation "
            "without changing world tick rate."
        ),
    )
    parser.add_argument(
        "--tempo-control-backend",
        choices=("auto", "carpet", "vanilla"),
        default="auto",
        help="Tick rate command backend. Defaults to auto.",
    )
    parser.add_argument(
        "--tempo-rate-decimals",
        type=int,
        default=2,
        help="Decimal places for tick rate commands. Defaults to 2.",
    )
    parser.add_argument(
        "--game-ticks-per-song-tick",
        type=int,
        default=4,
        help="Redstone timing model in game ticks per NBS tick. Defaults to 4.",
    )
    parser.add_argument(
        "--no-reset-tick-rate-after-playback",
        action="store_true",
        help="Do not generate a tick rate 20 reset command in tempo command mode.",
    )
    return parser


def resolve_config_from_args(
    args: argparse.Namespace,
    explicit_destinations: set[str],
) -> Nbs2FuncConfig:
    config = load_config(args.config) if args.config is not None else default_config()
    updates: dict[str, object] = {}

    direct_fields = set(config_to_dict(config))
    direct_cli_fields = direct_fields - {
        "input_path",
        "center_split_overrides",
        "enable_collision_resolver",
        "enable_depth_mirror_fallback",
        "enable_radius_relax_fallback",
        "enable_pan_zone_layout",
        "enable_depth_mirror_candidates",
        "allow_negative_depth_offsets",
        "allow_adjacent_pan_zone_fallback_for_failed",
        "fail_fast_on_too_many_collisions",
        "enable_note_level_center_split",
        "generate_playback_buttons",
        "split_functions",
        "reset_tick_rate_after_playback",
    }
    for field_name in sorted(direct_cli_fields):
        if field_name in explicit_destinations:
            updates[field_name] = getattr(args, field_name)

    if "file" in explicit_destinations:
        updates["input_path"] = args.file
    if "center_split_override" in explicit_destinations:
        updates["center_split_overrides"] = _parse_center_split_overrides(
            args.center_split_override
        )
    if "disable_collision_resolver" in explicit_destinations:
        updates["enable_collision_resolver"] = not args.disable_collision_resolver
    if "disable_depth_mirror_fallback" in explicit_destinations:
        updates["enable_depth_mirror_fallback"] = (
            not args.disable_depth_mirror_fallback
        )
    if "disable_radius_relax_fallback" in explicit_destinations:
        updates["enable_radius_relax_fallback"] = (
            not args.disable_radius_relax_fallback
        )
    if "disable_pan_zone_layout" in explicit_destinations:
        updates["enable_pan_zone_layout"] = not args.disable_pan_zone_layout
    if "disable_depth_mirror_candidates" in explicit_destinations:
        updates["enable_depth_mirror_candidates"] = (
            not args.disable_depth_mirror_candidates
        )
    if "disallow_negative_depth_offsets" in explicit_destinations:
        updates["allow_negative_depth_offsets"] = (
            not args.disallow_negative_depth_offsets
        )
    if "disable_adjacent_pan_zone_fallback_for_failed" in explicit_destinations:
        updates["allow_adjacent_pan_zone_fallback_for_failed"] = (
            not args.disable_adjacent_pan_zone_fallback_for_failed
        )
    if "no_fail_fast_on_too_many_collisions" in explicit_destinations:
        updates["fail_fast_on_too_many_collisions"] = (
            not args.no_fail_fast_on_too_many_collisions
        )
    if "disable_note_level_center_split" in explicit_destinations:
        updates["enable_note_level_center_split"] = (
            not args.disable_note_level_center_split
        )
    if "no_playback_buttons" in explicit_destinations:
        updates["generate_playback_buttons"] = not args.no_playback_buttons
    if "no_split_functions" in explicit_destinations:
        updates["split_functions"] = not args.no_split_functions
    if "no_reset_tick_rate_after_playback" in explicit_destinations:
        updates["reset_tick_rate_after_playback"] = (
            not args.no_reset_tick_rate_after_playback
        )

    return config_from_updates(config, updates)


def config_from_updates(
    config: Nbs2FuncConfig,
    updates: dict[str, object],
) -> Nbs2FuncConfig:
    if not updates:
        return config
    data = config_to_dict(config)
    for key, value in updates.items():
        data[key] = value
    return config_from_dict(data)


def _explicit_cli_destinations(
    parser: argparse.ArgumentParser,
    argv: list[str],
) -> set[str]:
    option_actions = {
        option: action
        for action in parser._actions
        for option in action.option_strings
    }
    explicit: set[str] = set()
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            if index + 1 < len(argv):
                explicit.add("file")
            break
        if token.startswith("-") and token != "-":
            option, has_inline_value = _split_option_token(token)
            action = option_actions.get(option)
            if action is None:
                index += 1
                continue
            explicit.add(action.dest)
            if _action_consumes_value(action) and not has_inline_value:
                index += 2
            else:
                index += 1
            continue
        explicit.add("file")
        index += 1
    return explicit


def _split_option_token(token: str) -> tuple[str, bool]:
    if token.startswith("--") and "=" in token:
        option, _value = token.split("=", 1)
        return option, True
    return token, False


def _action_consumes_value(action: argparse.Action) -> bool:
    return not isinstance(
        action,
        (argparse._StoreTrueAction, argparse._StoreFalseAction),
    )


def _args_namespace_from_config(config: Nbs2FuncConfig) -> argparse.Namespace:
    overrides = config.center_split_overrides or {}
    return argparse.Namespace(
        file=config.input_path,
        output=config.output,
        output_format=config.output_format,
        schematic_origin_mode=config.schematic_origin_mode,
        schematic_output=config.schematic_output,
        schematic_name=config.schematic_name,
        analyze_stereo=config.analyze_stereo,
        analyze_layout_spatial=config.analyze_layout_spatial,
        group_config=config.group_config,
        analysis_output=config.analysis_output,
        analysis_window_size=config.analysis_window_size,
        analysis_hop_size=config.analysis_hop_size,
        analysis_detail=config.analysis_detail,
        origin_x=config.origin_x,
        origin_y=config.origin_y,
        origin_z=config.origin_z,
        layout_mode=config.layout_mode,
        track_id=config.track_id,
        direction=config.direction,
        max_hearing_distance=config.max_hearing_distance,
        min_distance=config.min_distance,
        max_stereo_angle_degrees=config.max_stereo_angle_degrees,
        center_threshold=config.center_threshold,
        center_split_policy=config.center_split_policy,
        center_split_mode=config.center_split_mode,
        center_split_override=[
            f"{track_id}={action}"
            for track_id, action in sorted(overrides.items())
        ],
        center_split_pan=config.center_split_pan,
        max_auto_center_splits=config.max_auto_center_splits,
        disable_collision_resolver=not config.enable_collision_resolver,
        disable_depth_mirror_fallback=not config.enable_depth_mirror_fallback,
        disable_radius_relax_fallback=not config.enable_radius_relax_fallback,
        max_angle_deviation_degrees=config.max_angle_deviation_degrees,
        angle_search_step_degrees=config.angle_search_step_degrees,
        radius_relax_step=config.radius_relax_step,
        max_radius_relax=config.max_radius_relax,
        min_world_y=config.min_world_y,
        max_world_y=config.max_world_y,
        disable_pan_zone_layout=not config.enable_pan_zone_layout,
        allow_adjacent_pan_zone_fallback=config.allow_adjacent_pan_zone_fallback,
        pan_zone_search_radius_limit=config.pan_zone_search_radius_limit,
        max_candidates_per_emitter=config.max_candidates_per_emitter,
        max_candidate_y_layers=config.max_candidate_y_layers,
        max_candidate_lateral_positions=config.max_candidate_lateral_positions,
        radius_search_tolerance=config.radius_search_tolerance,
        max_lateral_distance=config.max_lateral_distance,
        pan_zone_reference_radius=config.pan_zone_reference_radius,
        disable_depth_mirror_candidates=not config.enable_depth_mirror_candidates,
        preferred_depth_sign=config.preferred_depth_sign,
        disallow_negative_depth_offsets=not config.allow_negative_depth_offsets,
        depth_mirror_penalty=config.depth_mirror_penalty,
        lateral_step_penalty=config.lateral_step_penalty,
        disable_adjacent_pan_zone_fallback_for_failed=(
            not config.allow_adjacent_pan_zone_fallback_for_failed
        ),
        retry_max_candidates_per_emitter=config.retry_max_candidates_per_emitter,
        enable_same_side_zone_split_fallback=(
            config.enable_same_side_zone_split_fallback
        ),
        same_side_split_volume_factor=config.same_side_split_volume_factor,
        min_rail_center_y_gap=config.min_rail_center_y_gap,
        activation_slot_radius=config.activation_slot_radius,
        max_collision_records=config.max_collision_records,
        max_collision_examples_per_group=config.max_collision_examples_per_group,
        preview_time_limit_seconds=config.preview_time_limit_seconds,
        no_fail_fast_on_too_many_collisions=(
            not config.fail_fast_on_too_many_collisions
        ),
        max_collision_records_before_abort=config.max_collision_records_before_abort,
        profile=config.profile,
        disable_note_level_center_split=not config.enable_note_level_center_split,
        center_split_left_pan=config.center_split_left_pan,
        center_split_right_pan=config.center_split_right_pan,
        center_split_volume_factor=config.center_split_volume_factor,
        max_note_level_center_splits=config.max_note_level_center_splits,
        enable_starter_module=config.enable_starter_module,
        command_block_x=config.command_block_x,
        command_block_y=config.command_block_y,
        command_block_z=config.command_block_z,
        starter_tag=config.starter_tag,
        starter_track_block=config.starter_track_block,
        starter_cell_offset=config.starter_cell_offset,
        enable_playback_assist=config.enable_playback_assist,
        playback_player_name=config.playback_player_name,
        playback_vehicle_tag=config.playback_vehicle_tag,
        count_objective=config.count_objective,
        vehicle_spawn_x=config.vehicle_spawn_x,
        vehicle_spawn_y=config.vehicle_spawn_y,
        vehicle_spawn_z=config.vehicle_spawn_z,
        music_start_x=config.music_start_x,
        music_start_y=config.music_start_y,
        music_start_z=config.music_start_z,
        command_module_origin_x=config.command_module_origin_x,
        command_module_origin_y=config.command_module_origin_y,
        command_module_origin_z=config.command_module_origin_z,
        no_playback_buttons=not config.generate_playback_buttons,
        playback_button_block=config.playback_button_block,
        prepare_button_x=config.prepare_button_x,
        prepare_button_y=config.prepare_button_y,
        prepare_button_z=config.prepare_button_z,
        start_button_x=config.start_button_x,
        start_button_y=config.start_button_y,
        start_button_z=config.start_button_z,
        no_split_functions=not config.split_functions,
        max_commands_per_build_part=config.max_commands_per_build_part,
        schedule_delay_ticks_between_parts=(
            config.schedule_delay_ticks_between_parts
        ),
        build_player_name=config.build_player_name,
        player_load_radius_chunks=config.player_load_radius_chunks,
        player_tp_chunk_load_wait_ticks=config.player_tp_chunk_load_wait_ticks,
        player_tp_after_build_wait_ticks=config.player_tp_after_build_wait_ticks,
        player_tp_window_length_blocks=config.player_tp_window_length_blocks,
        player_tp_window_lateral_width_blocks=(
            config.player_tp_window_lateral_width_blocks
        ),
        build_tp_y=config.build_tp_y,
        build_finish_tp_x=config.build_finish_tp_x,
        build_finish_tp_y=config.build_finish_tp_y,
        build_finish_tp_z=config.build_finish_tp_z,
        function_namespace=config.function_namespace,
        build_function_dir=config.build_function_dir,
        minecraft_version=config.minecraft_version,
        tempo_control_mode=config.tempo_control_mode,
        tempo_control_backend=config.tempo_control_backend,
        tempo_rate_decimals=config.tempo_rate_decimals,
        game_ticks_per_song_tick=config.game_ticks_per_song_tick,
        no_reset_tick_rate_after_playback=(
            not config.reset_tick_rate_after_playback
        ),
    )


def _print_generation_event(event: GenerationEvent) -> None:
    if event.kind == "notice":
        print(f"NOTICE: {event.message}")
    elif event.kind == "warning":
        print(f"WARNING: {event.message}")
    elif event.kind == "error":
        return
    else:
        print(event.message)


def main() -> int:
    parser = build_parser()
    raw_args = parser.parse_args()
    if raw_args.dump_default_config:
        print(json.dumps(config_to_dict(default_config()), indent=2))
        return 0

    try:
        config = resolve_config_from_args(
            raw_args,
            _explicit_cli_destinations(parser, sys.argv[1:]),
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    if raw_args.save_config is not None:
        try:
            save_config(config, raw_args.save_config)
        except OSError as exc:
            print(f"Error: could not save config: {exc}")
            return 1

    args = _args_namespace_from_config(config)
    if args.analyze_stereo:
        print("Error: --analyze-stereo was removed. Use --analyze-layout-spatial.")
        return 1

    if args.analyze_layout_spatial:
        path = Path(args.file)
        try:
            get_minecraft_version_profile(args.minecraft_version)
        except MinecraftVersionError as exc:
            print(f"Error: {exc}")
            return 1
        if not path.exists():
            print(f"Error: NBS file not found: {path}")
            print(
                "Pass a valid .nbs path, or run without arguments to use "
                "examples/demo.nbs."
            )
            return 1
        if not path.is_file():
            print(f"Error: path is not a file: {path}")
            return 1
        song = read_nbs(path)
        return _run_analyze_layout_spatial(args, song)

    try:
        generate_from_config(config, progress_callback=_print_generation_event)
    except (
        FileNotFoundError,
        ValueError,
        OSError,
        MinecraftVersionError,
        TempoControlError,
        LayoutError,
        NotImplementedError,
    ) as exc:
        print(f"Error: {exc}")
        return 1
    return 0

    path = Path(args.file)
    try:
        version_profile = get_minecraft_version_profile(args.minecraft_version)
    except MinecraftVersionError as exc:
        print(f"Error: {exc}")
        return 1

    if not path.exists():
        print(f"Error: NBS file not found: {path}")
        print("Pass a valid .nbs path, or run without arguments to use examples/demo.nbs.")
        return 1

    if not path.is_file():
        print(f"Error: path is not a file: {path}")
        return 1

    song = read_nbs(path)
    note_count = sum(len(track.notes) for track in song.tracks)

    if args.analyze_stereo:
        print("Error: --analyze-stereo was removed. Use --analyze-layout-spatial.")
        return 1

    if args.analyze_layout_spatial:
        return _run_analyze_layout_spatial(args, song)

    tempo_report = None
    if args.tempo_control_mode != "none":
        try:
            tempo_report = build_tempo_control_report(
                song,
                minecraft_version_profile=version_profile,
                backend=args.tempo_control_backend,
                rate_decimals=args.tempo_rate_decimals,
                game_ticks_per_song_tick=args.game_ticks_per_song_tick,
            )
        except TempoControlError as exc:
            print(f"Error: {exc}")
            return 1

    if args.tempo_control_mode == "command" and not args.enable_playback_assist:
        print(
            "Error: --tempo-control-mode command requires "
            "--enable-playback-assist so the tick rate command has a playback "
            "start command block."
        )
        return 1

    try:
        validate_song_instruments_for_version(song, version_profile)
    except MinecraftVersionError as exc:
        print(f"Error: {exc}")
        return 1

    print("Song")
    print(f"  file: {path}")
    print(f"  name: {song.name}")
    print(f"  author: {song.author}")
    print(f"  length: {song.length} ticks")
    print(f"  tracks: {len(song.tracks)}")
    print(f"  notes: {note_count}")
    print()
    if tempo_report is not None:
        for line in tempo_report_lines(tempo_report):
            print(line)
        if args.tempo_control_mode == "report":
            print("  Mode: report only; no tick rate command will be generated.")
        elif args.tempo_control_mode == "command":
            print("  Mode: command; playback assist will set the tick rate on start.")
        print()
    print("Track note summary")

    for track in song.tracks:
        if track.notes:
            ticks = [note.tick for note in track.notes]
            volumes = [note.final_volume for note in track.notes]
            pannings = [note.final_panning for note in track.notes]
            detail = (
                f"tick_range={min(ticks)}-{max(ticks)} "
                f"final_volume_range={min(volumes):.2f}-{max(volumes):.2f} "
                f"final_panning_range={min(pannings):.2f}-{max(pannings):.2f}"
            )
        else:
            detail = "empty"
        print(
            f"  track={track.id} "
            f"name={track.name!r} "
            f"source_layer={track.source_layer} "
            f"layer_volume={track.volume} "
            f"layer_stereo={track.panning} "
            f"notes={len(track.notes)} "
            f"{detail}"
        )

    strategy = build_layout_strategy(
        mode=args.layout_mode,
        origin=BlockPosition(args.origin_x, args.origin_y, args.origin_z),
        track_direction=args.direction,
        selected_track_id=args.track_id,
        stereo_config=StereoLayoutConfig(
            max_hearing_distance=args.max_hearing_distance,
            min_distance=args.min_distance,
            max_stereo_angle_degrees=args.max_stereo_angle_degrees,
            center_threshold=args.center_threshold,
            center_split_policy=args.center_split_policy,
            center_split_overrides=_parse_center_split_overrides(
                args.center_split_override
            ),
            center_split_mode=args.center_split_mode,
            center_split_pan=args.center_split_pan,
            max_auto_center_splits=args.max_auto_center_splits,
            enable_collision_resolver=not args.disable_collision_resolver,
            enable_depth_mirror_fallback=not args.disable_depth_mirror_fallback,
            enable_radius_relax_fallback=not args.disable_radius_relax_fallback,
            max_angle_deviation_degrees=args.max_angle_deviation_degrees,
            angle_search_step_degrees=args.angle_search_step_degrees,
            radius_relax_step=args.radius_relax_step,
            max_radius_relax=args.max_radius_relax,
            min_world_y=args.min_world_y,
            max_world_y=args.max_world_y,
            enable_pan_zone_layout=not args.disable_pan_zone_layout,
            allow_adjacent_pan_zone_fallback=args.allow_adjacent_pan_zone_fallback,
            pan_zone_search_radius_limit=args.pan_zone_search_radius_limit,
            max_candidates_per_emitter=args.max_candidates_per_emitter,
            max_candidate_y_layers=args.max_candidate_y_layers,
            max_candidate_lateral_positions=args.max_candidate_lateral_positions,
            radius_search_tolerance=args.radius_search_tolerance,
            max_lateral_distance=args.max_lateral_distance,
            pan_zone_reference_radius=args.pan_zone_reference_radius,
            enable_depth_mirror_candidates=(
                not args.disable_depth_mirror_candidates
            ),
            preferred_depth_sign=args.preferred_depth_sign,
            allow_negative_depth_offsets=(
                not args.disallow_negative_depth_offsets
            ),
            depth_mirror_penalty=args.depth_mirror_penalty,
            lateral_step_penalty=args.lateral_step_penalty,
            allow_adjacent_pan_zone_fallback_for_failed=(
                not args.disable_adjacent_pan_zone_fallback_for_failed
            ),
            retry_max_candidates_per_emitter=args.retry_max_candidates_per_emitter,
            enable_same_side_zone_split_fallback=(
                args.enable_same_side_zone_split_fallback
            ),
            same_side_split_volume_factor=args.same_side_split_volume_factor,
            min_rail_center_y_gap=args.min_rail_center_y_gap,
            activation_slot_radius=args.activation_slot_radius,
            max_collision_records=args.max_collision_records,
            max_collision_examples_per_group=args.max_collision_examples_per_group,
            preview_time_limit_seconds=args.preview_time_limit_seconds,
            fail_fast_on_too_many_collisions=(
                not args.no_fail_fast_on_too_many_collisions
            ),
            max_collision_records_before_abort=(
                args.max_collision_records_before_abort
            ),
            enable_progress_logging=args.layout_mode == "note_based_stereo",
            enable_note_level_center_split=(
                not args.disable_note_level_center_split
            ),
            center_split_left_pan=args.center_split_left_pan,
            center_split_right_pan=args.center_split_right_pan,
            center_split_volume_factor=args.center_split_volume_factor,
            max_note_level_center_splits=args.max_note_level_center_splits,
        ),
    )
    try:
        profiler = cProfile.Profile() if args.profile else None
        if profiler is not None:
            profiler.enable()
        layout = layout_song(song, strategy)
        if profiler is not None:
            profiler.disable()
            _print_profile_report(profiler)
    except NotImplementedError as exc:
        if args.profile and "profiler" in locals() and profiler is not None:
            profiler.disable()
            _print_profile_report(profiler)
        print(f"Error: {exc}")
        return 1
    except LayoutError as exc:
        if args.profile and "profiler" in locals() and profiler is not None:
            profiler.disable()
            _print_profile_report(profiler)
        print(f"Error: {exc}")
        return 1

    print()
    print(f"Layout preview ({layout.mode})")

    if layout.note_based_preview is not None:
        _print_note_based_preview(layout.note_based_preview)

    if layout.track_layouts:
        print("Track offsets")
        for info in layout.track_layouts:
            role = f" virtual={info.virtual_role}" if info.virtual_role else ""
            split = (
                f" split_reason={info.split_reason} split_mode={info.split_mode}"
                if info.split_reason
                else ""
            )
            print(
                f"  track={info.track_id} "
                f"layer={info.layer_id} "
                f"name={info.name!r}"
                f"{role} "
                f"original=(offset_y={info.original_offset_y}, "
                f"lateral={info.original_offset_lateral}, "
                f"radius={info.original_radius:.2f}, "
                f"angle={info.original_angle_degrees:.2f}) "
                f"resolved=(offset_y={info.offset_y}, "
                f"lateral={info.offset_lateral}, "
                f"radius={info.radius:.2f}, "
                f"angle={info.angle_degrees:.2f}) "
                f"fallback={info.fallback} "
                f"attempts={info.attempt_count} "
                f"unresolved={info.unresolved_stage}"
                f"{split}"
            )

    if layout.center_split_events:
        print("Center split events")
        for event in layout.center_split_events:
            print(
                f"  original_track={event.original_track_id} "
                f"layer={event.original_layer_id} "
                f"name={event.original_track_name!r} "
                f"clone={event.clone_track_id} "
                f"side={event.clone_side} "
                f"reason={event.split_reason} "
                f"mode={event.split_mode} "
                f"before=(y={event.before_offset_y}, "
                f"lateral={event.before_offset_lateral}, "
                f"radius={event.before_radius:.2f}, "
                f"angle={event.before_angle_degrees:.2f}) "
                f"after=(y={event.after_offset_y}, "
                f"lateral={event.after_offset_lateral}, "
                f"radius={event.after_radius:.2f}, "
                f"angle={event.after_angle_degrees:.2f})"
            )

    if layout.conflicts:
        print("Conflicts")
        for conflict in layout.conflicts:
            print(
                f"  tick={conflict.tick} "
                f"track={conflict.track_id} "
                f"notes={conflict.note_count}"
            )
    elif layout.collisions:
        print("Conflicts: hard block collisions found; see collision overview below")
    else:
        print("Conflicts: none")

    involved_collision_tracks = {
        summary.first_track.track_id
        for summary in layout.collision_summaries
    } | {
        summary.second_track.track_id
        for summary in layout.collision_summaries
    }
    print("Collision overview")
    print(f"  hard collision groups: {len(layout.collision_summaries)}")
    print(f"  hard collision records: {len(layout.collisions)}")
    print(f"  involved tracks: {len(involved_collision_tracks)}")

    if layout.collision_summaries:
        print("Hard collision summaries")
        for summary in layout.collision_summaries:
            first = summary.first_track
            second = summary.second_track
            print(
                f"  {summary.collision_type}: "
                f"track_a={first.track_id} layer={first.layer_id} name={first.name!r} "
                f"original=(y={first.original_offset_y}, lateral={first.original_offset_lateral}, "
                f"radius={first.original_radius:.2f}, angle={first.original_angle_degrees:.2f}) "
                f"resolved=(y={first.offset_y}, lateral={first.offset_lateral}, "
                f"radius={first.radius:.2f}, angle={first.angle_degrees:.2f}) "
                f"fallback={first.fallback} attempts={first.attempt_count} "
                f"unresolved={first.unresolved_stage}; "
                f"track_b={second.track_id} layer={second.layer_id} name={second.name!r} "
                f"original=(y={second.original_offset_y}, lateral={second.original_offset_lateral}, "
                f"radius={second.original_radius:.2f}, angle={second.original_angle_degrees:.2f}) "
                f"resolved=(y={second.offset_y}, lateral={second.offset_lateral}, "
                f"radius={second.radius:.2f}, angle={second.angle_degrees:.2f}) "
                f"fallback={second.fallback} attempts={second.attempt_count} "
                f"unresolved={second.unresolved_stage}; "
                f"estimated_cells={summary.estimated_cell_count}"
            )
            print("    examples:")
            for example in summary.examples:
                pos = example.position
                print(
                    f"      pos=({pos.x},{pos.y},{pos.z}) "
                    f"{example.first_block_type}@tick={example.first_tick} "
                    f"vs {example.second_block_type}@tick={example.second_tick}"
                )
    else:
        print("Hard collision summaries: none")

    if layout.collision_summaries == () and layout.collisions:
        print("Hard collision examples")
        for collision in layout.collisions[:3]:
            pos = collision.position
            print(
                f"  {collision.collision_type}: pos=({pos.x},{pos.y},{pos.z}) "
                f"{collision.first_block_type}@track={collision.first_track_id} "
                f"tick={collision.first_tick} vs "
                f"{collision.second_block_type}@track={collision.second_track_id} "
                f"tick={collision.second_tick}"
            )

    print("Placed note summary by track")
    for track_id, notes in _notes_by_track(layout.notes).items():
        first_note = notes[0]
        last_note = notes[-1]
        first_pos = first_note.note_block_position
        last_pos = last_note.note_block_position
        virtual = (
            f" virtual={first_note.virtual_role}"
            if first_note.virtual_role
            else ""
        )
        split = (
            f" split_reason={first_note.split_reason} split_mode={first_note.split_mode}"
            if first_note.split_reason
            else ""
        )
        print(
            f"  track={track_id} "
            f"source_track={first_note.source_track_id} "
            f"layer={first_note.layer} "
            f"notes={len(notes)} "
            f"tick_range={first_note.tick}-{last_note.tick} "
            f"track_volume={first_note.track_volume:.2f} "
            f"track_stereo={first_note.track_panning:.2f}"
            f"{virtual} "
            f"{split} "
            f"first_note=({first_pos.x},{first_pos.y},{first_pos.z}) "
            f"last_note=({last_pos.x},{last_pos.y},{last_pos.z})"
        )

    if layout.collisions:
        print()
        print("Did not generate mcfunction because block collision errors were found.")
        return 1

    if (
        layout.note_based_preview is not None
        and layout.note_based_preview.failed_assignment_count > 0
    ):
        print()
        print("Did not generate mcfunction because some emitters were not assigned.")
        return 1

    music_start_position = BlockPosition(
        args.music_start_x,
        args.music_start_y,
        args.music_start_z,
    )
    playback_total_track_length = total_track_length_from_layout(
        layout,
        args.direction,
        music_start_position,
    )
    playback_config = PlaybackAssistModuleConfig(
        enable_playback_assist=args.enable_playback_assist,
        player_name=args.playback_player_name,
        playback_vehicle_tag=args.playback_vehicle_tag,
        starter_tag=args.starter_tag,
        count_objective=args.count_objective,
        vehicle_spawn_position=_optional_position(
            args.vehicle_spawn_x,
            args.vehicle_spawn_y,
            args.vehicle_spawn_z,
        ),
        music_start_position=music_start_position,
        command_module_origin=_optional_position(
            args.command_module_origin_x,
            args.command_module_origin_y,
            args.command_module_origin_z,
        ),
        track_direction=args.direction,
        total_track_length=playback_total_track_length,
        generate_playback_buttons=not args.no_playback_buttons,
        playback_button_block=args.playback_button_block,
        prepare_button_position=_optional_position(
            args.prepare_button_x,
            args.prepare_button_y,
            args.prepare_button_z,
        ),
        start_button_position=_optional_position(
            args.start_button_x,
            args.start_button_y,
            args.start_button_z,
        ),
        minecraft_version_profile=version_profile,
        tempo_control_mode=args.tempo_control_mode,
        tempo_control_report=tempo_report,
        reset_tick_rate_after_playback=(
            not args.no_reset_tick_rate_after_playback
        ),
    )
    if args.enable_playback_assist:
        try:
            playback_debug = playback_assist_debug_info(playback_config)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        print()
        print("Playback assist")
        print(
            "  prepare_command_block_position: "
            f"{_format_position(playback_debug.prepare_command_block_position)}"
        )
        print(
            "  prepare_button_position: "
            f"{_format_position(playback_debug.prepare_button_position)}"
        )
        print(
            "  start_command_block_position: "
            f"{_format_position(playback_debug.start_command_block_position)}"
        )
        print(
            "  start_button_position: "
            f"{_format_position(playback_debug.start_button_position)}"
        )
        print(
            "  vehicle_spawn_position: "
            f"{_format_position(playback_debug.vehicle_spawn_position)}"
        )
        print(f"  music_start_position: {_format_position(playback_debug.music_start_position)}")
        print(f"  track_direction: {playback_debug.track_direction}")
        print(f"  yaw: {playback_debug.yaw}")
        print(f"  start_music_count: {playback_debug.start_music_count}")
        print(f"  end_count: {playback_debug.end_count}")
        print(f"  total_track_length: {playback_debug.total_track_length}")
        print(
            "  command_module_origin: "
            f"{_format_position(playback_debug.command_module_origin)}"
        )

    output_root = Path(args.output)
    datapack_root = output_root / sanitize_datapack_name(path.stem)
    writer_output_path = datapack_root
    writer_config = CommandWriterConfig(
        enable_starter_module=(
            args.enable_starter_module or args.enable_playback_assist
        ),
        command_block_position=BlockPosition(
            args.command_block_x,
            args.command_block_y,
            args.command_block_z,
        ),
        starter_tag=args.starter_tag,
        starter_track_block=args.starter_track_block,
        starter_cell_offset=args.starter_cell_offset,
        split_functions=not args.no_split_functions,
        function_namespace=args.function_namespace,
        build_function_dir=args.build_function_dir,
        minecraft_version_profile=version_profile,
        max_commands_per_build_part=args.max_commands_per_build_part,
        schedule_delay_ticks_between_parts=(
            args.schedule_delay_ticks_between_parts
        ),
        build_player_name=args.build_player_name,
        player_load_radius_chunks=args.player_load_radius_chunks,
        player_tp_chunk_load_wait_ticks=args.player_tp_chunk_load_wait_ticks,
        player_tp_after_build_wait_ticks=args.player_tp_after_build_wait_ticks,
        player_tp_window_length_blocks=args.player_tp_window_length_blocks,
        player_tp_window_lateral_width_blocks=(
            args.player_tp_window_lateral_width_blocks
        ),
        build_tp_y=args.build_tp_y,
        build_finish_tp_position=_optional_position(
            args.build_finish_tp_x,
            args.build_finish_tp_y,
            args.build_finish_tp_z,
        ),
        enable_playback_assist=args.enable_playback_assist,
        playback_player_name=args.playback_player_name,
        playback_vehicle_tag=args.playback_vehicle_tag,
        count_objective=args.count_objective,
        vehicle_spawn_position=playback_config.vehicle_spawn_position,
        music_start_position=playback_config.music_start_position,
        command_module_origin=playback_config.command_module_origin,
        playback_track_direction=args.direction,
        playback_total_track_length=playback_total_track_length,
        generate_playback_buttons=not args.no_playback_buttons,
        playback_button_block=args.playback_button_block,
        prepare_button_position=playback_config.prepare_button_position,
        start_button_position=playback_config.start_button_position,
        requested_origin_y=args.origin_y,
        tempo_control_mode=args.tempo_control_mode,
        tempo_control_report=tempo_report,
        reset_tick_rate_after_playback=(
            not args.no_reset_tick_rate_after_playback
        ),
    )
    full_build_plan = build_generated_plan(layout, writer_config)
    datapack_plan = full_build_plan
    schematic_plan = (
        filter_generated_plan(full_build_plan, STRUCTURE_WITH_MODULE_BLOCKS_BUILD_PLAN)
        if args.output_format == "both"
        else filter_generated_plan(full_build_plan, STRUCTURE_ONLY_BUILD_PLAN)
    )
    runtime_plan = filter_generated_plan(full_build_plan, RUNTIME_LOGIC_BUILD_PLAN)

    write_result = None
    if args.output_format in {"datapack", "both"}:
        if args.no_split_functions:
            write_pack_mcmeta(datapack_root, version_profile)
            writer_output_path = (
                datapack_root
                / "data"
                / args.function_namespace
                / version_profile.function_dir_name
                / args.build_function_dir
                / "start.mcfunction"
            )
        write_result = write_mcfunction(
            layout,
            writer_output_path,
            writer_config,
            plan=(runtime_plan if args.output_format == "both" else datapack_plan),
        )

    schematic_path = None
    schematic_origin = None
    if args.output_format in {"schem", "both"}:
        generation_origin = BlockPosition(args.origin_x, args.origin_y, args.origin_z)
        try:
            schematic_origin = resolve_schematic_origin(
                schematic_plan,
                args.schematic_origin_mode,
                generation_origin,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        schematic_output = (
            Path(args.schematic_output)
            if args.schematic_output is not None
            else output_root / f"{sanitize_datapack_name(path.stem)}.schem"
        )
        schematic_path = write_schematic(
            schematic_plan,
            schematic_output,
            version_profile=version_profile,
            schematic_origin=schematic_origin,
            schematic_name=args.schematic_name,
        )

    if layout.note_based_preview is not None and write_result is not None:
        _print_note_based_build_debug(layout.note_based_preview, write_result)

    if write_result is not None and write_result.player_tp_build is not None:
        _print_player_tp_build_debug(write_result.player_tp_build)

    print()
    if write_result is not None and args.no_split_functions:
        print(f"Generated datapack: {datapack_root}")
        print(f"Generated mcfunction: {writer_output_path}")
    elif write_result is not None:
        print(f"Generated datapack: {datapack_root}")
        print(
            "If split output was needed, run "
            f"/function {args.function_namespace}:{args.build_function_dir}/start"
        )
    if schematic_path is not None and schematic_origin is not None:
        print(f"Generated schematic: {schematic_path}")
        print(f"  schematic origin: {_format_position(schematic_origin)}")
        if args.output_format == "schem" and (
            args.enable_starter_module or args.enable_playback_assist
        ):
            print(
                "  WARNING: Schematic output does not include starter or "
                "playback assist modules."
            )
            print(
                "  WARNING: These modules require mcfunction support to "
                "execute runtime logic."
            )
        if args.output_format == "both":
            print(
                "  Note: The .schem file contains all blocks including "
                "command blocks."
            )
            print(
                "  Note: The .mcfunction output contains runtime logic such "
                "as scoreboard, summon, and execute."
            )
        for warning in schematic_warnings(schematic_plan):
            print(f"  WARNING: {warning}")

    return 0


def _run_analyze_layout_spatial(args, song) -> int:
    if args.group_config is not None:
        print(
            "Error: --group-config is not supported by "
            "--analyze-layout-spatial."
        )
        return 1

    try:
        report = analyze_layout_spatial(
            song,
            window_size=args.analysis_window_size,
            hop_size=args.analysis_hop_size,
            detail=args.analysis_detail,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    json_text = json.dumps(
        analysis_report_to_jsonable(report, detail=args.analysis_detail),
        indent=2,
    )
    if args.analysis_output is not None:
        output_path = Path(args.analysis_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_text + "\n", encoding="utf-8")
    else:
        print(json_text)

    return 0


def sanitize_datapack_name(name: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]+", "_", name.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "nbs_song"


def _notes_by_track(notes):
    grouped = {}
    for note in notes:
        grouped.setdefault(note.track_id, []).append(note)

    return {
        track_id: sorted(track_notes, key=lambda note: note.tick)
        for track_id, track_notes in grouped.items()
    }


def _print_note_based_preview(report) -> None:
    print("Note-based stereo rail preview")
    print(f"  total NoteEvent count: {report.total_note_events}")
    print(f"  total ideal emitters: {report.total_ideal_emitters}")
    print(f"  total activation rails: {report.total_activation_rails}")
    print(f"  unchanged ideal assignments: {report.unchanged_assignments}")
    print(f"  assignments with y movement: {report.y_movement_assignments}")
    print(f"  assignments with z movement: {report.z_movement_assignments}")
    print(f"  failed assignment count: {report.failed_assignment_count}")
    print(f"  average movement cost: {report.average_movement_cost:.3f}")
    print(f"  max movement cost: {report.max_movement_cost:.3f}")
    print(f"  positive depth rail count: {report.positive_depth_rail_count}")
    print(f"  negative depth rail count: {report.negative_depth_rail_count}")
    print(f"  positive depth assignments: {report.positive_depth_assignments}")
    print(f"  negative depth assignments: {report.negative_depth_assignments}")
    print(
        "  mirror fallback accepted / rejected: "
        f"{report.mirror_fallback_accepted_count} / "
        f"{report.mirror_fallback_rejected_count}"
    )
    print(
        "  average +Y assignment cost: "
        f"{report.average_positive_depth_assignment_cost:.3f}"
    )
    print(
        "  average -Y mirrored assignment cost: "
        f"{report.average_negative_depth_assignment_cost:.3f}"
    )
    print(f"  failed count after Pass 1: {report.failed_assignment_count_after_pass1}")
    print(f"  failed count after Pass 2: {report.failed_assignment_count_after_pass2}")
    print(f"  failed count after Pass 3: {report.failed_assignment_count_after_pass3}")
    print(
        "  retry attempted / accepted / failed: "
        f"{report.retry_attempted_count} / "
        f"{report.retry_accepted_count} / "
        f"{report.retry_failed_count}"
    )
    print(
        "  adjacent zone fallback attempted / accepted / failed: "
        f"{report.adjacent_zone_fallback_attempted_count} / "
        f"{report.adjacent_zone_fallback_accepted_count} / "
        f"{report.adjacent_zone_fallback_failed_count}"
    )
    print(f"  candidate truncation count: {report.candidate_truncation_count}")
    print(
        "  mirror candidate truncated count: "
        f"{report.mirror_candidate_truncated_count}"
    )
    if report.average_candidate_count_by_pass:
        print("  average candidate count by pass:")
        for pass_name, average in report.average_candidate_count_by_pass:
            print(f"    {pass_name}: {average:.2f}")
    print("Note-based stereo performance diagnostics")
    print(f"  total layout time: {report.total_note_based_layout_seconds:.3f}s")
    print(f"  ideal emitter build time: {report.ideal_emitter_build_seconds:.3f}s")
    print(f"  candidate generation time: {report.candidate_generation_seconds:.3f}s")
    print(f"  assignment total time: {report.assignment_total_seconds:.3f}s")
    print("  assignment breakdown:")
    print(f"    pass1 assignment: {report.pass1_assignment_seconds:.3f}s")
    print(
        "    pass2 retry candidate generation / merge / assignment: "
        f"{report.pass2_retry_candidate_generation_seconds:.3f}s / "
        f"{report.pass2_candidate_value_merge_seconds:.3f}s / "
        f"{report.pass2_assignment_seconds:.3f}s"
    )
    print(
        "    pass3 retry candidate generation / merge / assignment: "
        f"{report.pass3_retry_candidate_generation_seconds:.3f}s / "
        f"{report.pass3_candidate_value_merge_seconds:.3f}s / "
        f"{report.pass3_assignment_seconds:.3f}s"
    )
    print(
        "    same-side split / note-level center split / final fallback: "
        f"{report.same_side_split_seconds:.3f}s / "
        f"{report.note_level_center_split_seconds:.3f}s / "
        f"{report.final_fallback_split_handling_seconds:.3f}s"
    )
    print("  retry candidate generation:")
    print(
        "    pass2 emitters / total / avg / max: "
        f"{report.pass2_retry_emitter_count} / "
        f"{report.pass2_retry_total_candidates_generated} / "
        f"{report.pass2_retry_average_candidates_per_emitter:.2f} / "
        f"{report.pass2_retry_max_candidates_for_one_emitter}"
    )
    print(
        "    pass3 emitters / total / avg / max: "
        f"{report.pass3_retry_emitter_count} / "
        f"{report.pass3_retry_total_candidates_generated} / "
        f"{report.pass3_retry_average_candidates_per_emitter:.2f} / "
        f"{report.pass3_retry_max_candidates_for_one_emitter}"
    )
    print(f"  retry total time: {report.retry_total_seconds:.3f}s")
    print(f"  center split time: {report.center_split_total_seconds:.3f}s")
    print(f"  debug report build time: {report.debug_report_build_seconds:.3f}s")
    print(f"  rail validation time: {report.rail_validation_total_seconds:.3f}s")
    print(f"  footprint collision time: {report.footprint_collision_total_seconds:.3f}s")
    print(f"  rail center upgrade time: {report.rail_center_upgrade_total_seconds:.3f}s")
    print("  geometry skeleton cache:")
    print(
        "    hits / misses / unique keys: "
        f"{report.geometry_skeleton_cache_hits} / "
        f"{report.geometry_skeleton_cache_misses} / "
        f"{report.geometry_skeleton_unique_key_count}"
    )
    print(
        "    generated / reused skeleton candidates: "
        f"{report.geometry_skeleton_candidates_generated} / "
        f"{report.geometry_skeleton_candidates_reused}"
    )
    print(f"    hit rate: {report.geometry_skeleton_cache_hit_rate:.3f}")
    if report.geometry_skeleton_top_key_counts:
        print("    top key counts:")
        for key_label, count in report.geometry_skeleton_top_key_counts:
            print(f"      {key_label}: {count}")
    print("  candidate attempts:")
    print(f"    total: {report.candidate_attempt_count_total}")
    for pass_name, count in report.candidate_attempt_count_by_pass:
        print(f"    {pass_name}: {count}")
    print(
        "    existing active rail / new rail validation: "
        f"{report.candidate_attempts_on_existing_active_rail} / "
        f"{report.candidate_attempts_requiring_new_rail_validation}"
    )
    print(
        "    rejected slot / rail validation / footprint: "
        f"{report.candidate_attempts_rejected_by_slot_used} / "
        f"{report.candidate_attempts_rejected_by_rail_validation} / "
        f"{report.candidate_attempts_rejected_by_footprint_collision}"
    )
    print(f"    accepted: {report.candidate_attempts_accepted}")
    print("  rail validation:")
    print(f"    calls: {report.rail_validation_call_count}")
    for pass_name, count in report.rail_validation_call_count_by_pass:
        print(f"    calls {pass_name}: {count}")
    print(f"    rail pairs checked: {report.rail_pairs_checked}")
    for pass_name, count in report.rail_pairs_checked_by_pass:
        print(f"    rail pairs {pass_name}: {count}")
    print(
        "    avg/max rails checked per validation: "
        f"{report.average_rails_checked_per_candidate:.3f} / "
        f"{report.max_rails_checked_per_candidate}"
    )
    print(f"    accepted: {report.rail_validation_accepted_count}")
    print(
        "    rejected overlap / footprint: "
        f"{report.rail_validation_rejected_by_activation_overlap} / "
        f"{report.rail_pairs_rejected_by_full_footprint_collision}"
    )
    print("  footprint collision:")
    print(f"    checks: {report.footprint_collision_check_count}")
    print(
        "    avg check time: "
        f"{report.average_footprint_collision_seconds:.6f}s"
    )
    print(
        "    assignment / rail / upgrade time: "
        f"{report.assignment_footprint_collision_elapsed_seconds:.3f}s / "
        f"{report.rail_footprint_collision_elapsed_seconds:.3f}s / "
        f"{report.upgrade_footprint_collision_elapsed_seconds:.3f}s"
    )
    print(
        "  rail center upgrade attempted / accepted / rejected: "
        f"{report.rail_center_upgrade_attempted} / "
        f"{report.rail_center_upgrade_accepted} / "
        f"{report.rail_center_upgrade_rejected}"
    )
    print(
        "    rejected missing track / footprint / reserved air: "
        f"{report.rail_center_upgrade_rejected_by_missing_track_block} / "
        f"{report.rail_center_upgrade_rejected_by_center_footprint_collision} / "
        f"{report.rail_center_upgrade_rejected_by_reserved_air_collision}"
    )
    print(
        "    occupancy copies / local removes / local rollbacks: "
        f"{report.rail_center_upgrade_occupancy_copy_count} / "
        f"{report.rail_center_upgrade_local_remove_count} / "
        f"{report.rail_center_upgrade_local_rollback_count}"
    )
    if report.candidate_count_before_truncation_by_pass:
        print("  candidate count before truncation by pass:")
        for pass_name, count in report.candidate_count_before_truncation_by_pass:
            print(f"    {pass_name}: {count}")
    if report.candidate_count_after_truncation_by_pass:
        print("  candidate count after truncation by pass:")
        for pass_name, count in report.candidate_count_after_truncation_by_pass:
            print(f"    {pass_name}: {count}")
    if report.candidate_truncation_count_by_pass:
        print("  candidate truncation count by pass:")
        for pass_name, count in report.candidate_truncation_count_by_pass:
            print(f"    {pass_name}: {count}")
    if report.mirror_candidate_truncation_count_by_pass:
        print("  mirror candidate truncation count by pass:")
        for pass_name, count in report.mirror_candidate_truncation_count_by_pass:
            print(f"    {pass_name}: {count}")
    print(f"  pan zone unchanged count: {report.pan_zone_unchanged_count}")
    print(f"  adjacent zone fallback count: {report.adjacent_zone_fallback_count}")
    print(f"  average radius error: {report.average_radius_error:.3f}")
    print(f"  max radius error: {report.max_radius_error:.3f}")
    print(
        "  average pan error inside zone: "
        f"{report.average_pan_error_inside_zone:.3f}"
    )
    before = (
        str(report.rail_collision_count_before)
        if report.rail_collision_count_before is not None
        else "n/a"
    )
    after = (
        str(report.rail_collision_count_after)
        if report.rail_collision_count_after is not None
        else "n/a"
    )
    print(f"  rail collision count before / after: {before} / {after}")
    print(
        "  average used slots per active rail cell: "
        f"{report.average_used_slots_per_active_rail_cell:.3f}"
    )

    print("Performance report")
    print(f"  total notes: {report.total_note_events}")
    print(f"  total candidates generated: {report.total_candidates_generated}")
    print(
        "  average candidates per emitter: "
        f"{report.average_candidates_per_emitter:.2f}"
    )
    print(
        "  max candidates for one emitter: "
        f"{report.max_candidates_for_one_emitter}"
    )
    print(
        "  average rails checked per candidate: "
        f"{report.average_rails_checked_per_candidate:.2f}"
    )
    print(
        "  max rails checked per candidate: "
        f"{report.max_rails_checked_per_candidate}"
    )
    print(f"  collision records stored: {report.collision_records_stored}")
    print(
        "  collision records skipped due to cap: "
        f"{report.collision_records_skipped_due_to_cap}"
    )
    if report.stage_timings:
        print("  stage timings:")
        for timing in report.stage_timings:
            print(f"    {timing.stage}: {timing.seconds:.3f}s")

    print("Note-level center split fallback")
    print(f"  attempted: {report.center_split_attempted_count}")
    print(f"  accepted: {report.center_split_accepted_count}")
    print(f"  failed: {report.center_split_failed_count}")
    print(f"  emitters added: {report.emitters_added_by_center_split}")
    print(
        "  failed assignment count before split: "
        f"{report.failed_assignment_count_before_split}"
    )
    print(
        "  failed assignment count after split: "
        f"{report.failed_assignment_count_after_split}"
    )
    if report.center_split_examples:
        print("  first center split examples")
        for example in report.center_split_examples[:20]:
            print(
                f"    original={example.original_emitter_id} "
                f"tick={example.tick} layer={example.layer} "
                f"left={example.left_emitter_id} pan={example.left_pan:.1f} "
                f"right={example.right_emitter_id} pan={example.right_pan:.1f} "
                f"accepted={example.accepted} reason={example.reason}"
            )

    print("Failed assignments by pan zone")
    if not report.failed_assignment_count_by_pan_zone:
        print("  none")
    for zone, count in report.failed_assignment_count_by_pan_zone:
        print(f"  {zone}: {count}")

    print("Failed assignments by depth sign")
    if not report.failed_assignment_count_by_depth_sign:
        print("  none")
    for sign, count in report.failed_assignment_count_by_depth_sign:
        print(f"  {sign}: {count}")

    print("Adjacent zone fallback by source zone")
    if not report.adjacent_zone_fallback_by_source_zone:
        print("  none")
    for zone, attempted, accepted, failed in report.adjacent_zone_fallback_by_source_zone:
        print(
            f"  {zone}: attempted={attempted} accepted={accepted} failed={failed}"
        )

    print("Failed assignment examples after passes")
    examples_by_pass = (
        ("pass1", report.failed_examples_after_pass1),
        ("pass2", report.failed_examples_after_pass2),
        ("pass3", report.failed_examples_after_pass3),
    )
    for pass_name, examples in examples_by_pass:
        if not examples:
            print(f"  {pass_name}: none")
            continue
        print(f"  {pass_name}:")
        for example in examples[:20]:
            print(f"    {example}")

    print("Assignment pan examples")
    if not report.assignments:
        print("  none")
    for assignment in report.assignments[:20]:
        emitter = assignment.emitter
        depth_sign = "negative" if assignment.candidate.offset_y < 0 else "positive"
        print(
            f"  emitter={emitter.emitter_id} "
            f"tick={emitter.tick} "
            f"note_pan={emitter.note_panning:.1f} "
            f"layer_pan={emitter.layer_panning:.1f} "
            f"note_delta={emitter.note_pan_delta:.1f} "
            f"layer_delta={emitter.layer_pan_delta:.1f} "
            f"final_pan_delta={emitter.final_pan_delta:.1f} "
            f"final_pan={emitter.final_panning:.1f} "
            f"target_angle={emitter.target_angle_degrees:.1f} "
            f"target_radius={emitter.target_radius:.1f} "
            f"pan_zone={emitter.pan_zone} "
            f"chosen_angle={assignment.candidate.chosen_angle_degrees:.1f} "
            f"chosen_radius={assignment.candidate.chosen_radius:.1f} "
            f"chosen_y={assignment.candidate.offset_y} "
            f"chosen_lateral={assignment.candidate.offset_lateral} "
            f"depth_sign={depth_sign}"
        )

    print("Rail spacing / collision validation")
    print(f"  total rails: {report.total_activation_rails}")
    print(f"  rail pairs checked: {report.rail_pairs_checked}")
    print(
        "  rail pairs rejected by same-plane y gap: "
        f"{report.rail_pairs_rejected_by_same_plane_y_gap}"
    )
    print(
        "  rail pairs rejected by full footprint collision: "
        f"{report.rail_pairs_rejected_by_full_footprint_collision}"
    )
    if report.invalid_rail_pairs:
        print("  invalid rail pair examples")
        for issue in report.invalid_rail_pairs[:10]:
            a = issue.rail_a_center
            b = issue.rail_b_center
            collision = issue.first_collision_position
            collision_text = (
                f" first_collision=({collision.x},{collision.y},{collision.z})"
                if collision is not None
                else ""
            )
            print(
                f"    {issue.reason}: "
                f"rail_a={issue.rail_a_id} center=({a.x},{a.y},{a.z}) "
                f"rail_b={issue.rail_b_id} center=({b.x},{b.y},{b.z}) "
                f"direction={issue.direction} "
                f"rail_a_y={a.y} "
                f"rail_b_y={b.y} "
                f"rail_a_transverse_range={issue.rail_a_transverse_range} "
                f"rail_b_transverse_range={issue.rail_b_transverse_range} "
                f"ranges_overlap={issue.activation_ranges_overlap} "
                f"y_gap={issue.y_gap} "
                f"min_y_gap={issue.min_rail_center_y_gap}"
                f"{collision_text}"
            )

    print("Pan zone distribution")
    if not report.pan_zone_distribution:
        print("  none")
    for stat in report.pan_zone_distribution:
        print(
            f"  {stat.zone}: pan={stat.pan_min:.0f}-{stat.pan_max:.0f} "
            f"angle={stat.allowed_angle_range} "
            f"emitters={stat.emitter_count} "
            f"assignments={stat.assignment_count} "
            f"failed={stat.failed_count} "
            f"avg_target_angle={stat.average_target_angle:.2f} "
            f"avg_chosen_angle={stat.average_chosen_angle:.2f} "
            f"avg_target_radius={stat.average_target_radius:.2f} "
            f"avg_chosen_radius={stat.average_chosen_radius:.2f}"
        )

    print("Rail usage statistics")
    if not report.rail_usage_statistics:
        print("  none")
        return

    for stat in sorted(
        report.rail_usage_statistics,
        key=lambda item: (-item.used_slot_count, item.rail_id),
    )[:20]:
        print(
            f"  rail={stat.rail_id} "
            f"offset=(y={stat.offset_y}, lateral={stat.offset_lateral}) "
            f"candidate_value={stat.candidate_value} "
            f"active_cells={stat.active_cell_count} "
            f"used_slots={stat.used_slot_count} "
            f"avg_slots_per_cell={stat.average_used_slots_per_active_cell:.2f}"
        )

    if len(report.rail_usage_statistics) > 20:
        print(f"  ... {len(report.rail_usage_statistics) - 20} more rails")


def _print_note_based_build_debug(report, write_result) -> None:
    center_slot_count = sum(
        1
        for assignment in report.assignments
        if assignment.slot.slot_index == 0
    )
    side_slot_count = len(report.assignments) - center_slot_count

    print()
    print("Note-based stereo rail build debug")
    print(f"  total rails: {report.total_activation_rails}")
    print(f"  total emitters: {len(report.assignments)}")
    print(f"  total commands: {write_result.total_commands}")
    print(f"  total split function parts: {write_result.split_function_parts}")
    print(f"  center slot emitter count: {center_slot_count}")
    print(f"  side slot emitter count: {side_slot_count}")


def _print_profile_report(profiler: cProfile.Profile) -> None:
    output = io.StringIO()
    stats = pstats.Stats(profiler, stream=output)
    stats.strip_dirs().sort_stats("cumulative").print_stats(30)
    print()
    print("cProfile cumulative time top 30")
    print(output.getvalue())


def _print_player_tp_build_debug(debug) -> None:
    box = debug.build_bounding_box
    print()
    print("Build output")
    print("  build mode: player_tp")
    print(
        "  build bounding box: "
        f"({box.min_x},{box.min_y},{box.min_z}) -> "
        f"({box.max_x},{box.max_y},{box.max_z})"
    )
    print(f"  track_direction: {debug.track_direction}")
    print(f"  split axis: {debug.split_axis}")
    print(f"  build player name: {debug.build_player_name}")
    print(f"  player_load_radius_chunks: {debug.player_load_radius_chunks}")
    print(
        "  player_tp_window_length_blocks: "
        f"{debug.player_tp_window_length_blocks}"
    )
    print(
        "  player_tp_window_lateral_width_blocks: "
        f"{debug.player_tp_window_lateral_width_blocks}"
    )
    print(f"  total windows: {debug.total_windows}")
    print(f"  total commands: {debug.total_commands}")
    print(f"  max commands per part: {debug.max_commands_per_part}")
    print(f"  total parts: {debug.total_parts}")
    print(f"  wait ticks before build: {debug.wait_ticks_before_build}")
    print(f"  wait ticks after build: {debug.wait_ticks_after_build}")
    print(
        "  schedule_delay_ticks_between_parts: "
        f"{debug.schedule_delay_ticks_between_parts}"
    )
    print(
        "  estimated total build time: "
        f"{debug.estimated_total_build_ticks} ticks "
        f"({debug.estimated_total_build_ticks / 20:.1f}s)"
    )
    print("  windows:")
    for window in debug.windows:
        center = window.center_position
        window_box = window.bounding_box
        print(
            f"    window_{window.window_index:03d}: "
            f"center=({center.x},{center.y},{center.z}) "
            f"box=({window_box.min_x},{window_box.min_y},{window_box.min_z}) -> "
            f"({window_box.max_x},{window_box.max_y},{window_box.max_z}) "
            f"commands={window.command_count} parts={window.part_count}"
        )
    for warning in debug.warnings:
        print(f"  WARNING: {warning}")


def _format_position(position: BlockPosition) -> str:
    return f"({position.x},{position.y},{position.z})"


def _optional_position(
    x: int | None,
    y: int | None,
    z: int | None,
) -> BlockPosition | None:
    if x is None and y is None and z is None:
        return None
    if x is None or y is None or z is None:
        raise SystemExit("Custom button positions require X, Y, and Z.")
    return BlockPosition(x, y, z)


def _parse_center_split_overrides(values: list[str]) -> dict[int, str]:
    overrides: dict[int, str] = {}

    for value in values:
        if "=" not in value:
            raise SystemExit(
                "--center-split-override must use TRACK_ID=split or TRACK_ID=none"
            )
        raw_track_id, raw_action = value.split("=", 1)
        try:
            track_id = int(raw_track_id)
        except ValueError as exc:
            raise SystemExit(
                f"Invalid center split override track id: {raw_track_id!r}"
            ) from exc

        action = raw_action.strip().lower()
        if action not in {"split", "none"}:
            raise SystemExit(
                f"Invalid center split override for track {track_id}: {raw_action!r}"
            )
        overrides[track_id] = action

    return overrides
