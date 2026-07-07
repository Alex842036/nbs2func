import unittest

from nbs2func.core.nbs_reader import _RawNote, _build_note_event


class NbsReaderPanTest(unittest.TestCase):
    def test_final_panning_uses_note_delta_plus_half_layer_delta(self) -> None:
        cases = (
            (100, 100, 100),
            (200, 100, 200),
            (100, 200, 150),
            (0, 100, 0),
            (100, 0, 50),
            (200, 200, 200),
            (0, 0, 0),
        )

        for note_pan, layer_pan, expected in cases:
            with self.subTest(note_pan=note_pan, layer_pan=layer_pan):
                note = _build_note_event(
                    _RawNote(
                        tick=0,
                        layer=0,
                        instrument=0,
                        key=45,
                        panning=note_pan,
                    ),
                    layer_volume=100,
                    layer_panning=layer_pan,
                )

                self.assertAlmostEqual(note.final_panning, expected)


if __name__ == "__main__":
    unittest.main()
