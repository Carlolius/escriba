"""Transcribes and separates speakers in the cloud with AssemblyAI.

Much faster than local mode (minutes instead of ~1 h per hour of audio), for
~$0.23 per hour of audio and the audio leaving the PC. Transcription and
diarization happen there; voice identification against the project library
and the .txt/.speakers.json are done here, the same as in local mode
(speakers.py), so reviewing speakers works the same.

Steps: compress to Opus (~10x less to upload) -> upload -> transcribe with
your glossary as key terms -> download -> delete the transcript from
AssemblyAI (neither the audio nor the text stays there).

Needs the ASSEMBLYAI_API_KEY key (see config.read_secret).
"""
import sys
import tempfile
import time
from pathlib import Path

import requests

from . import audio as audio_util
from . import config, speakers as speakers_mod
from .i18n import _
from .progress import Progress, mmss, phase

API = "https://api.assemblyai.com/v2"
PRICE_PER_HOUR = 0.23  # $ (universal-3-5-pro 0.21 + diarization 0.02), Oct 2026
UPLOAD_CHUNK = 256 * 1024


class CloudError(RuntimeError):
    pass


def key_terms():
    """Glossary terms as keyterms (at most 6 words each)."""
    terms = []
    for line in config.read_glossary():
        for t in line.split(","):
            t = t.strip()
            if t and len(t.split()) <= 6:
                terms.append(t)
    return terms


def upload(session, path):
    total = path.stat().st_size
    progress = Progress()

    def chunks():
        sent = 0
        with open(path, "rb") as f:
            while chunk := f.read(UPLOAD_CHUNK):
                sent += len(chunk)
                progress.update("upload", sent, total)
                yield chunk

    try:
        r = session.post(f"{API}/upload", data=chunks(), timeout=600)
        r.raise_for_status()
    finally:
        progress.close()
    return r.json()["upload_url"]


MAX_WAIT = 6 * 3600      # seconds: something is wrong if it takes longer
NETWORK_RETRIES = 40     # consecutive failed checks (~5 min) before giving up


def wait(session, transcript_id):
    """AssemblyAI gives no percentage: show the status and the time so far.
    A network hiccup doesn't lose the transcription: it keeps asking."""
    start, last_status, last_print = time.time(), None, 0.0
    tty = sys.stdout.isatty()
    failures = 0
    while True:
        if time.time() - start > MAX_WAIT:
            raise CloudError(_("AssemblyAI didn't finish in {hours} h (transcript {id})",
                               hours=MAX_WAIT // 3600, id=transcript_id))
        try:
            r = session.get(f"{API}/transcript/{transcript_id}", timeout=60)
            r.raise_for_status()
            data = r.json()
            failures = 0
        except requests.RequestException as e:
            failures += 1
            if failures >= NETWORK_RETRIES:
                raise
            print(_("Network error, trying again: {error}", error=e), flush=True)
            time.sleep(min(30, 2 * failures))
            continue
        status = data["status"]
        if status in ("completed", "error"):
            if tty:
                print()
            return data
        elapsed = mmss(time.time() - start)
        if tty:
            print("\r" + _("Processing in the cloud ({status}): {elapsed}", status=status, elapsed=elapsed) + "   ",
                  end="", flush=True)
        elif status != last_status or time.time() - last_print >= 15:
            print(f"[cloud] {status} {elapsed}", flush=True)
            last_print = time.time()
        last_status = status
        time.sleep(3)


def segments_from_words(words):
    """Groups words into sentences (end of sentence, change of speaker or 30 s)
    so the .txt has [Ns] marks as often as in local mode."""
    segments, current = [], []
    for w in words:
        if current and (w.get("speaker") != current[0].get("speaker") or w["end"] - current[0]["start"] > 30000):
            segments.append(current)
            current = []
        current.append(w)
        if w["text"].endswith((".", "?", "!", "…")):
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return [(s[0]["start"] / 1000, s[-1]["end"] / 1000, " ".join(w["text"] for w in s)) for s in segments]


def transcribe(audio, out, language="auto", diarize=False, project="", speakers=()):
    key = config.read_secret("ASSEMBLYAI_API_KEY")
    if not key:
        raise CloudError(_("The AssemblyAI key is missing (ASSEMBLYAI_API_KEY)"))
    audio = Path(audio)
    speakers = list(speakers)
    session = requests.Session()
    session.headers["authorization"] = key

    with tempfile.TemporaryDirectory() as tmp:
        compressed = Path(tmp) / "upload.opus"
        phase("compressing")
        print(_("Compressing for upload..."), flush=True)
        audio_util.compress_opus(audio, compressed, level=audio_util.UPLOAD_LEVEL)
        url = upload(session, compressed)

    request = {"audio_url": url, "speech_models": ["universal-3-5-pro", "universal-2"], "punctuate": True}
    if language and language != "auto":
        request["language_code"] = language
    else:
        request["language_detection"] = True
    if diarize:
        request["speaker_labels"] = True
        if speakers and not project:
            request["speakers_expected"] = len(speakers)
    if terms := key_terms():
        request["keyterms_prompt"] = terms

    r = session.post(f"{API}/transcript", json=request, timeout=60)
    if r.status_code >= 400 and "keyterms_prompt" in request:
        # Only universal-3-5-pro takes keyterms; if the language falls back to another model, no glossary
        print(_("WARNING: AssemblyAI doesn't accept the glossary ({error}); retrying without it",
                error=r.json().get("error", r.text)))
        del request["keyterms_prompt"]
        r = session.post(f"{API}/transcript", json=request, timeout=60)
    r.raise_for_status()
    transcript_id = r.json()["id"]

    phase("cloud_waiting")
    data = wait(session, transcript_id)
    if data["status"] == "error":
        session.delete(f"{API}/transcript/{transcript_id}", timeout=60)
        raise CloudError(_("AssemblyAI error: {error}", error=data.get("error")))

    phase("cloud_done")
    seconds = data.get("audio_duration") or 0
    print(_("Detected language: {language} · model {model} · duration: {seconds:.0f}s · approx. cost ${cost:.2f}",
            language=data.get("language_code"), model=data.get("speech_model_used"), seconds=seconds,
            cost=seconds / 3600 * PRICE_PER_HOUR), flush=True)

    segments = segments_from_words(data.get("words") or [])
    turns = None
    if diarize and data.get("utterances"):
        turns = [(u["start"] / 1000, u["end"] / 1000, f"SPEAKER_{u['speaker']}") for u in data["utterances"]]

    # We have everything: delete it from AssemblyAI (text and uploaded audio)
    try:
        session.delete(f"{API}/transcript/{transcript_id}", timeout=60).raise_for_status()
    except requests.RequestException as e:
        print(_("WARNING: couldn't delete transcript {id} from AssemblyAI: {error}", id=transcript_id, error=e))

    names = speakers_mod.safe_name_speakers(audio, out, turns, project, speakers) if turns else None
    speakers_mod.write_transcript(str(out), segments, turns, names)
