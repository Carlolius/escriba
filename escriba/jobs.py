"""Background transcriptions: starting them, knowing whether they're still
alive and reading their progress from the log. Used by the terminal menu and
the web interface.

Each job is a separate process (python -m escriba transcribe ...) that goes on
even if the menu or the browser is closed, and writes its output to
<audio>_transcribe.log. The state keeps {"audio", "log", "pid"} for each one.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import psutil

from . import config
from .i18n import _

# Measured in Oct 2026 (Ryzen 5 5625U, medium + diarization): 5 min of audio
# take ~114 s to transcribe and ~250 s to diarize.
PROCESS_FACTOR = 1.25      # total time / audio duration
DIARIZATION_RATIO = 2.2    # diarization time / transcription time

# Lines written by progress.py and cloud.py (fixed format, any language)
RE_PROGRESS = re.compile(r"^\[progress\] (\w+) (\d+)% (\d+):(\d+)(?: ~(\d+):(\d+))?")
RE_CLOUD = re.compile(r"^\[cloud\] \w+ (\d+:\d+)")
RE_PHASE = re.compile(r"^\[phase\] (\w+)")


def format_minutes(seconds):
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def command(audio, project, engine, model, language):
    cmd = [sys.executable, "-m", "escriba", "transcribe", str(audio), "--project", project, "--language", language]
    if engine == "cloud":
        cmd.append("--cloud")
    else:
        cmd += ["--local", "--model", model]
    return cmd


def environment():
    """The child must find the package even when it isn't installed, and write
    the log in UTF-8 (on Windows it would be cp1252 and fail on "→")."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def start(audio, project, engine="cloud", model="medium", language="auto"):
    """Starts the transcription in the background and records it in the state."""
    audio = Path(audio).resolve()
    log = audio.with_name(audio.stem + "_transcribe.log")
    options = {}
    if os.name == "nt":
        # No console window, and out of the menu's Ctrl+C group
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        # So that a later Ctrl+C in the menu (e.g. while recording another meeting) doesn't kill it
        options["start_new_session"] = True
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(command(audio, project, engine, model, language), stdout=f,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=environment(), **options)
    state = config.load_state()
    state.setdefault("jobs", []).append({"audio": str(audio), "log": str(log), "pid": proc.pid})
    config.save_state(state)
    return log


def is_alive(pid):
    """Checking the command line avoids mistaking it for another process that
    reused the PID."""
    try:
        p = psutil.Process(pid)
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        cmd = " ".join(p.cmdline())
    except (psutil.Error, OSError):
        return False
    return "escriba" in cmd and "transcribe" in cmd


def progress_from_log(log):
    """Text like 'transcribing 45% (step 1/2) · ~38 min left', from the lines
    progress.py writes to the log."""
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return _("no log")
    for line in reversed(lines):
        if m := RE_PHASE.match(line):
            text = {
                "cloud_done": _("identifying voices (cloud part done)"),
                "cloud_waiting": _("processing in the cloud"),
                "diarizing": _("preparing speaker identification (step 2/2)"),
                "compressing": _("compressing audio (cloud)"),
                "loading_model": _("loading model..."),
            }.get(m.group(1))
            if text:
                return text
            continue
        if m := RE_CLOUD.match(line):
            return _("processing in the cloud ({elapsed})", elapsed=m.group(1))
        m = RE_PROGRESS.match(line)
        if not m:
            continue
        key, pct = m.group(1), int(m.group(2))
        elapsed = int(m.group(3)) * 60 + int(m.group(4))
        if key == "compress":
            return _("compressing audio {pct}% (cloud)", pct=pct)
        if key == "upload":
            return _("uploading audio {pct}% (cloud)", pct=pct)
        if key == "transcribe":
            if pct == 0:
                return _("transcribing 0% (step 1/2)")
            # Left: the rest of the transcription + the whole diarization,
            # estimated from how long the transcription will take.
            total = elapsed * 100 / pct
            left = total - elapsed + total * DIARIZATION_RATIO
            return _("transcribing {pct}% (step 1/2) · ~{left} left", pct=pct, left=format_minutes(left))
        if key == "segment" or m.group(5) is None:
            return _("identifying speakers {pct}% (step 2/2)", pct=0 if key == "segment" else pct)
        left = int(m.group(5)) * 60 + int(m.group(6))
        return _("identifying speakers {pct}% (step 2/2) · ~{left} left", pct=pct, left=format_minutes(left))
    return _("starting...")


def check_jobs():
    """[(job, "running" | "done" | "failed", text)]. Finished jobs are
    returned once and removed from the state."""
    state = config.load_state()
    jobs = state.get("jobs", [])
    result, still = [], []
    for job in jobs:
        if is_alive(job["pid"]):
            result.append((job, "running", progress_from_log(job["log"])))
            still.append(job)
        elif Path(job["audio"]).with_suffix(".txt").exists():
            result.append((job, "done", _("ready to review speakers")))
        else:
            result.append((job, "failed", _("see {log}", log=job["log"])))
    if len(still) != len(jobs):
        # Read again right before saving: another window may have started a job meanwhile
        state = config.load_state()
        finished = {job["pid"] for job, status, _text in result if status != "running"}
        state["jobs"] = [job for job in state.get("jobs", []) if job["pid"] not in finished]
        config.save_state(state)
    return result


def running_audio():
    return {job["audio"] for job in config.load_state().get("jobs", [])}


def untranscribed(folder, limit=30):
    """[(path, duration)] of the WAVs under `folder` that aren't transcribed
    (nor being transcribed), newest first. rglob: a project's recordings may
    be in subfolders."""
    from . import audio as audio_util

    folder = Path(folder)
    if not folder.is_dir():
        return []
    running = running_audio()
    wavs = sorted(folder.rglob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    todo = [w for w in wavs if not w.with_suffix(".txt").exists() and str(w.resolve()) not in running]
    return [(w, audio_util.duration(w)) for w in todo[:limit]]
