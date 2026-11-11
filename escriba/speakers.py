"""Naming speakers and writing the final transcript.

Shared by local mode (whisper + pyannote, local.py) and cloud mode (cloud.py):
both produce text segments and speaker turns with times, and from there the
result is the same .txt and the same .speakers.json, reviewed later
(review.py).

- segments: [(start_s, end_s, text)]
- turns:    [(start_s, end_s, speaker_id)]

The .speakers.json ("sidecar") holds one cluster per detected voice:
  {"project": ..., "reviewed": bool, "clusters": {speaker_id: {
      "name", "unnamed" (no voice match: generic "Speaker N"),
      "similarity", "speech_seconds", "embedding",
      "origin": {"audio", "start", "end"}, "reviewed"}}}
"""
import os

from . import config, encoder, voiceprints
from .i18n import _


def _fallback_name(speakers, n):
    """Name for the n-th unrecognised voice: from the --speakers list, or "Speaker n"."""
    return speakers[n - 1] if n <= len(speakers) else _("Speaker {n}", n=n)


def name_speakers(audio, out, turns, project, speakers):
    """Returns {speaker_id: name}. With a project, identifies voices against
    voiceprints/<project>.json and saves the .speakers.json sidecar; without
    one, uses `speakers` in order of appearance."""
    speaker_ids = sorted(set(s for _s, _e, s in turns))
    names = {}

    if not project:
        for i, spk in enumerate(speaker_ids):
            names[spk] = _fallback_name(speakers, i + 1)
        return names

    import numpy as np
    import soundfile as sf

    library = voiceprints.load_library(project)
    if not library:
        print(_("WARNING: project {project} has no saved voices yet: no voice identification", project=project))
    by_speaker = {}
    for s, e, spk in turns:
        by_speaker.setdefault(spk, []).append((s, e))

    clusters = {}
    unmatched = 0
    audio_abs = os.path.abspath(audio)
    for spk, segs in by_speaker.items():
        longest = sorted(segs, key=lambda x: x[1] - x[0], reverse=True)
        origin_s, origin_e = longest[0]
        origin_e = min(origin_e, origin_s + 8.0)
        chunks, collected = [], 0.0
        with sf.SoundFile(audio) as f:
            sr = f.samplerate
            for s, e in longest:
                if collected >= 15.0:
                    break
                dur = min(e - s, 8.0)
                f.seek(int(s * sr))
                chunks.append(f.read(int(dur * sr), dtype="float32", always_2d=True))
                collected += dur
        if not chunks:
            unmatched += 1
            names[spk] = _fallback_name(speakers, unmatched)
            continue
        emb = encoder.embed(np.concatenate(chunks), sr)
        name, sim = voiceprints.identify(emb, library)
        if name:
            names[spk] = name
            print(_("  {speaker} -> {name} (similarity {similarity:.2f})", speaker=spk, name=name, similarity=sim))
        else:
            unmatched += 1
            names[spk] = _fallback_name(speakers, unmatched)
            print(_("  {speaker} -> not identified (best similarity {similarity:.2f}) -> {name}",
                    speaker=spk, similarity=sim, name=names[spk]))
        clusters[spk] = {
            "name": names[spk],
            "unnamed": not name and unmatched > len(speakers),
            "similarity": sim,
            "speech_seconds": sum(e - s for s, e in segs),
            "embedding": emb.tolist(),
            "origin": {"audio": audio_abs, "start": origin_s, "end": origin_e},
        }

    sidecar = os.path.splitext(out)[0] + ".speakers.json"
    config.write_json(sidecar, {"project": project, "clusters": clusters}, indent=None)
    print(_("  Saved {path} (to review the speakers later)", path=sidecar))
    return names


def safe_name_speakers(audio, out, turns, project, speakers):
    """name_speakers, but a failure there (a damaged library, an unreadable
    file) costs the names, not the transcription: it returns None and the
    .txt is written with the generic speaker ids."""
    try:
        return name_speakers(str(audio), str(out), turns, project, list(speakers))
    except Exception as e:
        print(_("WARNING: couldn't identify the voices ({error}): the transcript keeps generic speakers",
                error=e), flush=True)
        return None


def write_transcript(out, segments, turns=None, names=None):
    """Writes the .txt. With speaker turns, each segment goes to the speaker
    with the most overlap in time, with a header on every change of speaker
    (of cluster: two clusters with the same name get separate headers). Where
    each cluster's headers are is saved in the sidecar ("headers"), so that
    correcting one cluster in the review renames only its own lines."""
    names = names or {}

    def speaker_at(start, end):
        best, best_overlap = None, 0.0
        for t0, t1, spk in turns:
            overlap = min(end, t1) - max(start, t0)
            if overlap > best_overlap:
                best_overlap, best = overlap, spk
        return best

    headers = {}
    lines = []
    previous = object()
    for start, end, text in segments:
        if turns:
            spk = speaker_at(start, end)
            if spk != previous:
                lines.append(f"\n[{int(start)}s] {names.get(spk, spk) if spk else '?'}:\n{text}")
                if spk:
                    headers.setdefault(spk, []).append(int(start))
                previous = spk
                continue
        lines.append(f"[{int(start)}s] {text}")
    with open(out, "w", encoding="utf-8") as f:
        for line in lines:
            print(line)
            f.write(line + "\n")

    sidecar = os.path.splitext(out)[0] + ".speakers.json"
    if turns and os.path.exists(sidecar):
        try:
            data = config.read_json(sidecar)
            data["headers"] = headers
            config.write_json(sidecar, data, indent=None)
        except (OSError, ValueError):
            pass
    print("\n" + _("Saved: {path}", path=out))
