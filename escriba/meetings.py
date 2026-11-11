"""The recorded meetings of a folder: what state each one is in, and deleting
one (for instance a test recording) with everything that came out of it.

A meeting is an audio file (.wav, or .opus once archived) plus what escriba
writes next to it: <name>.txt, <name>.speakers.json and <name>_transcribe.log.
"""
import json
from datetime import datetime
from pathlib import Path

from . import jobs, voiceprints
from .i18n import _
from .review import SUFFIX

AUDIO = (".wav", ".opus")
# Order in which they're listed
STATUSES = ("recording", "transcribing", "untranscribed", "to_review", "reviewed")


def files_of(audio):
    """The files that belong to this meeting and exist, audio first."""
    audio = Path(audio)
    candidates = [audio, *(audio.with_suffix(s) for s in AUDIO if s != audio.suffix),
                  audio.with_suffix(".txt"), audio.with_name(audio.stem + SUFFIX),
                  audio.with_name(audio.stem + "_transcribe.log")]
    return [p for p in candidates if p.exists()]


def status(audio, running=(), recording=None):
    audio = Path(audio)
    if recording and audio.resolve() == Path(recording).resolve():
        return "recording"
    if str(audio.resolve()) in running:
        return "transcribing"
    if not audio.with_suffix(".txt").exists():
        return "untranscribed"
    sidecar = audio.with_name(audio.stem + SUFFIX)
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if data.get("clusters") and not data.get("reviewed"):
            return "to_review"
    return "reviewed"


def list_meetings(folder, recording=None, limit=200):
    """[{"audio", "status", "date", "duration", "archived"}] under folder,
    newest first. If a meeting has both a WAV and an Opus, the WAV counts."""
    from . import audio as audio_util

    folder = Path(folder)
    if not folder.is_dir():
        return []
    found = {}
    for path in folder.rglob("*"):
        if path.suffix.lower() in AUDIO and path.is_file():
            key = path.with_suffix("")
            if key not in found or path.suffix.lower() == ".wav":
                found[key] = path
    newest = sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    running = jobs.running_audio()
    return [{
        "audio": p,
        "status": status(p, running, recording),
        "date": datetime.fromtimestamp(p.stat().st_mtime),
        "duration": audio_util.duration(p),
        "archived": p.suffix.lower() == ".opus",
    } for p in newest]


def delete(audio, delete_samples=False):
    """Deletes the meeting's files and, if asked, the voice samples taken from
    it (otherwise they stay in the library but can't be played any more).
    Refuses while it's being transcribed. Files first: if one can't be
    deleted (open in another program, on Windows), the samples are kept.
    Returns (files deleted, samples deleted)."""
    audio = Path(audio)
    if str(audio.resolve()) in jobs.running_audio():
        raise RuntimeError(_("{name} is being transcribed: wait until it ends", name=audio.stem))
    deleted = 0
    for p in files_of(audio):
        try:
            p.unlink()
            deleted += 1
        except FileNotFoundError:
            pass
        except PermissionError as e:
            raise RuntimeError(_("Can't delete {name}: it's open in another program ({error})",
                                 name=p.name, error=e)) from e
    samples = voiceprints.delete_samples_from_audio(audio) if delete_samples else 0
    return deleted, samples
