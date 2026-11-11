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
import time
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
    job = {"audio": str(audio), "log": str(log), "pid": proc.pid, "project": project, "engine": engine,
           "started": time.time()}
    config.update_state(lambda state: state.setdefault("jobs", []).append(job))
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


# Steps of each engine, as shown in the web
STEPS = {"local": ("transcribe", "speakers"), "cloud": ("compress", "upload", "cloud", "speakers")}


def progress_info(log, engine=None):
    """Where a background transcription is, from the lines progress.py and
    cloud.py write to its log:

    {"engine": "local" | "cloud", "step": one of STEPS[engine],
     "pct": 0-100 or None (no percentage for this step), "elapsed": seconds
     or None, "left": estimated seconds to the end or None, "text": the same
     in one line}"""
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = None
    if engine not in STEPS:
        cloud = lines and any(line.startswith(("[cloud]", "[phase] cloud", "[phase] compressing", "[progress] upload",
                                               "[progress] compress")) for line in lines)
        engine = "cloud" if cloud else "local"
    info = {"engine": engine, "step": STEPS[engine][0], "pct": None, "elapsed": None, "left": None}
    if lines is None:
        return dict(info, text=_("no log"))
    for line in reversed(lines):
        if m := RE_PHASE.match(line):
            step, text = {
                "cloud_done": ("speakers", _("identifying voices (cloud part done)")),
                "cloud_waiting": ("cloud", _("processing in the cloud")),
                "diarizing": ("speakers", _("preparing speaker identification (step 2/2)")),
                "compressing": ("compress", _("compressing audio (cloud)")),
                "loading_model": ("transcribe", _("loading model...")),
            }.get(m.group(1), (None, None))
            if text:
                return dict(info, step=step, text=text)
            continue
        if m := RE_CLOUD.match(line):
            minutes, seconds = m.group(1).split(":")
            return dict(info, step="cloud", elapsed=int(minutes) * 60 + int(seconds),
                        text=_("processing in the cloud ({elapsed})", elapsed=m.group(1)))
        m = RE_PROGRESS.match(line)
        if not m:
            continue
        key, pct = m.group(1), int(m.group(2))
        elapsed = int(m.group(3)) * 60 + int(m.group(4))
        info.update(pct=pct, elapsed=elapsed)
        if key == "compress":
            return dict(info, step="compress", text=_("compressing audio {pct}% (cloud)", pct=pct))
        if key == "upload":
            return dict(info, step="upload", text=_("uploading audio {pct}% (cloud)", pct=pct))
        if key == "transcribe":
            if pct == 0:
                return dict(info, step="transcribe", text=_("transcribing 0% (step 1/2)"))
            # Left: the rest of the transcription + the whole diarization,
            # estimated from how long the transcription will take.
            total = elapsed * 100 / pct
            left = total - elapsed + total * DIARIZATION_RATIO
            return dict(info, step="transcribe", left=left,
                        text=_("transcribing {pct}% (step 1/2) · ~{left} left", pct=pct, left=format_minutes(left)))
        if key == "segment" or m.group(5) is None:
            pct = 0 if key == "segment" else pct
            return dict(info, step="speakers", pct=pct, text=_("identifying speakers {pct}% (step 2/2)", pct=pct))
        left = int(m.group(5)) * 60 + int(m.group(6))
        return dict(info, step="speakers", left=left,
                    text=_("identifying speakers {pct}% (step 2/2) · ~{left} left", pct=pct, left=format_minutes(left)))
    return dict(info, text=_("starting..."))


def progress_from_log(log, engine=None):
    """Text like 'transcribing 45% (step 1/2) · ~38 min left'."""
    return progress_info(log, engine)["text"]


KEEP_FINISHED = 24 * 3600   # finished jobs stay listed for a day


def _finish(job):
    """Status of a job whose process is gone."""
    return "done" if Path(job["audio"]).with_suffix(".txt").exists() else "failed"


def check_jobs():
    """[(job, "running" | "done" | "failed", text)] of the running jobs and
    the ones finished in the last day. Finished jobs keep their status and
    end time in the state, so every window (web tabs, terminal menu) sees
    them; job["seen"] says whether the user was already told."""
    now = time.time()
    alive = {}

    def refresh(state):
        kept = []
        for job in state.get("jobs", []):
            if not job.get("status"):
                if job["pid"] not in alive:
                    alive[job["pid"]] = is_alive(job["pid"])
                if not alive[job["pid"]]:
                    job.update(status=_finish(job), ended=now)
            if job.get("status") and now - job.get("ended", now) > KEEP_FINISHED:
                continue
            kept.append(job)
        state["jobs"] = kept

    state = config.load_state()
    if any(not job.get("status") and not is_alive(job["pid"]) for job in state.get("jobs", [])) or any(
            job.get("status") and now - job.get("ended", now) > KEEP_FINISHED for job in state.get("jobs", [])):
        state = config.update_state(refresh)
    result = []
    for job in state.get("jobs", []):
        status = job.get("status") or "running"
        if status == "running":
            text = progress_from_log(job["log"], job.get("engine"))
        elif status == "done":
            text = _("ready to review speakers")
        else:
            text = _("see {log}", log=job["log"])
        result.append((job, status, text))
    return result


def mark_seen(pids):
    """The user was told these jobs finished."""
    pids = set(pids)
    if pids:
        config.update_state(lambda state: [job.update(seen=True) for job in state.get("jobs", [])
                                           if job["pid"] in pids])


def running_audio():
    """Audio files being transcribed right now."""
    return {job["audio"] for job in config.load_state().get("jobs", [])
            if not job.get("status") and is_alive(job["pid"])}


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
