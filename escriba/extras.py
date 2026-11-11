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
GPU_SIZE_GB = 5    # torch for CUDA 12 with its libraries (cuBLAS, cuDNN...): estimated from uv's plan
NEEDED_GB = 3      # the packages plus room for a whisper model
GPU_NEEDED_GB = 6
TORCH = ("torch", "torchaudio", "torchcodec")   # what changes between the CPU and the GPU builds


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


def local_job_running():
    """A local transcription in progress (it has torch's files open)."""
    from . import config, jobs
    return any(job.get("engine") == "local" and jobs.is_alive(job["pid"])
               for job in config.load_state().get("jobs", []))


def manual_command():
    """What to run by hand when it can't be done from here."""
    if os.name == "nt":
        return "powershell -ExecutionPolicy Bypass -File install.ps1 -Local"
    return 'uv tool install --force --python 3.11 "escriba[local] @ <escriba folder or URL>"'


def _pinned(free=()):
    """name==version of everything installed in this environment, except
    escriba and the `free` ones."""
    pins = set()
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name and name.lower() != "escriba" and name.lower() not in free:
            pins.add(f"{name}=={dist.version}")
    return sorted(pins)


def command(uv, constraints, gpu=False):
    cmd = [uv, "pip", "install", "--python", sys.executable, "--constraint", str(constraints)]
    if gpu:
        from .gpu import TORCH_BACKEND
        # Also when local mode is already there with the CPU torch: replace it
        cmd += ["--torch-backend", TORCH_BACKEND]
        for name in TORCH:
            cmd += ["--reinstall-package", name]
    else:
        cmd += ["--torch-backend", "cpu"]
    return cmd + requirements()


def install(output=print, gpu=False):
    """Installs local mode (with gpu, torch's CUDA 12 build, experimental);
    `output` receives each line uv prints. Returns True if it ended well (and
    then local mode works without restarting). Don't switch torch while a
    local transcription is running: on Windows its files are in use."""
    uv = find_uv()
    if not uv:
        raise FileNotFoundError("uv")
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "constraints.txt"
        constraints.write_text("\n".join(_pinned(TORCH if gpu else ())) + "\n", encoding="utf-8")
        cmd = command(uv, constraints, gpu)
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", **options)
        for line in proc.stdout:
            output(line.rstrip())
        ok = proc.wait() == 0
    importlib.invalidate_caches()
    return ok
