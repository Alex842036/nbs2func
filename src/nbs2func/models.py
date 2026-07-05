from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    """A note event in the project's internal song model."""

    tick: int
    layer: int
    instrument: int
    key: int
    velocity: int = 100
    panning: int = 100
    final_volume: float = 100.0
    final_panning: float = 100.0


@dataclass(frozen=True)
class Track:
    """A logical sequence of note events."""

    id: int
    name: str
    source_layer: int | None
    notes: tuple[NoteEvent, ...]
    volume: int = 100
    panning: int = 100


@dataclass(frozen=True)
class Song:
    """The internal representation used by importers and future exporters."""

    name: str
    author: str
    length: int
    tracks: tuple[Track, ...]
    nbs_tempo_tps: float = 10.0
