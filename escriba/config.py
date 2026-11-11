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


def write_json(path, data, indent=2):
    """Atomic write: the terminal menu, the web and background jobs may read a
    file while another one writes it."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ── State (last project and folders, running jobs, preferences) ──────────────
# Keys: last_project, project_dirs {project: folder}, jobs [{audio, log, pid}],
# theme (system/light/dark), language, output_device, mic.

def load_state():
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    write_json(_state_path(), state)


def update_state(**changes):
    """Read, change and save: never save an old state on top of the jobs that
    another window may have added in the meantime."""
    state = load_state()
    state.update(changes)
    save_state(state)
    return state


def project_dir(project):
    """Last folder used for a project, or None."""
    return load_state().get("project_dirs", {}).get(project)


def set_project_dir(project, folder):
    state = load_state()
    state.setdefault("project_dirs", {})[project] = str(folder)
    save_state(state)


def list_projects():
    return sorted(
        p.stem for p in voiceprints_dir().glob("*.json")
        if not p.stem.endswith(".audit_ok")
    )


def create_project(name):
    path = voiceprints_dir() / f"{name}.json"
    if not path.exists():
        path.write_text("{}", encoding="utf-8")


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
