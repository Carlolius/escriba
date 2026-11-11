"""Reviewing the speakers of a transcript and feeding the voice library.

Each transcript with identification has an <audio>.speakers.json with a
cluster per detected voice (see speakers.py). Reviewing means, for each
cluster: confirm the name (reinforces the library), correct it (adds the
sample to the right person and renames it in the .txt) or skip it (leaves the
library alone). Every decision is saved at once, so a review can be stopped
and resumed.

This layer asks nothing: the terminal menu and the web decide what to show.
"""
import json
import re
from pathlib import Path

import numpy as np

from . import archive, config, voiceprints

SUFFIX = ".speakers.json"


def load(sidecar):
    return json.loads(Path(sidecar).read_text(encoding="utf-8"))


def meeting_name(sidecar):
    return Path(sidecar).name.removesuffix(SUFFIX)


def txt_path(sidecar):
    sidecar = Path(sidecar)
    return sidecar.with_name(meeting_name(sidecar) + ".txt")


def quotes(text, name, n=3):
    """The n longest sentences `name` said in the transcript, in time order.
    Speaker headers are '[Ns] Name:' after a blank line."""
    found, current, previous = [], None, ""
    for line in text.splitlines():
        m = re.match(r"^\[\d+s\] (.+):$", line)
        if m and not previous.strip():
            current = m.group(1)
        elif current == name and line.strip():
            sentence = re.sub(r"^\[\d+s\] ", "", line).strip()
            if len(sentence.split()) >= 5:
                found.append(sentence)
        previous = line
    chosen = sorted(sorted(range(len(found)), key=lambda i: -len(found[i]))[:n])
    return [found[i] if len(found[i]) <= 140 else found[i][:137] + "..." for i in chosen]


def quotes_by_cluster(sidecar, n=3):
    txt = txt_path(sidecar)
    text = txt.read_text(encoding="utf-8") if txt.exists() else ""
    return {spk: quotes(text, info["name"], n) for spk, info in load(sidecar)["clusters"].items()}


def pending(only_project=None):
    """[(project, sidecar)] not reviewed yet, newest first, looking in each
    project's last folder. rglob because a project's recordings can end up in
    different subfolders."""
    found = {}
    for project, folder in config.load_state().get("project_dirs", {}).items():
        if only_project and project != only_project:
            continue
        folder = Path(folder)
        if not folder.exists():
            continue
        for s in folder.rglob("*" + SUFFIX):
            try:
                data = load(s)
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("clusters") and not data.get("reviewed"):  # no voices: nothing to review
                found[s.resolve()] = data.get("project", project)
    newest = sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    return [(found[s], s) for s in newest]


def known_names(sidecar, project):
    data = load(sidecar)
    return sorted(
        {c["name"] for c in data["clusters"].values() if not c.get("unnamed")}
        | set(voiceprints.load_library(project))
    )


def decide(sidecar, spk, new_name, project=None):
    """Saves the decision on a cluster. new_name: the same name = confirm,
    another one = correct, "" or None = skip.

    Returns {"samples": n, "added": bool, "renamed": n, "complete": bool}."""
    sidecar = Path(sidecar)
    data = load(sidecar)
    project = project or data.get("project")
    info = data["clusters"][spk]
    result = {"samples": 0, "added": False, "renamed": 0}

    if new_name:
        emb = np.array(info["embedding"], dtype="float32")
        result["samples"], result["added"] = voiceprints.add_sample(project, new_name, emb, origin=info.get("origin"))
        txt = txt_path(sidecar)
        if new_name != info["name"] and txt.exists():
            pattern = rf"^(\[\d+s\]) {re.escape(info['name'])}:$"
            text, n = re.subn(pattern, lambda m: f"{m.group(1)} {new_name}:",
                              txt.read_text(encoding="utf-8"), flags=re.MULTILINE)
            if n:
                txt.write_text(text, encoding="utf-8")
            result["renamed"] = n
        info["name"] = new_name
        info["unnamed"] = False

    info["reviewed"] = True
    data["reviewed"] = all(c.get("reviewed") for c in data["clusters"].values())
    config.write_json(sidecar, data)
    result["complete"] = data["reviewed"]
    return result


def remaining(sidecar):
    return sum(1 for c in load(sidecar)["clusters"].values() if not c.get("reviewed"))


def archive_if_complete(sidecar):
    """Once the meeting is reviewed, its WAV is only an archive: it goes to
    Opus. Returns (opus_path, bytes_saved), or None if there was nothing to do."""
    sidecar = Path(sidecar)
    wav = sidecar.with_name(meeting_name(sidecar) + ".wav")
    if not wav.exists() or not archive.ready_to_archive(wav):
        return None
    opus, saved, _refs = archive.archive(wav)
    return opus, saved


def enroll(audio, start, end, name, project):
    """Adds a voice sample by hand (the start-end clip of an audio file)."""
    from resemblyzer import VoiceEncoder

    from . import audio as audio_util

    data, _sr = audio_util.read_clip(audio, start, end)
    emb = VoiceEncoder(verbose=False).embed_utterance(data)
    origin = {"audio": str(Path(audio).resolve()), "start": float(start), "end": float(end)}
    return voiceprints.add_sample(project, name, emb, origin=origin)
