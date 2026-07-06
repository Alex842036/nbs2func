from __future__ import annotations

from dataclasses import dataclass

from .minecraft_version import MinecraftVersionProfile
from .models import Song


DEFAULT_GAME_TICKS_PER_SONG_TICK = 4
DEFAULT_MINECRAFT_TICK_RATE = 20.0
MIN_TARGET_TICK_RATE = 1.0
MAX_TARGET_TICK_RATE = 10000.0
HIGH_TARGET_TICK_RATE_WARNING = 200.0


class TempoControlError(ValueError):
    pass


@dataclass(frozen=True)
class TempoControlReport:
    nbs_tempo_tps: float
    display_bpm: float
    game_ticks_per_song_tick: int
    target_minecraft_tps: float
    backend: str
    backend_label: str
    command: str
    reset_command: str
    warnings: tuple[str, ...] = ()
    permission_hint: str = ""


def nbs_tempo_tps_from_song(song: Song) -> float:
    return song.nbs_tempo_tps


def target_minecraft_tps(
    nbs_tempo_tps: float,
    game_ticks_per_song_tick: int = DEFAULT_GAME_TICKS_PER_SONG_TICK,
) -> float:
    return nbs_tempo_tps * game_ticks_per_song_tick


def display_bpm(nbs_tempo_tps: float) -> float:
    return nbs_tempo_tps * 15


def resolve_tempo_backend(
    profile: MinecraftVersionProfile,
    requested_backend: str = "auto",
) -> str:
    if requested_backend == "auto":
        return profile.tempo_control_backend
    if requested_backend in {"carpet", "vanilla"}:
        return requested_backend
    raise TempoControlError(f"Unsupported tempo control backend: {requested_backend!r}")


def format_tick_rate(value: float, decimals: int = 2) -> str:
    decimals = max(0, decimals)
    formatted = f"{value:.{decimals}f}"
    if "." not in formatted:
        return formatted
    return formatted.rstrip("0").rstrip(".")


def tick_rate_command(value: float, decimals: int = 2) -> str:
    return f"tick rate {format_tick_rate(value, decimals)}"


def reset_tick_rate_command(decimals: int = 2) -> str:
    return tick_rate_command(DEFAULT_MINECRAFT_TICK_RATE, decimals)


def build_tempo_control_report(
    song: Song,
    *,
    minecraft_version_profile: MinecraftVersionProfile,
    backend: str = "auto",
    rate_decimals: int = 2,
    game_ticks_per_song_tick: int = DEFAULT_GAME_TICKS_PER_SONG_TICK,
) -> TempoControlReport:
    nbs_tempo_tps = nbs_tempo_tps_from_song(song)
    target_tps = target_minecraft_tps(
        nbs_tempo_tps,
        game_ticks_per_song_tick,
    )
    warnings = _validate_target_tick_rate(target_tps)
    resolved_backend = resolve_tempo_backend(minecraft_version_profile, backend)

    return TempoControlReport(
        nbs_tempo_tps=nbs_tempo_tps,
        display_bpm=display_bpm(nbs_tempo_tps),
        game_ticks_per_song_tick=game_ticks_per_song_tick,
        target_minecraft_tps=target_tps,
        backend=resolved_backend,
        backend_label=f"{resolved_backend} tick rate",
        command=tick_rate_command(target_tps, rate_decimals),
        reset_command=reset_tick_rate_command(rate_decimals),
        warnings=warnings,
        permission_hint=_permission_hint(resolved_backend),
    )


def tempo_report_lines(report: TempoControlReport) -> tuple[str, ...]:
    lines = [
        "Tempo control:",
        f"  NBS tempo: {_format_number(report.nbs_tempo_tps)} song ticks/s",
        f"  Estimated BPM: {_format_number(report.display_bpm)}",
        (
            "  Redstone timing: "
            f"{report.game_ticks_per_song_tick} game ticks per song tick"
        ),
        (
            "  Recommended Minecraft tick rate: "
            f"{_format_number(report.target_minecraft_tps)}"
        ),
        f"  Backend: {report.backend_label}",
        f"  Command: {report.command}",
        f"  Reset command: {report.reset_command}",
    ]
    for warning in report.warnings:
        lines.append(f"  WARNING: {warning}")
    if report.permission_hint:
        lines.append(f"  {report.permission_hint}")
    return tuple(lines)


def _validate_target_tick_rate(target_tps: float) -> tuple[str, ...]:
    if target_tps <= MIN_TARGET_TICK_RATE:
        raise TempoControlError(
            "Recommended Minecraft tick rate must be greater than "
            f"{MIN_TARGET_TICK_RATE}; got {target_tps}."
        )
    if target_tps >= MAX_TARGET_TICK_RATE:
        raise TempoControlError(
            "Recommended Minecraft tick rate must be less than "
            f"{MAX_TARGET_TICK_RATE}; got {target_tps}."
        )
    if target_tps > HIGH_TARGET_TICK_RATE_WARNING:
        return (
            "Recommended Minecraft tick rate is very high and may be unstable.",
        )
    return ()


def _permission_hint(backend: str) -> str:
    if backend == "carpet":
        return "This requires Carpet Mod and permission to run /tick rate."
    if backend == "vanilla":
        return (
            "Vanilla /tick requires elevated permissions and may not be "
            "available from command blocks/datapacks by default."
        )
    return ""


def _format_number(value: float) -> str:
    return format_tick_rate(value, 2)
