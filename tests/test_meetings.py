"""Meetings list and delete; renaming people; structured progress."""
import json

import numpy as np
import pytest

from conftest import emb
from escriba import config, jobs, meetings, review, voiceprints


def test_meeting_states(meeting, wav):
    audio, sidecar, _txt = meeting
    untranscribed = wav("new.wav")
    found = {m["audio"].name: m["status"] for m in meetings.list_meetings(audio.parent)}
    assert found == {"meeting.wav": "to_review", "new.wav": "untranscribed"}
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["reviewed"] = True
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    assert meetings.status(audio) == "reviewed"
    assert meetings.list_meetings(audio.parent, recording=untranscribed)[0]["status"] == "recording"


def test_delete_meeting_with_or_without_its_samples(meeting):
    audio, sidecar, txt = meeting
    origin = {"audio": str(audio), "start": 0.0, "end": 2.0}
    voiceprints.add_sample("test", "Ana", emb(1), origin=origin)
    voiceprints.add_sample("test", "Bea", emb(2), origin={"audio": "/elsewhere.wav", "start": 0, "end": 1})
    assert voiceprints.samples_from_audio(audio) == {"test": 1}
    assert meetings.delete(audio, delete_samples=True) == (3, 1)
    assert not audio.exists() and not sidecar.exists() and not txt.exists()
    assert list(voiceprints.load_samples("test")) == ["Bea"]
    voiceprints.restore_backup("test")
    assert sorted(voiceprints.load_samples("test")) == ["Ana", "Bea"]


def test_rename_person_and_in_transcripts(meeting):
    audio, sidecar, txt = meeting
    config.set_project_dir("test", audio.parent)
    voiceprints.add_sample("test", "Ana", emb(1))
    voiceprints.add_sample("test", "Anna", emb(5))
    assert voiceprints.rename_person("test", "Ana", "Anna") == 2  # same person: joined
    assert list(voiceprints.load_samples("test")) == ["Anna"]
    assert review.rename_in_transcripts("test", "Ana", "Anna") == 1
    assert "[3s] Anna:" in txt.read_text(encoding="utf-8")
    names = {c["name"] for c in review.load(sidecar)["clusters"].values()}
    assert names == {"Speaker 1", "Anna"}
    assert voiceprints.rename_person("test", "Nobody", "X") is None


def test_progress_info(tmp_path):
    log = tmp_path / "t.log"
    log.write_text("[progress] transcribe 50% 1:00 ~1:00\n", encoding="utf-8")
    info = jobs.progress_info(log)
    assert (info["engine"], info["step"], info["pct"]) == ("local", "transcribe", 50)
    assert np.isclose(info["left"], 60 + 120 * jobs.DIARIZATION_RATIO)
    log.write_text("[phase] compressing\n[progress] upload 35% 0:05 ~0:10\n", encoding="utf-8")
    info = jobs.progress_info(log)
    assert (info["engine"], info["step"], info["pct"]) == ("cloud", "upload", 35)
    log.write_text("", encoding="utf-8")
    assert jobs.progress_info(log, "cloud")["step"] == "compress"


def test_rename_meeting_keeps_transcript_and_samples(meeting):
    audio, sidecar, txt = meeting
    log = audio.with_name(audio.stem + "_transcribe.log")
    log.write_text("done", encoding="utf-8")
    voiceprints.add_sample("test", "Ana", emb(1), origin={"audio": str(audio), "start": 0.0, "end": 2.0})
    new = meetings.rename(audio, "  Weekly v1.2.wav ")
    assert new == audio.with_name("Weekly v1.2.wav") and new.exists()
    assert sorted(p.name for p in meetings.files_of(new)) == [
        "Weekly v1.2.speakers.json", "Weekly v1.2.txt", "Weekly v1.2.wav", "Weekly v1.2_transcribe.log"]
    assert not any(p.exists() for p in (audio, sidecar, txt, log))
    assert voiceprints.samples_from_audio(new) == {"test": 1}
    clusters = json.loads(new.with_suffix(".speakers.json").read_text(encoding="utf-8"))["clusters"]
    assert {c["origin"]["audio"] for c in clusters.values()} == {str(new.resolve())}
    assert meetings.list_meetings(new.parent)[0]["status"] == "to_review"


def test_rename_meeting_refuses(meeting, wav, monkeypatch):
    audio, _sidecar, _txt = meeting
    wav("taken.wav")
    for bad in ("", "  ", "a/b", "what?", "dots.", "nul", "tab\there"):
        with pytest.raises(ValueError):
            meetings.rename(audio, bad)
    with pytest.raises(FileExistsError):
        meetings.rename(audio, "taken")
    with pytest.raises(RuntimeError):
        meetings.rename(audio, "other", recording=audio)
    monkeypatch.setattr(jobs, "running_audio", lambda: {str(audio.resolve())})
    with pytest.raises(RuntimeError):
        meetings.rename(audio, "other")
    assert meetings.rename(audio, "meeting") == audio and audio.exists()
