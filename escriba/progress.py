"""Progress of transcription, diarization, compression and upload.

In a terminal it draws rich bars (percentage, elapsed and remaining time). When
the output goes to a log (background jobs), it writes a line every 5% in a
fixed format that doesn't depend on the interface language, so jobs.py can
read it back:

    [progress] transcribe 45% 1:00 ~1:13
    [phase] diarizing
"""
import sys
import time

from .i18n import N_, _

PHASES = {
    "transcribe": N_("Transcribing"),
    "segment": N_("Segmenting voices"),
    "embed": N_("Identifying speakers"),
    "compress": N_("Compressing audio"),
    "upload": N_("Uploading audio"),
}


def mmss(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def phase(name):
    """Marks a step in the log (loading_model, diarizing, compressing,
    cloud_waiting, cloud_done). Nothing in a terminal: there the user sees the
    translated messages."""
    if not sys.stdout.isatty():
        print(f"[phase] {name}", flush=True)


class Progress:
    def __init__(self):
        self.tty = sys.stdout.isatty()
        self._tasks = {}  # key -> rich task id | (start, last % printed)
        if self.tty:
            from rich.progress import (
                BarColumn, Progress, TaskProgressColumn, TextColumn,
                TimeElapsedColumn, TimeRemainingColumn,
            )
            self._rich = Progress(
                TextColumn("{task.description:<24}"), BarColumn(), TaskProgressColumn(),
                TimeElapsedColumn(), TextColumn(_("left")), TimeRemainingColumn(),
            )
            self._rich.start()

    def update(self, key, done, total):
        """key: one of PHASES."""
        if not total:
            return
        if self.tty:
            if key not in self._tasks:
                self._tasks[key] = self._rich.add_task(_(PHASES[key]), total=total)
            self._rich.update(self._tasks[key], completed=done, total=total)
            return

        start, last = self._tasks.setdefault(key, (time.time(), -5))
        pct = min(100, int(100 * done / total))
        if pct == last or (pct - last < 5 and pct < 100):
            return
        elapsed = time.time() - start
        left = f" ~{mmss(elapsed * (100 - pct) / pct)}" if 0 < pct < 100 else ""
        print(f"[progress] {key} {pct}% {mmss(elapsed)}{left}", flush=True)
        self._tasks[key] = (start, pct)

    def pyannote_hook(self):
        """Hook for Pipeline(...)(audio, hook=...): only the steps that report progress."""
        keys = {"segmentation": "segment", "embeddings": "embed"}

        def hook(step, artifact, file=None, total=None, completed=None):
            if total is not None and completed is not None and step in keys:
                self.update(keys[step], completed, total)
        return hook

    def close(self):
        if self.tty:
            self._rich.stop()
