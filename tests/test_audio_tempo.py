import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from core import audio_tempo as tempo

RATE = 22050


def clicks(bpm, seconds=30, rate=RATE):
    samples = np.zeros(int(seconds * rate), dtype="float32")
    rng = np.random.default_rng(1)
    step = int(rate * 60 / bpm)
    for start in range(0, len(samples) - 400, step):
        samples[start:start + 400] += rng.normal(0, 0.6, 400).astype("float32") * np.exp(-np.arange(400) / 80)
    return samples


class Estimate(unittest.TestCase):
    def assertSameTempo(self, found, bpm):
        self.assertIsNotNone(found)
        self.assertLess(tempo.tempo_distance(found, bpm), 0.04, (found, bpm))

    def test_finds_the_tempo_of_a_pulse(self):
        for bpm in (84, 110, 128, 150, 175):
            self.assertSameTempo(tempo.estimate(clicks(bpm), RATE), bpm)

    def test_other_sample_rates(self):
        self.assertSameTempo(tempo.estimate(clicks(120, rate=44100), 44100), 120)

    def test_silence_has_no_tempo(self):
        self.assertIsNone(tempo.estimate(np.zeros(RATE * 30), RATE))

    def test_too_short_has_no_tempo(self):
        self.assertIsNone(tempo.estimate(clicks(120, seconds=3), RATE))


class Sources(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_reads_a_file_without_changing_it(self):
        path = self.folder / "song.flac"
        sf.write(path, clicks(128, seconds=90), RATE)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertLess(tempo.tempo_distance(tempo.file_tempo(path), 128), 0.04)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_unreadable_file_has_no_tempo(self):
        path = self.folder / "broken.flac"
        path.write_bytes(b"not audio at all")
        self.assertIsNone(tempo.file_tempo(path))

    def test_missing_file_has_no_tempo(self):
        self.assertIsNone(tempo.file_tempo(self.folder / "gone.flac"))

    def test_garbage_data_has_no_tempo(self):
        self.assertIsNone(tempo.data_tempo(b"ID3\x04\x00\x00\x00\x00\x00\x00nothing"))


class Distance(unittest.TestCase):
    def test_half_and_double_are_the_same_tempo(self):
        self.assertAlmostEqual(tempo.tempo_distance(90, 180), 0)
        self.assertAlmostEqual(tempo.tempo_distance(160, 80), 0)

    def test_different_tempos_are_apart(self):
        self.assertGreater(tempo.tempo_distance(100, 130), 0.3)


class Fit(unittest.TestCase):
    def test_close_tempo_fits_and_a_far_one_does_not(self):
        seeds = [(120, 1)]
        self.assertGreater(tempo.tempo_fit(122, seeds), 0.9)
        self.assertLess(tempo.tempo_fit(150, seeds), 0.1)

    def test_a_rarely_played_outlier_barely_counts(self):
        # An album mostly at 100, with one rarely played track at 140: the mean
        # (about 102) is not what counts, and 140 stays a poor fit.
        seeds = [(100, 50), (100, 40), (140, 1)]
        self.assertGreater(tempo.tempo_fit(100, seeds), 0.9)
        self.assertLess(tempo.tempo_fit(140, seeds), 0.1)

    def test_two_tempos_stay_two_instead_of_their_mean(self):
        seeds = [(90, 10), (130, 10)]
        self.assertGreater(tempo.tempo_fit(90, seeds), 0.4)
        self.assertGreater(tempo.tempo_fit(130, seeds), 0.4)
        self.assertLess(tempo.tempo_fit(110, seeds), 0.1)

    def test_unknown_tempo_gives_no_answer(self):
        self.assertIsNone(tempo.tempo_fit(None, [(120, 1)]))
        self.assertIsNone(tempo.tempo_fit(120, [(None, 1)]))
        self.assertIsNone(tempo.tempo_fit(120, []))


if __name__ == "__main__":
    unittest.main()
