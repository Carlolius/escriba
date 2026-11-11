"""Transcribes an audio file (locally or in the cloud) and leaves the .txt and
the .speakers.json next to it. It's what each background job runs."""
import os
from pathlib import Path

import psutil

from . import config, i18n
from .i18n import _

# The prompt goes in the language of the meeting: whisper leans towards the
# language of its prompt.
PROMPTS = {
    "es": "Reunión de trabajo. Términos y nombres propios: {terms}.",
    "gl": "Reunión de trabajo. Términos y nombres propios: {terms}.",
    "en": "Work meeting. Terms and proper names: {terms}.",
}


def local_available():
    """Local mode needs the "local" extra (faster-whisper and pyannote)."""
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("faster_whisper", "pyannote.audio"))


def missing_key(engine):
    """Name of the key the engine needs and isn't set, or None."""
    key = "ASSEMBLYAI_API_KEY" if engine == "cloud" else "HF_TOKEN"
    return None if config.read_secret(key) else key


def low_priority():
    """Like nice 19 + ionice idle, on Linux, macOS and Windows: uses the free
    CPU without making the rest of the PC sluggish."""
    p = psutil.Process()
    try:
        p.nice(psutil.IDLE_PRIORITY_CLASS if os.name == "nt" else 19)
    except (psutil.Error, OSError):
        pass
    if hasattr(psutil, "IOPRIO_CLASS_IDLE"):  # Linux only
        try:
            p.ionice(psutil.IOPRIO_CLASS_IDLE)
        except (psutil.Error, OSError):
            pass


def glossary_prompt(language="auto"):
    lines = config.read_glossary()
    if not lines:
        return ""
    lang = language if language in PROMPTS else i18n.language()
    return PROMPTS.get(lang, PROMPTS["en"]).format(terms=", ".join(lines))


def transcribe(audio, engine="cloud", model="medium", language="auto", diarize=True, project="",
               speakers=(), prompt=None):
    """engine: "cloud" (AssemblyAI) or "local" (faster-whisper + pyannote)."""
    audio = Path(audio).resolve()
    out = audio.with_suffix(".txt")
    if engine == "cloud":
        from . import cloud
        print(_("Transcribing in the cloud (AssemblyAI) → {path}", path=out), flush=True)
        cloud.transcribe(audio, out, language=language, diarize=diarize, project=project, speakers=speakers)
    else:
        from . import local
        low_priority()
        print(_("Transcribing with faster-whisper ({model}, low priority) → {path}", model=model, path=out),
              flush=True)
        local.transcribe(audio, out, model=model, language=language,
                         prompt=glossary_prompt(language) if prompt is None else prompt,
                         diarize=diarize, project=project, speakers=speakers)
    return out
