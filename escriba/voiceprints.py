"""Speaker identification by voiceprint (one voice library per project).

Each person may have several samples (embeddings from encoder.py) taken in
different recording conditions. Identification uses the highest similarity
between the cluster's embedding and every saved sample of each person.

voiceprints/<project>.json: {name: [sample, ...]}, each sample being
  {"id": "abc123...", "embedding": [...], "origin": {"audio", "start", "end"} | None}

"id" is stable (it doesn't change when other samples are deleted or moved) and
is what delete_sample/move_sample use to point at a sample.
"""
import os
import uuid
from pathlib import Path

import numpy as np

from . import config

DEFAULT_THRESHOLD = 0.87
DUPLICATE_THRESHOLD = 0.93


def library_path(project):
    return str(config.voiceprints_dir() / f"{project}.json")


def _backup(path):
    """One-step backup before a destructive operation (delete, move, rename).
    It keeps the state just before that change, not a full history; any
    later change that isn't backed up (a sample added in a review) drops it,
    so that undoing never throws that change away."""
    if os.path.exists(path):
        config.write_json(path + ".bak", _load(path), indent=None)


def has_backup(project):
    return os.path.exists(library_path(project) + ".bak")


def restore_backup(project):
    """Undoes the last delete/move by restoring the library's .bak copy."""
    path = library_path(project)
    if not os.path.exists(path + ".bak"):
        return False
    config.write_json(path, _load(path + ".bak"), indent=None)
    return True


def _load(path):
    if not os.path.exists(path):
        return {}
    return config.read_json(path)


def _save(path, data, backed_up=False):
    """Atomic: a crash halfway, or a background job reading it, never sees
    half a library. backed_up: _backup() was called for this change;
    otherwise the old backup no longer describes "the last change"."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    config.write_json(path, data, indent=None)
    if not backed_up and os.path.exists(path + ".bak"):
        os.remove(path + ".bak")


def load_library(project):
    """For similarity: name -> list of embeddings (np.array)."""
    return {
        name: [np.array(s["embedding"], dtype="float32") for s in samples]
        for name, samples in _load(library_path(project)).items()
    }


def load_samples(project):
    """For managing/playing: name -> list of {"id", "embedding", "origin"}."""
    return _load(library_path(project))


def cos_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def identify(embedding, library, threshold=DEFAULT_THRESHOLD):
    """(name, similarity) of the best match, or (None, similarity) below the threshold."""
    best_name, best_sim = None, 0.0
    for name, samples in library.items():
        sim = max(cos_sim(embedding, s) for s in samples)
        if sim > best_sim:
            best_sim, best_name = sim, name
    if best_sim >= threshold:
        return best_name, best_sim
    return None, best_sim


def add_sample(project, name, embedding, origin=None):
    """origin, if known: {"audio": path, "start": seconds, "end": seconds}.

    If the new sample is almost identical to one already saved (similarity >=
    DUPLICATE_THRESHOLD: same conditions again, same channel, same day...),
    no new entry is added. So the library doesn't grow forever just by
    confirming the same condition over and over; it only grows with samples
    that really bring a different condition.

    Returns (n_samples, added): the current total for that person, and
    whether this call added a new sample."""
    path = library_path(project)
    data = _load(path)
    existing = data.get(name, [])

    if existing:
        best = max(cos_sim(embedding, np.array(s["embedding"], dtype="float32")) for s in existing)
        if best >= DUPLICATE_THRESHOLD:
            return len(existing), False

    sample = {"id": uuid.uuid4().hex[:10], "embedding": embedding.tolist(), "origin": origin}
    data.setdefault(name, []).append(sample)
    _save(path, data)
    return len(data[name]), True


def delete_person(project, name):
    path = library_path(project)
    data = _load(path)
    if name not in data:
        return False
    _backup(path)
    del data[name]
    _save(path, data, backed_up=True)
    return True


def _index(samples, sample_id):
    return next((i for i, s in enumerate(samples) if s["id"] == sample_id), None)


def find_sample(project, name, sample_id):
    return next((s for s in load_samples(project).get(name, []) if s["id"] == sample_id), None)


def delete_sample(project, name, sample_id):
    path = library_path(project)
    data = _load(path)
    samples = data.get(name, [])
    i = _index(samples, sample_id)
    if i is None:
        return False
    _backup(path)
    samples.pop(i)
    if not samples:
        del data[name]
    _save(path, data, backed_up=True)
    return True


def move_sample(project, current_name, sample_id, new_name):
    """Moves a sample from one person to another (or to a new name), keeping
    its embedding and origin."""
    path = library_path(project)
    data = _load(path)
    samples = data.get(current_name, [])
    i = _index(samples, sample_id)
    if i is None:
        return False
    _backup(path)
    sample = samples.pop(i)
    if not samples:
        del data[current_name]
    data.setdefault(new_name, []).append(sample)
    _save(path, data, backed_up=True)
    return True


def rename_person(project, old_name, new_name):
    """Renames a person. If new_name already exists, old_name's samples join
    theirs (it was the same person under two names). Returns the new total of
    samples, or None if old_name doesn't exist."""
    path = library_path(project)
    data = _load(path)
    if old_name not in data or not new_name or new_name == old_name:
        return None
    _backup(path)
    data.setdefault(new_name, []).extend(data.pop(old_name))
    _save(path, data, backed_up=True)
    return len(data[new_name])


def _from_audio(sample, audio):
    origin = sample.get("origin")
    return bool(origin) and Path(origin["audio"]).resolve() == Path(audio).resolve()


def samples_from_audio(audio):
    """{project: n} of the samples taken from this audio, in every library."""
    found = {}
    for project in config.list_projects():
        n = sum(_from_audio(s, audio) for samples in load_samples(project).values() for s in samples)
        if n:
            found[project] = n
    return found


def delete_samples_from_audio(audio):
    """Deletes from every library the samples taken from this audio (one
    backup per library, so it can be undone). Returns how many it deleted."""
    total = 0
    for project in samples_from_audio(audio):
        path = library_path(project)
        data = _load(path)
        _backup(path)
        for name in list(data):
            kept = [s for s in data[name] if not _from_audio(s, audio)]
            total += len(data[name]) - len(kept)
            if kept:
                data[name] = kept
            else:
                del data[name]
        _save(path, data, backed_up=True)
    return total

# ── Audit ────────────────────────────────────────────────────────────────────

def _audit_ok_path(project):
    return str(config.voiceprints_dir() / f"{project}.audit_ok.json")


def load_audit_ok(project):
    """Audit findings the user already marked as fine: don't show them again
    even if the similarity stays the same. Kept on disk between sessions."""
    path = _audit_ok_path(project)
    if not os.path.exists(path):
        return set()
    return {tuple(x) for x in config.read_json(path)}


def finding_key(kind, id_a, id_b):
    return (kind,) + tuple(sorted((id_a, id_b)))


def mark_as_ok(project, kind, id_a, id_b):
    path = _audit_ok_path(project)
    ok = load_audit_ok(project)
    ok.add(finding_key(kind, id_a, id_b))
    config.write_json(path, sorted(list(k) for k in ok), indent=None)


def audit_library(project, confusion_threshold=0.80, include_ok=False):
    """Finds three kinds of problem in the library, always pointing at the most
    telling pair of samples (by id) of each finding:
    - "spread": two samples of the same person that don't look alike
      (maybe two different recording conditions mixed up, or two people).
    - "duplicate": two almost identical samples of the same person
      (same condition twice: nothing new, one can be deleted).
    - "confusion": samples of two different people that look very alike
      (real risk of misidentifying, especially above DEFAULT_THRESHOLD).

    Leaves out the ones the user marked as fine (see mark_as_ok) unless
    include_ok=True.

    Each finding: {"kind", "similarity", "name_a", "id_a", "name_b", "id_b"}.
    """
    data = load_samples(project)
    ok = set() if include_ok else load_audit_ok(project)
    findings = []

    def emb(s):
        return np.array(s["embedding"], dtype="float32")

    def finding(kind, sim, name_a, id_a, name_b, id_b):
        findings.append({"kind": kind, "similarity": sim, "name_a": name_a, "id_a": id_a,
                         "name_b": name_b, "id_b": id_b})

    for name, samples in data.items():
        if len(samples) < 2:
            continue
        worst = best = None
        for i, a in enumerate(samples):
            for b in samples[i + 1:]:
                sim = cos_sim(emb(a), emb(b))
                if worst is None or sim < worst[0]:
                    worst = (sim, a["id"], b["id"])
                if best is None or sim > best[0]:
                    best = (sim, a["id"], b["id"])
        if worst[0] < DEFAULT_THRESHOLD:
            finding("spread", worst[0], name, worst[1], name, worst[2])
        if best[0] >= DUPLICATE_THRESHOLD:
            finding("duplicate", best[0], name, best[1], name, best[2])

    names = list(data)
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            best = None
            for a in data[n1]:
                for b in data[n2]:
                    sim = cos_sim(emb(a), emb(b))
                    if best is None or sim > best[0]:
                        best = (sim, a["id"], b["id"])
            if best and best[0] >= confusion_threshold:
                finding("confusion", best[0], n1, best[1], n2, best[2])

    if ok:
        findings = [f for f in findings if finding_key(f["kind"], f["id_a"], f["id_b"]) not in ok]
    return findings


def most_urgent_first(findings):
    """Confusions and duplicates by highest similarity, spreads by lowest."""
    return sorted(findings, key=lambda f: -f["similarity"] if f["kind"] != "spread" else f["similarity"])
