import pytest

from nbs2func.core.minecraft_version import get_minecraft_version_profile
from nbs2func.core.models import Song
from nbs2func.core.tempo_control import (
    TempoControlError,
    build_tempo_control_report,
    display_bpm,
    format_tick_rate,
    target_minecraft_tps,
)


def _song(nbs_tempo_tps: float) -> Song:
    return Song(
        name="Tempo Song",
        author="Tester",
        length=1,
        tracks=(),
        nbs_tempo_tps=nbs_tempo_tps,
    )


def test_tempo_5_song_ticks_per_second_targets_20_tps() -> None:
    assert target_minecraft_tps(5) == 20


def test_tempo_10_song_ticks_per_second_targets_40_tps() -> None:
    assert target_minecraft_tps(10) == 40


def test_display_bpm_uses_nbs_tempo_ticks_per_second() -> None:
    assert display_bpm(10) == 150


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (20.00, "20"),
        (32.50, "32.5"),
        (33.33, "33.33"),
    ),
)
def test_tick_rate_formatting_trims_insignificant_zeros(
    value: float,
    expected: str,
) -> None:
    assert format_tick_rate(value, 2) == expected


@pytest.mark.parametrize(
    ("version", "expected_backend"),
    (
        ("1.16.5", "carpet"),
        ("1.20.1", "carpet"),
        ("1.21.1", "vanilla"),
    ),
)
def test_auto_backend_uses_version_profile(
    version: str,
    expected_backend: str,
) -> None:
    report = build_tempo_control_report(
        _song(10),
        minecraft_version_profile=get_minecraft_version_profile(version),
    )

    assert report.backend == expected_backend


@pytest.mark.parametrize("nbs_tempo_tps", (0.25, 2500.0))
def test_invalid_target_tick_rate_raises(nbs_tempo_tps: float) -> None:
    with pytest.raises(TempoControlError):
        build_tempo_control_report(
            _song(nbs_tempo_tps),
            minecraft_version_profile=get_minecraft_version_profile("1.16.5"),
        )
