from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class MinecraftVersionError(ValueError):
    pass


@dataclass(frozen=True)
class MinecraftVersionProfile:
    version_id: str
    pack_format: int
    min_build_y: int
    # Highest placeable block Y, inclusive. For example, 1.16.5 allows Y=255.
    max_build_y: int
    namespace: str
    function_dir_name: str
    function_tag_dir_name: str
    command_syntax_profile: str = "java_1_13_plus"
    datapack_layout_profile: str = "java_functions"
    supports_function_tags: bool = True
    supports_player_tp_build: bool = True
    supports_starter_module: bool = True
    supports_playback_assist: bool = True
    supports_minecart_playback_assist: bool = True
    tempo_control_backend: str = "carpet"
    mcschematic_version: str = "JE_1_16_5"
    supported_note_block_instruments: frozenset[str] = frozenset()
    supported_base_blocks: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()
    data_status: str = "verified"

    def __post_init__(self) -> None:
        if self.data_status not in {"verified", "needs_verification", "experimental"}:
            raise ValueError(
                f"Invalid Minecraft profile data_status: {self.data_status}"
            )
        if self.min_build_y > self.max_build_y:
            raise ValueError(
                f"Invalid Minecraft build height range for {self.version_id}: "
                f"{self.min_build_y}..{self.max_build_y}"
            )
        if self.tempo_control_backend not in {"carpet", "vanilla"}:
            raise ValueError(
                "Invalid Minecraft tempo_control_backend for "
                f"{self.version_id}: {self.tempo_control_backend}"
            )

    @property
    def version(self) -> str:
        """Compatibility alias for older callers."""

        return self.version_id


# Note block instrument names match instrument_mapping.INSTRUMENT_NOTE_BLOCK_INSTRUMENTS.
BASE_NOTE_BLOCK_INSTRUMENTS = frozenset(
    {
        "harp",
        "bass",
        "basedrum",
        "snare",
        "hat",
    }
)

JAVA_1_12_NOTE_BLOCK_INSTRUMENTS = frozenset(
    {
        *BASE_NOTE_BLOCK_INSTRUMENTS,
        "guitar",
        "flute",
        "bell",
        "chime",
        "xylophone",
    }
)

JAVA_1_14_NOTE_BLOCK_INSTRUMENTS = frozenset(
    {
        *JAVA_1_12_NOTE_BLOCK_INSTRUMENTS,
        "iron_xylophone",
        "cow_bell",
        "didgeridoo",
        "bit",
        "banjo",
        "pling",
    }
)

JAVA_1_21_NOTE_BLOCK_INSTRUMENTS = frozenset(
    {
        *JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        "copper",
        "exposed_copper",
        "weathered_copper",
        "oxidized_copper",
    }
)

JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS = frozenset(
    {
        "minecraft:dirt",
        "minecraft:oak_planks",
        "minecraft:stone",
        "minecraft:sand",
        "minecraft:glass",
        "minecraft:white_wool",
        "minecraft:clay",
        "minecraft:gold_block",
        "minecraft:packed_ice",
        "minecraft:bone_block",
        "minecraft:iron_block",
        "minecraft:soul_sand",
        "minecraft:pumpkin",
        "minecraft:emerald_block",
        "minecraft:hay_block",
        "minecraft:glowstone",
    }
)

JAVA_1_21_NOTE_BLOCK_BASE_BLOCKS = frozenset(
    {
        *JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
        "minecraft:copper_block",
        "minecraft:exposed_copper",
        "minecraft:weathered_copper",
        "minecraft:oxidized_copper",
    }
)


# Pack format values are centralized here and verified against Java Edition data
# pack format history; keep 1.16.5 at pack_format=6 to preserve existing output.
JAVA_1_16_5 = MinecraftVersionProfile(
    version_id="1.16.5",
    pack_format=6,
    min_build_y=0,
    max_build_y=255,
    namespace="nbs",
    function_dir_name="functions",
    function_tag_dir_name="functions",
    supported_note_block_instruments=JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
    supported_base_blocks=JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
)


SUPPORTED_VERSION_PROFILES: dict[str, MinecraftVersionProfile] = {
    "1.14.4": MinecraftVersionProfile(
        version_id="1.14.4",
        pack_format=4,
        min_build_y=0,
        max_build_y=255,
        namespace="nbs",
        function_dir_name="functions",
        function_tag_dir_name="functions",
        mcschematic_version="JE_1_14_4",
        supported_note_block_instruments=JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        supported_base_blocks=JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
    ),
    JAVA_1_16_5.version_id: JAVA_1_16_5,
    "1.18.2": MinecraftVersionProfile(
        version_id="1.18.2",
        pack_format=9,
        min_build_y=-64,
        max_build_y=319,
        namespace="nbs",
        function_dir_name="functions",
        function_tag_dir_name="functions",
        mcschematic_version="JE_1_18_2",
        supported_note_block_instruments=JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        supported_base_blocks=JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
    ),
    "1.20.1": MinecraftVersionProfile(
        version_id="1.20.1",
        pack_format=15,
        min_build_y=-64,
        max_build_y=319,
        namespace="nbs",
        function_dir_name="functions",
        function_tag_dir_name="functions",
        mcschematic_version="JE_1_20_1",
        supported_note_block_instruments=JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        supported_base_blocks=JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
    ),
    "1.21.1": MinecraftVersionProfile(
        version_id="1.21.1",
        pack_format=48,
        min_build_y=-64,
        max_build_y=319,
        namespace="nbs",
        function_dir_name="function",
        function_tag_dir_name="function",
        tempo_control_backend="vanilla",
        mcschematic_version="JE_1_21_1",
        supported_note_block_instruments=JAVA_1_21_NOTE_BLOCK_INSTRUMENTS,
        supported_base_blocks=JAVA_1_21_NOTE_BLOCK_BASE_BLOCKS,
    ),
}

# Aliases select one explicit profile and do not imply compatibility with an
# entire Minecraft minor-version series.
VERSION_ALIASES: dict[str, str] = {
    "1.14": "1.14.4",
    "1.14.x": "1.14.4",
    "1.16": "1.16.5",
    "1.16.x": "1.16.5",
    "1.18": "1.18.2",
    "1.18.x": "1.18.2",
    "1.20": "1.20.1",
    "1.21": "1.21.1",
}

DEFAULT_MINECRAFT_VERSION = JAVA_1_16_5.version_id
DEFAULT_MINECRAFT_VERSION_PROFILE = JAVA_1_16_5


def get_minecraft_version_profile(version: str | None) -> MinecraftVersionProfile:
    normalized = (version or "").strip()
    if not normalized:
        normalized = DEFAULT_MINECRAFT_VERSION

    profile = SUPPORTED_VERSION_PROFILES.get(normalized)
    if profile is not None:
        return _verified_profile(profile)

    alias_target = VERSION_ALIASES.get(normalized)
    if alias_target is not None:
        return _verified_profile(SUPPORTED_VERSION_PROFILES[alias_target])

    raise MinecraftVersionError(
        "Unsupported Minecraft Java version: "
        f"{version!r}. Supported exact profiles: "
        f"{', '.join(supported_minecraft_versions())}. "
        "Supported profile aliases: "
        f"{', '.join(supported_minecraft_version_aliases())}. "
        "Aliases select a specific profile and do not mean every patch version "
        "in that series is supported."
    )


def _verified_profile(profile: MinecraftVersionProfile) -> MinecraftVersionProfile:
    if profile.data_status == "verified":
        return profile

    raise MinecraftVersionError(
        "Minecraft Java "
        f"{profile.version_id} profile data is {profile.data_status}; "
        "this target version is not enabled for generation yet."
    )


def get_version_profile(version: str | None) -> MinecraftVersionProfile:
    return get_minecraft_version_profile(version)


def supported_minecraft_versions() -> tuple[str, ...]:
    return tuple(SUPPORTED_VERSION_PROFILES)


def supported_minecraft_version_aliases() -> tuple[str, ...]:
    return tuple(VERSION_ALIASES)


def write_pack_mcmeta(
    datapack_root: Path,
    profile: MinecraftVersionProfile | None = None,
    description: str | None = None,
) -> None:
    version_profile = profile or DEFAULT_MINECRAFT_VERSION_PROFILE
    datapack_root.mkdir(parents=True, exist_ok=True)
    pack_description = (
        description
        if description is not None
        else f"Generated by nbs2func for Minecraft Java {version_profile.version_id}"
    )
    data = {
        "pack": {
            "pack_format": version_profile.pack_format,
            "description": pack_description,
        }
    }
    (datapack_root / "pack.mcmeta").write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
