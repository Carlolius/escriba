"""Voiceprints (speaker embeddings) with numpy only.

It's resemblyzer's VoiceEncoder (Apache-2.0, https://github.com/resemble-ai/Resemblyzer)
rewritten without torch or librosa: the same pretrained weights
(models/voice_encoder.npz, exported with tools/export_voice_encoder.py), the
same mel spectrogram and the same 3-layer LSTM. The embeddings match
resemblyzer's, so libraries made with it keep working. Removes ~1 GB of
dependencies (torch, librosa, scipy, numba).
"""
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 16000
N_FFT = 400            # 25 ms window
HOP = 160              # 10 ms step
PARTIAL_FRAMES = 160   # 1.6 s per partial utterance
LAYERS = 3
WEIGHTS = Path(__file__).resolve().parent / "models" / "voice_encoder.npz"


@lru_cache(maxsize=1)
def _weights():
    with np.load(WEIGHTS) as w:
        return {k: w[k] for k in w.files}


def mel_spectrogram(wav):
    """(frames, 40) power mel spectrogram, like librosa.feature.melspectrogram
    with center=True and zero padding."""
    wav = np.asarray(wav, dtype=np.float32)
    padded = np.pad(wav, N_FFT // 2)
    n = 1 + (len(padded) - N_FFT) // HOP
    frames = np.lib.stride_tricks.as_strided(
        padded, shape=(n, N_FFT), strides=(padded.strides[0] * HOP, padded.strides[0]))
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)  # periodic Hann
    power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    return (power @ _weights()["mel_basis"].T).astype(np.float32)


def _sigmoid(x):
    return 0.5 * (1 + np.tanh(0.5 * x))  # = 1 / (1 + e^-x), without overflow


def _forward(mels):
    """(batch, frames, 40) -> (batch, 256) L2-normalized embeddings."""
    w = _weights()
    x = mels
    for layer in range(LAYERS):
        w_ih, w_hh = w[f"lstm_weight_ih_l{layer}"], w[f"lstm_weight_hh_l{layer}"]
        bias = w[f"lstm_bias_ih_l{layer}"] + w[f"lstm_bias_hh_l{layer}"]
        inputs = x @ w_ih.T + bias   # every time step at once
        batch, steps, _ = inputs.shape
        hidden = w_hh.shape[1]
        h = np.zeros((batch, hidden), np.float32)
        c = np.zeros((batch, hidden), np.float32)
        outputs = np.empty((batch, steps, hidden), np.float32)
        for t in range(steps):
            gates = inputs[:, t] + h @ w_hh.T
            i, f, g, o = np.split(gates, 4, axis=1)  # PyTorch's gate order
            c = _sigmoid(f) * c + _sigmoid(i) * np.tanh(g)
            h = _sigmoid(o) * np.tanh(c)
            outputs[:, t] = h
        x = outputs
    raw = np.maximum(h @ w["linear_weight"].T + w["linear_bias"], 0)
    return raw / np.linalg.norm(raw, axis=1, keepdims=True)


def _partial_slices(n_samples, rate=1.3, min_coverage=0.75):
    n_frames = int(np.ceil((n_samples + 1) / HOP))
    step = int(np.round((SR / rate) / HOP))
    starts = list(range(0, max(1, n_frames - PARTIAL_FRAMES + step + 1), step))
    last = starts[-1] * HOP
    coverage = (n_samples - last) / (PARTIAL_FRAMES * HOP)
    if coverage < min_coverage and len(starts) > 1:
        starts.pop()
    return starts


def to_16k_mono(wav, sr):
    """Mixes channels down and resamples to 16 kHz (in the frequency domain:
    no aliasing, and it's only used on clips of a few seconds)."""
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr == SR or len(wav) == 0:
        return wav
    n = max(1, int(round(len(wav) * SR / sr)))
    spectrum = np.fft.rfft(wav)
    kept = np.zeros(n // 2 + 1, dtype=spectrum.dtype)
    k = min(len(kept), len(spectrum))
    kept[:k] = spectrum[:k]
    return (np.fft.irfft(kept, n) * (n / len(wav))).astype(np.float32)


def embed(wav, sr=SR):
    """Embedding (256 floats, L2-normalized) of an utterance (any rate, mono
    or not): the average of overlapping 1.6 s pieces, like
    VoiceEncoder.embed_utterance."""
    wav = to_16k_mono(wav, sr)
    starts = _partial_slices(len(wav))
    needed = (starts[-1] + PARTIAL_FRAMES) * HOP
    if needed >= len(wav):
        wav = np.pad(wav, (0, needed - len(wav)))
    mel = mel_spectrogram(wav)
    mels = np.stack([mel[s:s + PARTIAL_FRAMES] for s in starts])
    raw = _forward(mels).mean(axis=0)
    return raw / np.linalg.norm(raw)
