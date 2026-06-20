import pytest

from nbs2func.instrument_mapping import validate_song_instruments_for_version
from nbs2func.minecraft_version import (
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
