from dataclasses import replace

import pytest

from nbs2func.instrument_mapping import (
    INSTRUMENT_BLOCKS,
    INSTRUMENT_NOTE_BLOCK_INSTRUMENTS,
    validate_song_instruments_for_version,
)
from nbs2func.minecraft_version import (
    JAVA_1_16_5,
    JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
    JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
    JAVA_1_21_NOTE_BLOCK_BASE_BLOCKS,
    JAVA_1_21_NOTE_BLOCK_INSTRUMENTS,
    MinecraftVersionError,
    get_minecraft_version_profile,
)
from nbs2func.models import NoteEvent, Song, Track


def test_java_1_16_5_instrument_validation_accepts_current_mapping() -> None:
    song = Song(
        name="Supported",
        author="Tester",
        length=16,
        tracks=(
            Track(
                id=1,
                name="Layer 1",
                source_layer=1,
                notes=(
                    NoteEvent(tick=0, layer=1, instrument=0, key=45),
                    NoteEvent(tick=4, layer=1, instrument=15, key=45),
                ),
            ),
        ),
    )

    validate_song_instruments_for_version(
        song,
        get_minecraft_version_profile("1.16.5"),
    )


def test_target_profiles_support_expected_note_block_instrument_sets() -> None:
    expected_by_version = {
        "1.14.4": JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        "1.16.5": JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        "1.18.2": JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        "1.20.1": JAVA_1_14_NOTE_BLOCK_INSTRUMENTS,
        "1.21.1": JAVA_1_21_NOTE_BLOCK_INSTRUMENTS,
    }

    for version_id, expected in expected_by_version.items():
        profile = get_minecraft_version_profile(version_id)
        assert profile.supported_note_block_instruments == expected


def test_target_profiles_support_expected_base_block_sets() -> None:
    expected_by_version = {
        "1.14.4": JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
        "1.16.5": JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
        "1.18.2": JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
        "1.20.1": JAVA_1_14_NOTE_BLOCK_BASE_BLOCKS,
        "1.21.1": JAVA_1_21_NOTE_BLOCK_BASE_BLOCKS,
    }

    for version_id, expected in expected_by_version.items():
        profile = get_minecraft_version_profile(version_id)
        assert profile.supported_base_blocks == expected


def test_profile_instrument_names_match_current_mapping_names() -> None:
    legacy_instruments = {
        value
        for key, value in INSTRUMENT_NOTE_BLOCK_INSTRUMENTS.items()
        if key <= 15
    }
    all_instruments = frozenset(INSTRUMENT_NOTE_BLOCK_INSTRUMENTS.values())

    for version_id in ("1.14.4", "1.16.5", "1.18.2", "1.20.1"):
        profile = get_minecraft_version_profile(version_id)
        assert legacy_instruments <= profile.supported_note_block_instruments

    assert (
        all_instruments
        <= get_minecraft_version_profile("1.21.1").supported_note_block_instruments
    )


def test_profile_base_blocks_match_current_mapping_block_ids() -> None:
    legacy_blocks = {value for key, value in INSTRUMENT_BLOCKS.items() if key <= 15}
    all_blocks = frozenset(INSTRUMENT_BLOCKS.values())

    for version_id in ("1.14.4", "1.16.5", "1.18.2", "1.20.1"):
        profile = get_minecraft_version_profile(version_id)
        assert legacy_blocks <= profile.supported_base_blocks

    assert all_blocks <= get_minecraft_version_profile("1.21.1").supported_base_blocks


def test_instrument_validation_rejects_unsupported_mapping() -> None:
    song = Song(
        name="Unsupported",
        author="Tester",
        length=16,
        tracks=(
            Track(
                id=7,
                name="Copper",
                source_layer=3,
                notes=(NoteEvent(tick=9, layer=3, instrument=16, key=45),),
            ),
        ),
    )

    with pytest.raises(MinecraftVersionError) as exc_info:
        validate_song_instruments_for_version(
            song,
            get_minecraft_version_profile("1.16.5"),
        )

    message = str(exc_info.value)
    assert "1.16.5" in message
    assert "NBS instrument=16" in message
    assert "mapped Minecraft instrument=copper" in message
    assert "mapped base block=minecraft:copper_block" in message
    assert "first seen tick=9" in message
    assert "track=7" in message
    assert "layer=3" in message


def test_instrument_validation_rejects_fake_unsupported_instrument() -> None:
    song = Song(
        name="Unsupported Instrument",
        author="Tester",
        length=16,
        tracks=(
            Track(
                id=1,
                name="Layer 1",
                source_layer=1,
                notes=(NoteEvent(tick=2, layer=1, instrument=15, key=45),),
            ),
        ),
    )
    profile = replace(
        JAVA_1_16_5,
        supported_note_block_instruments=frozenset({"harp"}),
    )

    with pytest.raises(MinecraftVersionError) as exc_info:
        validate_song_instruments_for_version(song, profile)

    message = str(exc_info.value)
    assert "1.16.5" in message
    assert "mapped Minecraft instrument=pling" in message
    assert "mapped base block=minecraft:glowstone" in message


def test_instrument_validation_rejects_fake_unsupported_base_block() -> None:
    song = Song(
        name="Unsupported Base Block",
        author="Tester",
        length=16,
        tracks=(
            Track(
                id=1,
                name="Layer 1",
                source_layer=1,
                notes=(NoteEvent(tick=2, layer=1, instrument=15, key=45),),
            ),
        ),
    )
    profile = replace(
        JAVA_1_16_5,
        supported_base_blocks=frozenset({"minecraft:stone"}),
    )

    with pytest.raises(MinecraftVersionError) as exc_info:
        validate_song_instruments_for_version(song, profile)

    message = str(exc_info.value)
    assert "1.16.5" in message
    assert "mapped Minecraft instrument=pling" in message
    assert "mapped base block=minecraft:glowstone" in message
