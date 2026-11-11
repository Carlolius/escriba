"""The numpy voice encoder must give the same embeddings as resemblyzer (the
reference was computed with resemblyzer's VoiceEncoder, see
tools/export_voice_encoder.py), or existing voice libraries would stop matching."""
from pathlib import Path

import numpy as np

from escriba import encoder

REFERENCE = Path(__file__).parent / "data" / "encoder_reference.npy"


def _signal(n=48000):
    t = np.arange(n) / 16000
    return (0.1 * np.sin(2 * np.pi * (150 + 200 * t) * t) * np.sin(2 * np.pi * 3 * t)).astype("float32")


def test_same_as_resemblyzer():
    emb = encoder.embed(_signal())
    assert emb.shape == (256,)
    assert float(emb @ np.load(REFERENCE)) > 0.99999


def test_short_and_silent_audio():
    for wav in (_signal(800), np.zeros(16000, dtype="float32") + 1e-6):
        emb = encoder.embed(wav)
        assert emb.shape == (256,) and abs(float(np.linalg.norm(emb)) - 1) < 1e-5
