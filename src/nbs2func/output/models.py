from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlacedBlock:
    """A final block placement in world coordinates."""

    x: int
    y: int
    z: int
    block: str
    nbt: str | None = None
    source: str = ""


@dataclass(frozen=True)
class GeneratedCommand:
    """A generated non-block command that remains part of mcfunction output."""

    command: str
    source: str = ""
    schem_supported: bool = False
    reason: str = ""


@dataclass(frozen=True)
class GeneratedComment:
    """A mcfunction comment preserved outside schematic block data."""

    text: str


GeneratedBuildItem = PlacedBlock | GeneratedCommand | GeneratedComment


@dataclass(frozen=True)
class GeneratedBuildSection:
    """An ordered group of generated items, preserving mcfunction batching."""

    items: tuple[GeneratedBuildItem, ...]
    comments: tuple[str, ...] = ()
    trailing_blank: bool = True


@dataclass(frozen=True)
class GeneratedBuildPlan:
    """Structured generated build data shared by output serializers."""

    blocks: tuple[PlacedBlock, ...]
    commands: tuple[GeneratedCommand, ...] = ()
    warnings: tuple[str, ...] = ()
    sections: tuple[GeneratedBuildSection, ...] = ()
