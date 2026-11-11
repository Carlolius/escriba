"""Exports resemblyzer's pretrained voice encoder (Apache-2.0,
https://github.com/resemble-ai/Resemblyzer) to escriba/models/voice_encoder.npz,
so escriba can compute the same voiceprints with numpy only, without torch.

Run once, with resemblyzer and librosa installed (not needed by escriba):

    uv run --no-project --with resemblyzer --with librosa python tools/export_voice_encoder.py

--help shows this text.
"""
import sys
from pathlib import Path

if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__)
    sys.exit(0)

import librosa
import numpy as np
import resemblyzer
import torch

weights = torch.load(Path(resemblyzer.__file__).parent / "pretrained.pt", map_location="cpu")["model_state"]
arrays = {k.replace(".", "_"): v.numpy().astype(np.float32) for k, v in weights.items()
          if k.startswith(("lstm.", "linear."))}
# The mel filter bank resemblyzer gets from librosa (16 kHz, 25 ms window, 40 bands)
arrays["mel_basis"] = librosa.filters.mel(sr=16000, n_fft=400, n_mels=40).astype(np.float32)
target = Path(__file__).resolve().parent.parent / "escriba" / "models" / "voice_encoder.npz"
np.savez_compressed(target, **arrays)
print(target, f"{target.stat().st_size / 1e6:.1f} MB", sorted(arrays))
