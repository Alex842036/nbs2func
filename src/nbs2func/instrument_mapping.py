from __future__ import annotations

from typing import Final

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
