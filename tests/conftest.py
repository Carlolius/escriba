import json

import numpy as np
import pytest
import soundfile as sf

from escriba import i18n


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    """Each test with its own data folder, no keys from the environment, in English."""
    folder = tmp_path / "data"
    monkeypatch.setenv("ESCRIBA_DATA", str(folder))
    for key in ("ASSEMBLYAI_API_KEY", "HF_TOKEN", "ESCRIBA_LANG"):
        monkeypatch.delenv(key, raising=False)
    i18n.set_language("en")
    return folder


@pytest.fixture
def wav(tmp_path):
    """Creates a 16 kHz mono WAV with soft noise; returns its path."""
    def create(name="meeting.wav", seconds=5.0, folder=None):
        path = (folder or tmp_path / "meetings") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(0)
        sf.write(path, (rng.standard_normal(int(16000 * seconds)) * 0.05).astype("float32"), 16000)
        return path
    return create


def emb(seed):
    v = np.random.default_rng(seed).standard_normal(256).astype("float32")
    return v / np.linalg.norm(v)


@pytest.fixture
def meeting(wav):
    """Transcribed meeting with two speakers not reviewed yet: (wav, sidecar, txt)."""
    audio = wav()
    txt = audio.with_suffix(".txt")
    txt.write_text(
        "\n[0s] Speaker 1:\nHello everyone, let's start today's meeting now.\n"
        "\n[3s] Ana:\nGreat, I bring the sales report for the quarter.\n",
        encoding="utf-8",
    )
    sidecar = audio.with_suffix(".speakers.json")
    clusters = {
        spk: {"name": name, "unnamed": unnamed, "similarity": sim, "speech_seconds": 2.0,
              "embedding": emb(i).tolist(), "origin": {"audio": str(audio), "start": 0.0, "end": 2.0}}
        for i, (spk, name, unnamed, sim) in enumerate([("SPEAKER_A", "Speaker 1", True, 0.5),
                                                       ("SPEAKER_B", "Ana", False, 0.9)])
    }
    sidecar.write_text(json.dumps({"project": "test", "clusters": clusters}), encoding="utf-8")
    return audio, sidecar, txt
