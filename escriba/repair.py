"""Repairing paths: voice samples pointing at an audio file that isn't there.

It happens when meetings are moved to another folder or folders are renamed.
Voice identification keeps working (the voiceprint is in the library), but
those samples can't be played any more. The audio files are looked up by file
name in the projects' folders (and any others given) and, when there's a
single candidate, the paths are updated in the libraries, their .bak and the
sidecars.
"""
import json
from pathlib import Path

from . import archive, config

EXTENSIONS = (".wav", ".opus", ".flac", ".ogg")


def _origins(samples):
    for s in samples:
        origin = s.get("origin") if isinstance(s, dict) else None
        if origin and origin.get("audio"):
            yield origin["audio"]


def _folders(extra=()):
    seen, folders = set(), []
    for d in [*archive.project_dirs(), *map(Path, extra)]:
        d = Path(d).expanduser()
        if d.is_dir() and d.resolve() not in seen:
            seen.add(d.resolve())
            folders.append(d)
    return folders


def broken_paths(extra=()):
    """{path that doesn't exist: number of references} in libraries and sidecars."""
    broken = {}

    def check(path):
        if not Path(path).exists():
            broken[path] = broken.get(path, 0) + 1

    for lib in config.voiceprints_dir().glob("*.json*"):
        if ".audit_ok" in lib.name:
            continue
        try:
            data = json.loads(lib.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for samples in data.values():
            if isinstance(samples, list):
                for path in _origins(samples):
                    check(path)
    for folder in _folders(extra):
        for sidecar in folder.rglob("*.speakers.json"):
            try:
                clusters = json.loads(sidecar.read_text(encoding="utf-8")).get("clusters", {})
            except (OSError, json.JSONDecodeError):
                continue
            for path in _origins(clusters.values()):
                check(path)
    return broken


def repair(extra=(), dry_run=False):
    """Returns {"fixed": [(old, new, refs)], "not_found": [old],
    "ambiguous": [(old, [candidates])]}."""
    broken = broken_paths(extra)
    result = {"fixed": [], "not_found": [], "ambiguous": []}
    if not broken:
        return result

    by_name = {}
    for folder in _folders(extra):
        for p in folder.rglob("*"):
            if p.suffix.lower() in EXTENSIONS and p.is_file():
                by_name.setdefault(p.name, set()).add(p.resolve())

    for old in sorted(broken):
        o = Path(old)
        candidates = by_name.get(o.name, set())
        if not candidates and o.suffix.lower() == ".wav":
            # Archived to Opus after being moved
            candidates = by_name.get(o.with_suffix(".opus").name, set())
        if len(candidates) == 1:
            new = next(iter(candidates))
            refs = broken[old] if dry_run else archive.update_paths(o, new)
            result["fixed"].append((old, str(new), refs))
        elif candidates:
            result["ambiguous"].append((old, sorted(map(str, candidates))))
        else:
            result["not_found"].append(old)
    return result
