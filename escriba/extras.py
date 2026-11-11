"""Installing local mode (faster-whisper + pyannote) after escriba, from the
web or the terminal menu, so the base install stays small (~150 MB).

The packages are added to escriba's own environment with `uv pip install`,
with every package already installed pinned to its current version: nothing
in use is replaced, so it works while escriba is running (on Windows, files in
use can't be overwritten). Whisper's models are downloaded later, the first
time each one is used.
"""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

# Kept in sync with the "local" extra in pyproject.toml (read from there when installed)
FALLBACK = ["faster-whisper>=1.1", "pyannote.audio>=3.3"]
SIZE_GB = 1.5      # torch CPU-only + faster-whisper + pyannote, measured on Linux
NEEDED_GB = 3      # the packages plus room for a whisper model


def requirements():
    try:
        reqs = metadata.requires("escriba") or []
    except metadata.PackageNotFoundError:
        reqs = []
    local = [r.split(";")[0].strip() for r in reqs if 'extra == "local"' in r.replace("'", '"')]
    return local or FALLBACK


def find_uv():
    if path := shutil.which("uv"):
        return path
    for folder in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        for name in ("uv.exe", "uv"):
            if (folder / name).is_file():
                return str(folder / name)
    return None


def free_gb():
    return shutil.disk_usage(sys.prefix).free / 1e9


def manual_command():
    """What to run by hand when it can't be done from here."""
    if os.name == "nt":
        return "powershell -ExecutionPolicy Bypass -File install.ps1 -Local"
    return 'uv tool install --force --python 3.11 "escriba[local] @ <escriba folder or URL>"'


def _pinned():
    """name==version of everything installed in this environment."""
    pins = set()
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name and name.lower() != "escriba":
            pins.add(f"{name}=={dist.version}")
    return sorted(pins)


def install(output=print):
    """Installs local mode; `output` receives each line uv prints. Returns
    True if it ended well (and then local mode works without restarting)."""
    uv = find_uv()
    if not uv:
        raise FileNotFoundError("uv")
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "constraints.txt"
        constraints.write_text("\n".join(_pinned()) + "\n", encoding="utf-8")
        cmd = [uv, "pip", "install", "--python", sys.executable, "--torch-backend", "cpu",
               "--constraint", str(constraints), *requirements()]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", **options)
        for line in proc.stdout:
            output(line.rstrip())
        ok = proc.wait() == 0
    importlib.invalidate_caches()
    return ok
