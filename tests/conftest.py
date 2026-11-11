import json

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    """Cada prueba con su propia carpeta de datos y sin claves del entorno."""
    carpeta = tmp_path / "datos"
    monkeypatch.setenv("ESCRIBA_DATOS", str(carpeta))
    for clave in ("ASSEMBLYAI_API_KEY", "HF_TOKEN"):
        monkeypatch.delenv(clave, raising=False)
    return carpeta


@pytest.fixture
def wav(tmp_path):
    """Crea un WAV mono de 16 kHz con ruido suave; devuelve su ruta."""
    def crear(nombre="reunion.wav", segundos=5.0, carpeta=None):
        ruta = (carpeta or tmp_path / "reuniones") / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(0)
        sf.write(ruta, (rng.standard_normal(int(16000 * segundos)) * 0.05).astype("float32"), 16000)
        return ruta
    return crear


def emb(semilla):
    v = np.random.default_rng(semilla).standard_normal(256).astype("float32")
    return v / np.linalg.norm(v)


@pytest.fixture
def reunion(wav):
    """Reunión transcrita con dos hablantes sin revisar: (wav, sidecar, txt)."""
    audio = wav()
    txt = audio.with_suffix(".txt")
    txt.write_text(
        "\n[0s] Hablante 1:\nHola a todos, empezamos con la reunión de hoy.\n"
        "\n[3s] Ana:\nPerfecto, yo traigo el informe de ventas del trimestre.\n",
        encoding="utf-8",
    )
    sidecar = audio.with_suffix(".speakers.json")
    clusters = {
        spk: {"nombre": nombre, "similitud": sim, "duracion_hablada": 2.0, "embedding": emb(i).tolist(),
              "origen": {"audio": str(audio), "inicio": 0.0, "fin": 2.0}}
        for i, (spk, nombre, sim) in enumerate([("SPEAKER_A", "Hablante 1", 0.5), ("SPEAKER_B", "Ana", 0.9)])
    }
    sidecar.write_text(json.dumps({"proyecto": "prueba", "clusters": clusters}), encoding="utf-8")
    return audio, sidecar, txt
