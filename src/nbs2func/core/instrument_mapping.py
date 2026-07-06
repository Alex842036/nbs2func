from __future__ import annotations

from typing import Final

from .minecraft_version import MinecraftVersionError, MinecraftVersionProfile
from .models import Song

DEFAULT_INSTRUMENT_BLOCK: Final = "minecraft:stone"

GRAVITY_BLOCKS: Final[set[str]] = {
    "minecraft:sand",
    "minecraft:red_sand",
    "minecraft:gravel",
    "minecraft:white_concrete_powder",
    "minecraft:orange_concrete_powder",
    "minecraft:magenta_concrete_powder",
    "minecraft:light_blue_concrete_powder",
    "minecraft:yellow_concrete_powder",
    "minecraft:lime_concrete_powder",
    "minecraft:pink_concrete_powder",
    "minecraft:gray_concrete_powder",
    "minecraft:light_gray_concrete_powder",
    "minecraft:cyan_concrete_powder",
    "minecraft:purple_concrete_powder",
    "minecraft:blue_concrete_powder",
    "minecraft:brown_concrete_powder",
    "minecraft:green_concrete_powder",
    "minecraft:red_concrete_powder",
    "minecraft:black_concrete_powder",
}

# Default Open Note Block Studio / Minecraft note block instrument order.
# Values are Java Edition block ids for the block placed below the note block.
INSTRUMENT_BLOCKS: Final[dict[int, str]] = {
    0: "minecraft:dirt",  # harp / piano
    1: "minecraft:oak_planks",  # double bass / bass
    2: "minecraft:stone",  # bass drum / basedrum
    3: "minecraft:sand",  # snare drum / snare
    4: "minecraft:glass",  # click / hi-hat
    5: "minecraft:white_wool",  # guitar
    6: "minecraft:clay",  # flute
    7: "minecraft:gold_block",  # bell
    8: "minecraft:packed_ice",  # chime
    9: "minecraft:bone_block",  # xylophone
    10: "minecraft:iron_block",  # iron xylophone
    11: "minecraft:soul_sand",  # cow bell
    12: "minecraft:pumpkin",  # didgeridoo
    13: "minecraft:emerald_block",  # bit
    14: "minecraft:hay_block",  # banjo
    15: "minecraft:glowstone",  # pling
    16: "minecraft:copper_block",  # copper
    17: "minecraft:exposed_copper",  # exposed copper
    18: "minecraft:weathered_copper",  # weathered copper
    19: "minecraft:oxidized_copper",  # oxidized copper
}

INSTRUMENT_NOTE_BLOCK_INSTRUMENTS: Final[dict[int, str]] = {
    0: "harp",
    1: "bass",
    2: "basedrum",
    3: "snare",
    4: "hat",
    5: "guitar",
    6: "flute",
    7: "bell",
    8: "chime",
    9: "xylophone",
    10: "iron_xylophone",
    11: "cow_bell",
    12: "didgeridoo",
    13: "bit",
    14: "banjo",
    15: "pling",
    16: "copper",
    17: "exposed_copper",
    18: "weathered_copper",
    19: "oxidized_copper",
}

INSTRUMENT_NAME_ALIASES: Final[dict[str, int]] = {
    "harp": 0,
    "piano": 0,
    "bass": 1,
    "double_bass": 1,
    "basedrum": 2,
    "bass_drum": 2,
    "snare": 3,
    "snare_drum": 3,
    "hat": 4,
    "hi_hat": 4,
    "click": 4,
    "guitar": 5,
    "flute": 6,
    "bell": 7,
    "chime": 8,
    "xylophone": 9,
    "iron_xylophone": 10,
    "cow_bell": 11,
    "didgeridoo": 12,
    "bit": 13,
    "banjo": 14,
    "pling": 15,
    "copper": 16,
    "copper_block": 16,
    "exposed_copper": 17,
    "weathered_copper": 18,
    "oxidized_copper": 19,
}


def get_instrument_block(instrument: int | str) -> str:
    instrument_id = _normalize_instrument(instrument)
    if instrument_id is None:
        return DEFAULT_INSTRUMENT_BLOCK

    return INSTRUMENT_BLOCKS.get(instrument_id, DEFAULT_INSTRUMENT_BLOCK)


def has_instrument_mapping(instrument: int | str) -> bool:
    instrument_id = _normalize_instrument(instrument)
    return instrument_id in INSTRUMENT_BLOCKS if instrument_id is not None else False


def get_note_block_instrument(instrument: int | str) -> str | None:
    instrument_id = _normalize_instrument(instrument)
    if instrument_id is None:
        return None

    return INSTRUMENT_NOTE_BLOCK_INSTRUMENTS.get(instrument_id)


def validate_song_instruments_for_version(
    song: Song,
    profile: MinecraftVersionProfile,
) -> None:
    if (
        not profile.supported_note_block_instruments
        or not profile.supported_base_blocks
    ):
        raise MinecraftVersionError(
            "Minecraft Java "
            f"{profile.version_id} profile is missing instrument compatibility "
            "data. Cannot safely generate output for this target version."
        )

    for track in song.tracks:
        for note in track.notes:
            minecraft_instrument = get_note_block_instrument(note.instrument)
            base_block = get_instrument_block(note.instrument)
            if minecraft_instrument is None:
                raise MinecraftVersionError(
                    "Unsupported NBS instrument for Minecraft Java "
                    f"{profile.version_id}: instrument={note.instrument!r}, "
                    f"mapped Minecraft instrument=<unknown>, "
                    f"mapped base block={base_block}, first seen tick={note.tick}, "
                    f"track={track.id}, layer={note.layer}. "
                    "Use a supported instrument, edit the NBS file, or choose a "
                    "target version/profile that supports this mapping."
                )
            if minecraft_instrument not in profile.supported_note_block_instruments:
                raise MinecraftVersionError(
                    "Unsupported note block instrument for Minecraft Java "
                    f"{profile.version_id}: NBS instrument={note.instrument!r}, "
                    f"mapped Minecraft instrument={minecraft_instrument}, "
                    f"mapped base block={base_block}, first seen tick={note.tick}, "
                    f"track={track.id}, layer={note.layer}. "
                    "Use a supported instrument, edit the NBS file, or choose a "
                    "higher/supported target version."
                )
            if base_block not in profile.supported_base_blocks:
                raise MinecraftVersionError(
                    "Unsupported note block base block for Minecraft Java "
                    f"{profile.version_id}: NBS instrument={note.instrument!r}, "
                    f"mapped Minecraft instrument={minecraft_instrument}, "
                    f"mapped base block={base_block}, first seen tick={note.tick}, "
                    f"track={track.id}, layer={note.layer}. "
                    "Use a supported instrument, edit the NBS file, or choose a "
                    "higher/supported target version."
                )


def is_gravity_block(block_id: str) -> bool:
    return _normalize_block_id(block_id) in GRAVITY_BLOCKS


def get_required_support_block(
    instrument_block: str,
    support_block: str = DEFAULT_INSTRUMENT_BLOCK,
) -> str | None:
    if not is_gravity_block(instrument_block):
        return None

    return _normalize_block_id(support_block)


def _normalize_instrument(instrument: int | str) -> int | None:
    if isinstance(instrument, int):
        return instrument

    normalized = instrument.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized.isdigit():
        return int(normalized)

    return INSTRUMENT_NAME_ALIASES.get(normalized)


def _normalize_block_id(block_id: str) -> str:
    if block_id.startswith("minecraft:"):
        return block_id
    return f"minecraft:{block_id}"
