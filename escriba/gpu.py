"""NVIDIA GPU for local mode (experimental: not tested on real hardware by the
authors; every failure falls back to the CPU).

- Detection without importing torch (the web shouldn't load 1 GB to draw a
  card): nvidia-smi for the card and driver, torch's files for its build.
- faster-whisper's engine (CTranslate2 4.x) needs CUDA 12 (cuBLAS 12 and
  cuDNN 9): torch is installed from the cu126 index, never CUDA 13, and its
  libraries are made visible to CTranslate2 before loading whisper.
"""
import ctypes
import glob
import importlib.util
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import config

TORCH_BACKEND = "cu126"   # CUDA 12.6: what CTranslate2 4.x accepts, and the oldest drivers
# Oldest driver for CUDA 12.x (minor version compatibility), per platform
MIN_DRIVER = (528, 33) if os.name == "nt" else (525, 60)
SETTINGS = ("auto", "never")


@lru_cache(maxsize=1)
def nvidia():
    """{"name", "driver", "memory_mb", "driver_ok"} of the first NVIDIA card, or None."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run([smi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_smi(out.stdout) if out.returncode == 0 else None


def parse_smi(text):
    line = text.strip().splitlines()[0] if text.strip() else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None
    name, driver, memory = parts[:3]
    try:
        version = tuple(int(x) for x in driver.split(".")[:2])
    except ValueError:
        version = (0, 0)
    try:
        memory_mb = int(float(memory))
    except ValueError:
        memory_mb = 0
    return {"name": name, "driver": driver, "memory_mb": memory_mb, "driver_ok": version >= MIN_DRIVER}


def torch_has_cuda():
    """Whether the installed torch is a CUDA build, looking at its files."""
    spec = importlib.util.find_spec("torch")
    if not spec or not spec.submodule_search_locations:
        return False
    lib = Path(list(spec.submodule_search_locations)[0]) / "lib"
    return bool(glob.glob(str(lib / "*torch_cuda*")))


def setting():
    """"auto" (try the GPU) or "never". ESCRIBA_GPU overrides the saved one."""
    value = os.environ.get("ESCRIBA_GPU") or config.load_state().get("gpu", "auto")
    return value if value in SETTINGS else "auto"


def will_try():
    """Whether local mode will try the GPU (it may still fall back to the CPU)."""
    card = nvidia()
    return bool(card and card["driver_ok"] and setting() == "auto" and torch_has_cuda())


def whisper_compute_type(memory_mb):
    # float16 is the fastest; with little memory int8_float16 takes about half
    return "float16" if memory_mb >= 4000 else "int8_float16"


def prepare_libraries():
    """Makes the CUDA libraries that came with torch visible to CTranslate2,
    which looks for cublas/cudnn by name. Importing torch loads them on Linux;
    on Windows its DLL folders must be added to the search path."""
    import torch

    site = Path(torch.__file__).resolve().parent.parent
    folders = [Path(torch.__file__).resolve().parent / "lib"]
    folders += [Path(p) for p in glob.glob(str(site / "nvidia" / "*" / ("bin" if os.name == "nt" else "lib")))]
    if os.name == "nt":
        for folder in folders:
            if folder.is_dir():
                os.add_dll_directory(str(folder))
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    else:
        for pattern in ("libcublasLt.so.12", "libcublas.so.12", "libcudnn*.so.9"):
            for folder in folders:
                for lib in sorted(glob.glob(str(folder / pattern))):
                    try:
                        ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass
    return torch


def cuda_available():
    """For the transcription process: True if it should try the GPU."""
    if setting() == "never" or not torch_has_cuda():
        return False
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def describe():
    """Card name for the log."""
    card = nvidia()
    return card["name"] if card else "CUDA"

