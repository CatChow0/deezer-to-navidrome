"""The tempo of a track, measured from its audio, since almost no file carries it
in its tags. Read only: a file is never changed.

Beats show up as sudden rises in the spectrum (spectral flux), and the delay at
which that signal best repeats gives the tempo. The result may land on half or
double the real tempo, as with any such method: tempo_distance treats those as
the same tempo."""
import io
import logging
import math

logger = logging.getLogger(__name__)

SAMPLE_RATE = 22050
FRAME = 1024
HOP = 256
MIN_BPM, MAX_BPM = 50, 220
PREFERRED_BPM = 120
EXCERPT_SECONDS = 60
MIN_SECONDS = 8


def _libraries():
    """Imported on demand: only analysis needs them, not the rest of the app."""
    import numpy
    import soundfile

    return numpy, soundfile


def estimate(samples, rate):
    """Beats per minute of a mono signal, or None when it has no usable pulse."""
    np, _ = _libraries()
    samples = np.asarray(samples, dtype="float32")
    if len(samples) < MIN_SECONDS * rate or not np.any(np.abs(samples) > 1e-4):
        return None
    if rate != SAMPLE_RATE:
        positions = np.arange(0, len(samples), rate / SAMPLE_RATE)
        samples = np.interp(positions, np.arange(len(samples)), samples).astype("float32")
    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME)[::HOP] * np.hanning(FRAME)
    spectrum = np.log1p(10 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(spectrum, axis=0)).sum(axis=1)
    flux = np.maximum(flux - np.convolve(flux, np.ones(32) / 32, mode="same"), 0)
    repeats = np.fft.irfft(np.abs(np.fft.rfft(flux, 2 * len(flux))) ** 2)[: len(flux)]
    if repeats[0] <= 0:
        return None
    frames_per_second = SAMPLE_RATE / HOP
    lags = np.arange(int(frames_per_second * 60 / MAX_BPM), int(frames_per_second * 60 / MIN_BPM))
    bpm = 60 * frames_per_second / lags
    preference = np.exp(-0.5 * (np.log2(bpm / PREFERRED_BPM) / 0.9) ** 2)
    return round(float(bpm[np.argmax(repeats[lags] / repeats[0] * preference)]), 1)


def _read(source):
    np, soundfile = _libraries()
    with soundfile.SoundFile(source) as audio:
        wanted = EXCERPT_SECONDS * audio.samplerate
        # The middle of a song, not its intro.
        if audio.seekable() and len(audio) > wanted:
            audio.seek((len(audio) - wanted) // 2)
        samples = audio.read(wanted, dtype="float32", always_2d=True)
        return samples.mean(axis=1), audio.samplerate


def file_tempo(path):
    """Tempo of an audio file; None when it cannot be read or has no pulse."""
    try:
        return estimate(*_read(str(path)))
    except Exception as e:
        logger.info("No tempo for %s: %s", path, e)
        return None


def data_tempo(data):
    """Tempo of audio held in memory, such as a Deezer preview."""
    # The audio library refuses the empty tag Deezer previews start with.
    if data[:3] == b"ID3":
        start = data.find(b"\xff\xfb")
        data = data[start:] if start > 0 else data
    try:
        return estimate(*_read(io.BytesIO(data)))
    except Exception as e:
        logger.info("No tempo for a preview: %s", e)
        return None


def tempo_distance(a, b) -> float:
    """How far apart two tempos are, in octaves; half and double count as equal."""
    gap = abs(math.log2(a / b)) % 1
    return min(gap, 1 - gap)


def tempo_fit(bpm, seeds, width=0.07):
    """From 0 to 1, how well a tempo sits among weighted (bpm, weight) seeds, or
    None when either is unknown. Each seed counts by its weight instead of being
    averaged, so a few rarely played tracks that stand out barely matter, and two
    distinct tempos stay two."""
    known = [(tempo, weight) for tempo, weight in seeds if tempo and weight > 0]
    if not bpm or not known:
        return None
    total = sum(weight for _, weight in known)
    return sum(
        weight * math.exp(-0.5 * (tempo_distance(bpm, tempo) / width) ** 2) for tempo, weight in known
    ) / total
