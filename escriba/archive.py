"""Compresses to Opus the audio of meetings already transcribed and reviewed.

A .wav is archived once it has its .txt and, if it has a .speakers.json, that
sidecar is reviewed. It's converted to .opus (mono, ~16 kbps: ~15x smaller
than the WAV, with no audible difference in voice nor in the voiceprints), its
duration is checked, the paths pointing at the .wav are updated (samples in
the voice libraries and their .bak, and the sidecar) and the .wav is deleted.

It runs on its own when the review of a meeting is finished; to convert
everything already reviewed at once: escriba archive (see --help).
"""
import json
from pathlib import Path

from . import audio as audio_util
from . import config
from .i18n import _, _n


def sidecar_path(wav):
    return wav.with_suffix(".speakers.json")


def ready_to_archive(wav):
    if not wav.with_suffix(".txt").exists():
        return False
    sidecar = sidecar_path(wav)
    if not sidecar.exists():
        return True
    try:
        return bool(json.loads(sidecar.read_text(encoding="utf-8")).get("reviewed"))
    except (OSError, json.JSONDecodeError):
        return False


def _replace_in_samples(samples, old, new):
    changes = 0
    for s in samples:
        origin = s.get("origin") if isinstance(s, dict) else None
        if origin and Path(origin["audio"]).resolve() == old:
            origin["audio"] = str(new)
            changes += 1
    return changes


def update_paths(old, new):
    """Changes old -> new in the samples of every voice library (also in the
    .bak, so that undoing doesn't bring dead paths back) and in the meeting's
    own sidecar. Returns how many references it changed."""
    old, new = Path(old).resolve(), Path(new).resolve()
    total = 0
    for path in sorted(config.voiceprints_dir().glob("*.json*")):
        if ".audit_ok" in path.name:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        changes = sum(_replace_in_samples(s, old, new) for s in data.values() if isinstance(s, list))
        if changes:
            path.write_text(json.dumps(data), encoding="utf-8")
            total += changes

    # The sidecar may still be next to the old path or have moved with the audio
    for sidecar in {sidecar_path(old), sidecar_path(new)}:
        if not sidecar.exists():
            continue
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        changes = _replace_in_samples(data.get("clusters", {}).values(), old, new)
        if changes:
            config.write_json(sidecar, data)
            total += changes
    return total


def archive(wav):
    """wav -> opus, updates references and deletes the wav.
    Returns (opus_path, bytes_saved, references_changed)."""
    wav = Path(wav).resolve()
    opus = wav.with_suffix(".opus")
    tmp = opus.with_name(opus.name + ".tmp")
    dur_wav = audio_util.duration(wav)
    audio_util.compress_opus(wav, tmp)
    dur_opus = audio_util.duration(tmp) or 0
    if abs(dur_wav - dur_opus) > 0.5:
        tmp.unlink()
        raise RuntimeError(_("{name}: different duration after converting ({wav:.1f}s vs {opus:.1f}s)",
                             name=wav.name, wav=dur_wav, opus=dur_opus))
    tmp.rename(opus)
    saved = wav.stat().st_size - opus.stat().st_size
    refs = update_paths(wav, opus)
    wav.unlink()
    return opus, saved, refs


def project_dirs():
    """Last folder of each project (the same ones the menu and the web look in)."""
    return [Path(d) for d in config.load_state().get("project_dirs", {}).values()]


def archive_dirs(dirs, dry_run=False):
    wavs = sorted({w.resolve() for d in dirs if d.exists() for w in d.rglob("*.wav")})
    ready = [w for w in wavs if ready_to_archive(w)]
    for w in wavs:
        if w not in ready:
            print(_("  stays as WAV (not transcribed or not reviewed): {path}", path=w))

    total_saved = 0
    for w in ready:
        if dry_run:
            print(_("  would convert: {path} ({mb:.0f} MB)", path=w, mb=w.stat().st_size / 1e6))
            continue
        print(f"{w.name}:", flush=True)
        opus, saved, refs = archive(w)
        total_saved += saved
        print("  ✓ " + _n("{name}: -{mb:.0f} MB, {n} reference updated", "{name}: -{mb:.0f} MB, {n} references updated",
                          refs, name=opus.name, mb=saved / 1e6))
    if not dry_run:
        print(_n("{n} audio file archived, {mb:.0f} MB freed", "{n} audio files archived, {mb:.0f} MB freed",
                 len(ready), mb=total_saved / 1e6))
