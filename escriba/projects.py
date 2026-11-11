"""Editing projects: renaming, changing the folder and deleting one.

A project is its voice library (voiceprints/<name>.json, plus the .bak undo
copy and the .audit_ok.json reviewed findings), its folder in the state, and
its name in the meetings' .speakers.json. Recordings and transcripts are never
deleted here.
"""
import json
import os
from pathlib import Path

from . import config, jobs, voiceprints
from .i18n import _
from .review import SUFFIX


def _files(name):
    base = config.voiceprints_dir()
    return [base / f"{name}.json", base / f"{name}.json.bak", base / f"{name}.audit_ok.json"]


def summary():
    """[{"name", "folder", "people", "samples"}] of every project."""
    result = []
    for name in config.list_projects():
        library = voiceprints._load(voiceprints.library_path(name))
        result.append({"name": name, "folder": config.project_dir(name), "people": len(library),
                       "samples": sum(len(s) for s in library.values())})
    return result


def _check_idle(name):
    for job in config.load_state().get("jobs", []):
        if job.get("project") == name and not job.get("status") and jobs.is_alive(job["pid"]):
            raise RuntimeError(_("{name} has a transcription running: wait until it ends", name=name))


def _sidecars(name):
    """The .speakers.json of the project's meetings, in every folder escriba knows."""
    folders = {Path(f) for f in config.load_state().get("project_dirs", {}).values()}
    seen = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for sidecar in folder.rglob("*" + SUFFIX):
            if sidecar.resolve() in seen:
                continue
            seen.add(sidecar.resolve())
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("project") == name:
                yield sidecar, data


def rename(old, new):
    """Renames a project. ValueError if the new name isn't valid or is taken,
    RuntimeError while it's transcribing. Returns how many meetings changed."""
    new = config.check_project_name(new)
    if new == old:
        return 0
    if old not in config.list_projects():
        raise ValueError(_("{name} doesn't exist", name=old))
    if new.lower() in {p.lower() for p in config.list_projects() if p != old}:
        raise ValueError(_("There's already a project called {name}", name=new))
    _check_idle(old)
    for source, target in zip(_files(old), _files(new)):
        if source.exists():
            os.replace(source, target)

    def change(state):
        dirs = state.get("project_dirs", {})
        if old in dirs:
            dirs[new] = dirs.pop(old)
        if state.get("last_project") == old:
            state["last_project"] = new
        for job in state.get("jobs", []):
            if job.get("project") == old:
                job["project"] = new
    config.update_state(change)
    changed = 0
    for sidecar, data in _sidecars(old):
        data["project"] = new
        config.write_json(sidecar, data)
        changed += 1
    return changed


def delete(name):
    """Deletes a project's voice library (the voices of its people) and
    forgets its folder. The recordings and transcripts stay where they are.
    RuntimeError while it's transcribing."""
    _check_idle(name)
    for path in _files(name):
        path.unlink(missing_ok=True)

    def change(state):
        state.get("project_dirs", {}).pop(name, None)
        if state.get("last_project") == name:
            state.pop("last_project")
    config.update_state(change)
