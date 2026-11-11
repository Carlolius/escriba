"""Recording meetings: mixes what plays on the PC with your microphone.

Uses soundcard, which on Windows records "what you hear" through WASAPI
loopback and on Linux through the PipeWire/PulseAudio monitor, so the same code
works on both. Each source is captured in its own thread and a third thread
mixes them and writes a 16 kHz mono WAV (what whisper and voice identification
need) while recording, so if something hangs, what was recorded is already on
disk.
"""
import queue
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config
from .i18n import _

SR = 16000
STOP_GRACE = 3   # seconds a stuck capture may delay stopping
CHUNK = SR // 10           # each source delivers 0.1 s chunks
MAX_LAG = SR               # if a source falls >1 s behind, it's padded with silence
MUTED_MIC_WARNING_S = 10   # mic at absolute zero for this long -> warning


def _sc():
    import soundcard
    return soundcard


def _loopback_of(speaker):
    """The "microphone" that captures what plays through that speaker."""
    sc = _sc()
    candidates = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    for m in candidates:
        if m.id == speaker.id or m.id.startswith(speaker.id) or speaker.name in m.name:
            return m
    return None


def list_devices():
    """{"outputs": [(name, is_default)], "mics": [(name, is_default)]}"""
    sc = _sc()
    default_out, default_mic = sc.default_speaker(), sc.default_microphone()
    return {
        "outputs": [(s.name, s.id == default_out.id) for s in sc.all_speakers()],
        "mics": [(m.name, m.id == default_mic.id) for m in sc.all_microphones()],
    }


def _find(devices, name):
    return next((d for d in devices if d.name == name or d.id == name), None)


def resolve_devices(output=None, mic=None):
    """(loopback, mic) from names; None = the default one."""
    sc = _sc()
    spk = _find(sc.all_speakers(), output) if output else sc.default_speaker()
    if spk is None:
        raise ValueError(_("Audio output '{name}' not found", name=output))
    loop = _loopback_of(spk)
    if loop is None:
        raise ValueError(_("Can't record what plays through '{name}' (no loopback)", name=spk.name))
    device = _find(sc.all_microphones(), mic) if mic else sc.default_microphone()
    if device is None:
        raise ValueError(_("Microphone '{name}' not found", name=mic))
    return loop, device


class Recording:
    """r = Recording(path); r.start(); ... r.stop()

    While recording: r.seconds, r.levels ({"system", "mic"}: RMS volume of the
    last chunk) and r.warnings (list of texts, e.g. muted microphone)."""

    def __init__(self, target, output=None, mic=None):
        self.target = Path(target)
        self.loop, self.mic = resolve_devices(output, mic)
        self.levels = {"system": 0.0, "mic": 0.0}
        self.warnings = []
        self.errors = []
        self._queues = {"system": queue.Queue(), "mic": queue.Queue()}
        self._alive = {"system": True, "mic": True}
        self._stop = threading.Event()
        self._threads = []
        self._written = 0
        self._mic_silent_since = None

    @property
    def seconds(self):
        return self._written / SR

    def start(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        # "x": fails if the file exists, instead of overwriting another recording
        self._file = sf.SoundFile(str(self.target), "x", samplerate=SR, channels=1, subtype="PCM_16")
        for name, device in (("system", self.loop), ("mic", self.mic)):
            self._threads.append(threading.Thread(target=self._capture, args=(name, device), daemon=True))
        self._threads.append(threading.Thread(target=self._mix, daemon=True))
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        # The mixer is the only one writing the file: it ends by itself at
        # most STOP_GRACE seconds later, even if a capture is stuck
        mixer = self._threads[-1]
        mixer.join(timeout=STOP_GRACE + 5)
        if not mixer.is_alive():
            self._file.close()
        return self.target

    def _capture(self, name, device):
        try:
            # blocksize: without it PulseAudio delivers ~2 s blocks, and the last one is lost on stop
            with device.recorder(samplerate=SR, channels=1, blocksize=CHUNK) as r:
                while not self._stop.is_set():
                    data = r.record(numframes=CHUNK)
                    data = data[:, 0] if data.ndim > 1 else data
                    self.levels[name] = float(np.sqrt(np.mean(data ** 2))) if len(data) else 0.0
                    self._queues[name].put(data.astype("float32"))
        except Exception as e:  # device unplugged, etc.: the other source goes on
            self.errors.append(f"{name}: {e}")
        finally:
            self._alive[name] = False
            self.levels[name] = 0.0

    def _mix(self):
        pending = {"system": np.zeros(0, "float32"), "mic": np.zeros(0, "float32")}
        last_flush = time.time()
        stopped_at = None
        while True:
            stopping = self._stop.is_set()
            if stopping and stopped_at is None:
                stopped_at = time.time()
            # Before draining the queues: if no capture is alive any more, what's
            # left in them is the last of it and we can finish after writing it.
            capturing = any(t.is_alive() for t in self._threads[:2])
            for name, q in self._queues.items():
                chunks = []
                while True:
                    try:
                        chunks.append(q.get_nowait())
                    except queue.Empty:
                        break
                if chunks:
                    pending[name] = np.concatenate([pending[name], *chunks])

            a, b = pending["system"], pending["mic"]
            # A dead or stuck source can't hold back the other: pad it with silence
            for x, y, name in ((a, b, "system"), (b, a, "mic")):
                if len(y) - len(x) > MAX_LAG or (not self._alive[name] and len(y) > len(x)) or stopping:
                    pending[name] = np.concatenate([x, np.zeros(max(0, len(y) - len(x)), "float32")])
            a, b = pending["system"], pending["mic"]

            n = min(len(a), len(b))
            if n:
                self._file.write(np.clip(a[:n] + b[:n], -1.0, 1.0))
                self._written += n
                pending["system"], pending["mic"] = a[n:], b[n:]
                self._watch_mic(b[:n])
            if time.time() - last_flush > 5:
                self._file.flush()  # header up to date: if it's cut, the WAV still works
                last_flush = time.time()
            if stopping and (not capturing or time.time() - stopped_at > STOP_GRACE):
                break
            time.sleep(0.1)

    def _watch_mic(self, data):
        if np.any(data != 0):
            self._mic_silent_since = None
            return
        if self._mic_silent_since is None:
            self._mic_silent_since = self._written
        elif (self._written - self._mic_silent_since) / SR > MUTED_MIC_WARNING_S:
            warning = _("The microphone picks up nothing: is it muted, or the wrong one?")
            if warning not in self.warnings:
                self.warnings.append(warning)


def from_preferences(target):
    """Recording with the output and mic chosen in Settings. If they're gone
    (headphones unplugged...), with the system ones and a warning.
    Returns (recording, warning | None)."""

    state = config.load_state()
    output, mic = state.get("output_device"), state.get("mic")
    try:
        return Recording(target, output=output, mic=mic), None
    except ValueError as e:
        if not (output or mic):
            raise
        return Recording(target), _("{error}: using the system ones", error=e)


def default_name(description=""):
    from datetime import datetime
    now = datetime.now()
    return f"{now:%Y-%m-%d}_{config.clean_name(description) or _('meeting') + '_' + now.strftime('%H%M')}"


def free_target(folder, stem):
    """folder/stem.wav, or stem_2.wav, stem_3.wav... if a meeting with that
    name already exists (also archived as .opus, or just its transcript):
    a new recording never overwrites nor inherits another meeting's files."""
    from . import meetings

    folder = Path(folder)
    target, n = folder / f"{stem}.wav", 2
    while meetings.files_of(target):
        target, n = folder / f"{stem}_{n}.wav", n + 1
    return target
