"""Where escriba keeps its data, and reading state, secrets and glossary.

Everything that belongs to the user (voice libraries, state, glossary, keys)
lives in their data folder, not next to the program:
  Linux:   ~/.local/share/escriba
  Windows: %LOCALAPPDATA%\\escriba
  macOS:   ~/Library/Application Support/escriba
The ESCRIBA_DATA environment variable overrides it (useful for tests).

Recordings and transcripts don't move: they stay in each project's folders,
chosen by the user.
"""
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import platformdirs

from .i18n import N_, _

APP = "escriba"


def data_dir():
    path = os.environ.get("ESCRIBA_DATA")
    path = Path(path).expanduser() if path else platformdirs.user_data_path(APP, appauthor=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def voiceprints_dir():
    path = data_dir() / "voiceprints"
    path.mkdir(exist_ok=True)
    return path


def glossary_path():
    path = data_dir() / "glossary.txt"
    if not path.exists():
        path.write_text(_(INITIAL_GLOSSARY), encoding="utf-8")
    return path


def secrets_path():
    return data_dir() / "secrets.env"


def _state_path():
    return data_dir() / "state.json"


def _retry(action, attempts=20):
    """On Windows a file another process is reading can't be replaced for a
    moment (PermissionError): try again for up to ~1 s."""
    for i in range(attempts):
        try:
            return action()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05)


def write_json(path, data, indent=2):
    """Atomic write: the terminal menu, the web and background jobs may read a
    file while another one writes it. Each write uses its own temporary file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        _retry(lambda: os.replace(tmp, path))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path):
    return _retry(lambda: json.loads(Path(path).read_text(encoding="utf-8")))


@contextmanager
def locked(name="state", timeout=10.0):
    """Exclusive section between threads and processes (web, menu, jobs) for
    read-modify-write. A lock file older than `timeout` is from a process that
    died, and is taken over."""
    lock = data_dir() / f".{name}.lock"
    with _THREAD_LOCK:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > timeout:
                        lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if time.monotonic() > deadline:
                    lock.unlink(missing_ok=True)  # stuck: better than not saving at all
                    continue
                time.sleep(0.02)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)


_THREAD_LOCK = threading.RLock()


# ── State (last project and folders, running jobs, preferences) ──────────────
# Keys: last_project, project_dirs {project: folder}, jobs [{audio, log, pid,
# project, engine, status, ended}], theme (system/light/dark), colors (see
# themes.py), language,
# output_device, mic, gpu.

def load_state():
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = read_json(path)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def update_state(change=None, **changes):
    """Read, change and save under the lock, so nothing another window or a
    background job saved in between is lost. `change(state)` may modify the
    state in place; keyword arguments are set as they are. If the file exists
    but can't be read, it's kept as state.json.broken instead of being
    replaced by an empty state."""
    with locked():
        path = _state_path()
        state = {}
        if path.exists():
            try:
                state = read_json(path)
            except (OSError, json.JSONDecodeError):
                _retry(lambda: os.replace(path, path.with_name("state.json.broken")))
            if not isinstance(state, dict):
                state = {}
        if change:
            change(state)
        state.update(changes)
        write_json(path, state)
        return state


def project_dir(project):
    """Last folder used for a project, or None."""
    return load_state().get("project_dirs", {}).get(project)


def set_project_dir(project, folder):
    update_state(lambda state: state.setdefault("project_dirs", {}).__setitem__(project, str(folder)))


def list_projects():
    return sorted(
        p.stem for p in voiceprints_dir().glob("*.json")
        if not p.stem.endswith(".audit_ok")
    )


# Not valid in file names on Windows (and "/" nowhere)
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def clean_name(text):
    """A text made safe as a file name on Windows and Linux: invalid
    characters become "_", no trailing dots or spaces."""
    text = _INVALID.sub("_", text or "").strip().rstrip(". ")
    return "" if text in ("", ".", "..") else text


def check_project_name(name):
    """The name stripped, or ValueError if it can't be a project (it names a file)."""
    name = (name or "").strip()
    if not name:
        raise ValueError(_("The project needs a name"))
    if clean_name(name) != name or name.lower() in _RESERVED or name.endswith(".audit_ok") or len(name) > 60:
        raise ValueError(_("{name} can't be a project name: use letters, numbers, spaces, - or _", name=name))
    return name


def create_project(name):
    """Creates the project's (empty) voice library if it doesn't exist.
    Returns the clean name; ValueError if it's not valid."""
    name = check_project_name(name)
    path = voiceprints_dir() / f"{name}.json"
    if not path.exists():
        write_json(path, {})
    return name


# ── Secrets (AssemblyAI and Hugging Face keys) ───────────────────────────────

def _read_env(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def read_secret(name):
    """The environment variable first; otherwise secrets.env in the data folder."""
    return os.environ.get(name) or _read_env(secrets_path()).get(name)


def save_secret(name, value):
    """Save (or delete, with an empty value) a key in secrets.env, changing
    only its own line: the rest of the file (other keys, comments) is kept.
    secrets.env may be a link to a .env you already use for other things."""
    path = secrets_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    new, done = [], False
    for line in lines:
        if line.strip().split("=", 1)[0].strip() == name and "=" in line and not line.lstrip().startswith("#"):
            if value and not done:
                new.append(f"{name}={value}")
                done = True
            continue
        new.append(line)
    if value and not done:
        new.append(f"{name}={value}")
    target = path.resolve()  # if it's a link, write the linked file
    target.write_text("\n".join(new) + "\n", encoding="utf-8")
    if os.name == "posix":
        target.chmod(0o600)


# ── Glossary (proper names and terms, to improve transcription) ──────────────

def read_glossary():
    """Glossary lines without comments or blanks. Each line may hold several
    comma-separated terms."""
    path = glossary_path()
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


INITIAL_GLOSSARY = N_("""\
# Glossary: proper names and terms that come up in your meetings.
# It helps the transcription spell them right. One or more per line,
# separated by commas. Lines starting with # are ignored.
""")
