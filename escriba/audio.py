"""Audio utilities without ffmpeg: duration, Opus compression and playback.

soundfile (libsndfile) reads and writes WAV, FLAC and Ogg/Opus on Linux,
Windows and macOS without installing anything else, and soundcard plays through
the system speaker. So the program doesn't need ffmpeg.
"""
from pathlib import Path

import numpy as np
import soundfile as sf

from .progress import Progress

# libsndfile compression_level for Opus. Not linear: measured on a real
# meeting at 16 kHz, 0.84 gives ~21 kbps and 0.89 ~16 kbps. Voiceprints come
# out the same (similarity > 0.999 against the WAV).
ARCHIVE_LEVEL = 0.89
UPLOAD_LEVEL = 0.84
OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
BLOCK_S = 10


def duration(path):
    try:
        return sf.info(str(path)).duration
    except Exception:
        return None


def _to_mono(block):
    return block.mean(axis=1) if block.ndim > 1 else block


def _resample(block, sr_from, sr_to):
    """Linear interpolation: good enough for voice, and no scipy needed."""
    n = int(round(len(block) * sr_to / sr_from))
    if n == 0:
        return block[:0]
    x = np.linspace(0, len(block) - 1, n)
    return np.interp(x, np.arange(len(block)), block).astype("float32")


def compress_opus(source, target, level=ARCHIVE_LEVEL):
    """Any audio soundfile can read -> mono Ogg/Opus, with a progress bar."""
    with sf.SoundFile(str(source)) as reader:
        sr = reader.samplerate
        sr_out = sr if sr in OPUS_RATES else 16000
        total = reader.frames / sr
        progress = Progress()
        try:
            with sf.SoundFile(str(target), "w", samplerate=sr_out, channels=1, format="OGG",
                              subtype="OPUS", compression_level=level) as writer:
                done = 0.0
                for block in reader.blocks(blocksize=sr * BLOCK_S, dtype="float32", always_2d=True):
                    block = _to_mono(block)
                    if sr_out != sr:
                        block = _resample(block, sr, sr_out)
                    writer.write(block)
                    done += BLOCK_S
                    progress.update("compress", min(done, total), total)
            progress.update("compress", total, total)
        finally:
            progress.close()


def read_clip(path, start, end):
    """(mono float32 samples, sample rate) between start and end, in seconds."""
    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        first = max(0, int(start * sr))
        if first >= f.frames or end <= start:  # outside the audio: nothing
            return np.zeros(0, dtype="float32"), sr
        f.seek(first)
        data = f.read(int((end - start) * sr), dtype="float32", always_2d=True)
    return _to_mono(data), sr


def play(path, start, end):
    """Plays a clip through the default speaker. Blocks until it ends; Ctrl+C
    stops it (it plays in chunks so the stop is immediate)."""
    import soundcard as sc

    data, sr = read_clip(Path(path), start, end)
    chunk = sr // 4
    with sc.default_speaker().player(samplerate=sr, channels=1) as player:
        for i in range(0, len(data), chunk):
            player.play(data[i:i + chunk])
