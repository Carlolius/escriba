"""Transcribe un audio (local o en la nube) y deja el .txt y el .speakers.json
junto a él. Es lo que ejecuta cada transcripción en segundo plano."""
import os
from pathlib import Path

import psutil

from . import config


def local_disponible():
    """El modo local necesita el extra "local" (faster-whisper y pyannote)."""
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("faster_whisper", "pyannote.audio"))


def clave_que_falta(motor):
    """Nombre de la clave que necesita el motor y no está, o None."""
    clave = "ASSEMBLYAI_API_KEY" if motor == "nube" else "HF_TOKEN"
    return None if config.leer_secreto(clave) else clave


def prioridad_baja():
    """Equivalente a nice 19 + ionice idle, en Linux, macOS y Windows: usa la
    CPU que esté libre sin quitarle fluidez al resto del PC."""
    p = psutil.Process()
    try:
        p.nice(psutil.IDLE_PRIORITY_CLASS if os.name == "nt" else 19)
    except (psutil.Error, OSError):
        pass
    if hasattr(psutil, "IOPRIO_CLASS_IDLE"):  # solo Linux
        try:
            p.ionice(psutil.IOPRIO_CLASS_IDLE)
        except (psutil.Error, OSError):
            pass


def prompt_glosario():
    lineas = config.leer_glosario()
    if not lineas:
        return ""
    return f"Reunión de trabajo. Términos y nombres propios: {', '.join(lineas)}."


def transcribir(audio, motor="nube", modelo="medium", idioma="auto", diarizar=True, proyecto="",
                hablantes=(), prompt=None):
    """motor: "nube" (AssemblyAI) o "local" (faster-whisper + pyannote)."""
    audio = Path(audio).resolve()
    salida = audio.with_suffix(".txt")
    if motor == "nube":
        from . import nube
        print(f"Transcribiendo en la nube (AssemblyAI) → {salida}", flush=True)
        nube.transcribir(audio, salida, idioma=idioma, diarizar=diarizar, proyecto=proyecto,
                         hablante_list=hablantes)
    else:
        from . import local
        prioridad_baja()
        print(f"Transcribiendo con faster-whisper ({modelo}, prioridad baja) → {salida}", flush=True)
        local.transcribir(audio, salida, modelo=modelo, idioma=idioma,
                          prompt=prompt_glosario() if prompt is None else prompt,
                          diarizar=diarizar, proyecto=proyecto, hablante_list=hablantes)
    return salida
