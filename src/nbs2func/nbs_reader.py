from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .models import NoteEvent, Song, Track


class NbsFormatError(ValueError):
    """Raised when an NBS file cannot be parsed."""


@dataclass(frozen=True)
class _LayerMetadata:
    name: str
    volume: int = 100
    panning: int = 100


@dataclass(frozen=True)
class _RawNote:
    tick: int
    layer: int
    instrument: int
    key: int
    velocity: int = 100
    panning: int = 100


class _Reader:
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def byte(self) -> int:
        return self._unpack("<B", 1)

    def short(self) -> int:
        return self._unpack("<h", 2)

    def unsigned_short(self) -> int:
        return self._unpack("<H", 2)

    def int(self) -> int:
        return self._unpack("<i", 4)

    def string(self) -> str:
        length = self.int()
        if length < 0:
            raise NbsFormatError(f"Invalid string length: {length}")

        data = self._stream.read(length)
        if len(data) != length:
            raise NbsFormatError("Unexpected end of file while reading string")

        return data.decode("utf-8", errors="replace")

    def skip(self, size: int) -> None:
        data = self._stream.read(size)
        if len(data) != size:
            raise NbsFormatError("Unexpected end of file while skipping bytes")

    def _unpack(self, fmt: str, size: int) -> int:
        data = self._stream.read(size)
        if len(data) != size:
            raise NbsFormatError("Unexpected end of file")
        return struct.unpack(fmt, data)[0]


def read_nbs(path: str | Path) -> Song:
    """Read a Note Block Studio .nbs file into the project song model."""

    file_path = Path(path)
    with file_path.open("rb") as stream:
        reader = _Reader(stream)
        version, song_length, layer_count = _read_version_and_size(reader)
        name, author = _read_header_metadata(reader, version)
        notes_by_layer = _read_notes_by_layer(reader, version)
        layer_metadata = _read_layer_metadata(reader, version, layer_count)

    return Song(
        name=name,
        author=author,
        length=song_length,
        tracks=_build_tracks(notes_by_layer, layer_metadata, layer_count),
    )


def _read_version_and_size(reader: _Reader) -> tuple[int, int, int]:
    first_length = reader.unsigned_short()

    if first_length == 0:
        version = reader.byte()
        reader.byte()  # Vanilla instrument count.
        song_length = reader.unsigned_short()
    else:
        version = 0
        song_length = first_length

    layer_count = reader.unsigned_short()
    return version, song_length, layer_count


def _read_header_metadata(reader: _Reader, version: int) -> tuple[str, str]:
    name = reader.string()
    author = reader.string()
    reader.string()  # Original author.
    reader.string()  # Description.

    reader.unsigned_short()  # Tempo, stored as ticks per second * 100.
    reader.byte()  # Auto-save enabled.
    reader.byte()  # Auto-save duration.
    reader.byte()  # Time signature.
    reader.int()  # Minutes spent.
    reader.int()  # Left clicks.
    reader.int()  # Right clicks.
    reader.int()  # Note blocks added.
    reader.int()  # Note blocks removed.
    reader.string()  # MIDI/schematic file name.

    if version >= 4:
        reader.byte()  # Loop enabled.
        reader.byte()  # Max loop count.
        reader.unsigned_short()  # Loop start tick.

    return name, author


def _read_notes_by_layer(reader: _Reader, version: int) -> dict[int, list[_RawNote]]:
    notes_by_layer: dict[int, list[_RawNote]] = {}
    tick = -1

    while True:
        tick_jump = reader.unsigned_short()
        if tick_jump == 0:
            break

        tick += tick_jump
        layer = -1

        while True:
            layer_jump = reader.unsigned_short()
            if layer_jump == 0:
                break

            layer += layer_jump
            instrument = reader.byte()
            key = reader.byte()
            velocity = 100
            panning = 100

            if version >= 4:
                velocity = reader.byte()
                panning = reader.byte()
                reader.short()  # Pitch.

            notes_by_layer.setdefault(layer, []).append(
                _RawNote(
                    tick=tick,
                    layer=layer,
                    instrument=instrument,
                    key=key,
                    velocity=velocity,
                    panning=panning,
                )
            )

    return notes_by_layer


def _read_layer_metadata(
    reader: _Reader,
    version: int,
    layer_count: int,
) -> dict[int, _LayerMetadata]:
    layer_metadata: dict[int, _LayerMetadata] = {}

    for layer in range(layer_count):
        try:
            name = reader.string()
            if version >= 4:
                reader.byte()  # Lock flag.
            volume = reader.byte()
            panning = 100

            if version >= 2:
                panning = reader.byte()

            layer_metadata[layer] = _LayerMetadata(
                name=name,
                volume=volume,
                panning=panning,
            )
        except NbsFormatError:
            break

    return layer_metadata


def _build_tracks(
    notes_by_layer: dict[int, list[_RawNote]],
    layer_metadata: dict[int, _LayerMetadata],
    layer_count: int,
) -> tuple[Track, ...]:
    track_ids = sorted(set(range(layer_count)) | set(notes_by_layer))

    return tuple(
        _build_track(layer, notes_by_layer.get(layer, ()), layer_metadata.get(layer))
        for layer in track_ids
    )


def _build_track(
    layer: int,
    raw_notes: list[_RawNote] | tuple[_RawNote, ...],
    metadata: _LayerMetadata | None,
) -> Track:
    layer_volume = metadata.volume if metadata else 100
    layer_panning = metadata.panning if metadata else 100

    return Track(
        id=layer,
        name=metadata.name if metadata and metadata.name else f"Layer {layer}",
        source_layer=layer,
        notes=tuple(
            _build_note_event(note, layer_volume, layer_panning)
            for note in raw_notes
        ),
        volume=layer_volume,
        panning=layer_panning,
    )


def _build_note_event(
    raw_note: _RawNote,
    layer_volume: int,
    layer_panning: int,
) -> NoteEvent:
    final_volume = layer_volume * raw_note.velocity / 100
    final_panning = _final_panning(
        note_panning=raw_note.panning,
        layer_panning=layer_panning,
    )

    return NoteEvent(
        tick=raw_note.tick,
        layer=raw_note.layer,
        instrument=raw_note.instrument,
        key=raw_note.key,
        velocity=raw_note.velocity,
        panning=raw_note.panning,
        final_volume=final_volume,
        final_panning=final_panning,
    )


def _final_panning(note_panning: int = 100, layer_panning: int = 100) -> float:
    note_delta = note_panning - 100
    layer_delta = (layer_panning - 100) * 0.5
    final_delta = max(-100, min(100, note_delta + layer_delta))
    return 100 + final_delta
