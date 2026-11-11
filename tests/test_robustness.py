"""Fixes from the pre-publication review: they must not come back."""
import threading

import numpy as np
import pytest

from escriba import config, jobs, meetings, record, review, speakers, voiceprints
from conftest import emb


def test_concurrent_state_updates_lose_nothing():
    config.update_state(project_dirs={"keep": "/x"})
    errors = []

    def work(i):
        try:
            for j in range(30):
                config.update_state(lambda s, k=f"t{i}_{j}": s.setdefault("seen", []).append(k))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    state = config.load_state()
    assert not errors
    assert state["project_dirs"] == {"keep": "/x"} and len(state["seen"]) == 120


def test_a_broken_state_file_is_kept_aside(data):
    config.update_state(last_project="a")
    (data / "state.json").write_text("{not json", encoding="utf-8")
    config.update_state(last_project="b")
    assert (data / "state.json.broken").read_text(encoding="utf-8") == "{not json"


def test_correcting_one_cluster_keeps_the_other_with_the_same_name(tmp_path):
    out = tmp_path / "m.txt"
    sidecar = tmp_path / "m.speakers.json"
    clusters = {spk: {"name": "Ana", "embedding": emb(i).tolist(), "origin": None}
                for i, spk in enumerate(("S1", "S2"))}
    config.write_json(sidecar, {"project": "p", "clusters": clusters})
    segments = [(0, 2, "one"), (3, 5, "two"), (6, 8, "three")]
    turns = [(0, 2.5, "S1"), (2.5, 5.5, "S2"), (5.5, 9, "S1")]
    speakers.write_transcript(str(out), segments, turns, {"S1": "Ana", "S2": "Ana"})
    review.decide(sidecar, "S2", "Bea")
    text = out.read_text(encoding="utf-8")
    assert "[0s] Ana:" in text and "[3s] Bea:" in text and "[6s] Ana:" in text


def test_a_new_recording_never_reuses_a_meeting_name(tmp_path):
    (tmp_path / "2026-01-01_x.opus").write_bytes(b"")  # archived meeting with that name
    target = record.free_target(tmp_path, "2026-01-01_x")
    assert target.name == "2026-01-01_x_2.wav"
    assert record.default_name("a/b: c?").endswith("_a_b_ c_")


@pytest.mark.parametrize("name", ["../x", "a/b", "c:d", "con", " ", "x."])
def test_invalid_project_names(name):
    with pytest.raises(ValueError):
        config.create_project(name)


def test_project_names_are_stripped():
    assert config.create_project("  client x ") == "client x"
    assert "client x" in config.list_projects()


def test_undo_never_drops_samples_added_after_it():
    voiceprints.add_sample("p", "Ana", emb(1))
    sample_id = voiceprints.load_samples("p")["Ana"][0]["id"]
    voiceprints.delete_sample("p", "Ana", sample_id)
    assert voiceprints.has_backup("p")
    voiceprints.add_sample("p", "Bea", emb(2))   # a review afterwards
    assert not voiceprints.has_backup("p")


def test_a_meeting_being_transcribed_is_not_deleted(wav, monkeypatch):
    audio = wav()
    monkeypatch.setattr(jobs, "running_audio", lambda: {str(audio.resolve())})
    with pytest.raises(RuntimeError):
        meetings.delete(audio)
    assert audio.exists()


def test_finished_jobs_are_seen_by_every_window(wav, monkeypatch):
    audio = wav()
    audio.with_suffix(".txt").write_text("x", encoding="utf-8")
    config.update_state(jobs=[{"audio": str(audio), "log": "l", "pid": 999999, "engine": "cloud"}])
    monkeypatch.setattr(jobs, "is_alive", lambda pid: False)
    for _window in range(2):
        assert [status for _j, status, _t in jobs.check_jobs()] == ["done"]
    assert jobs.running_audio() == set()


def test_a_failing_voice_library_keeps_the_transcript(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("damaged library")

    monkeypatch.setattr(speakers, "name_speakers", broken)
    assert speakers.safe_name_speakers(tmp_path / "a.wav", tmp_path / "a.txt", [(0, 1, "S1")], "p", []) is None


def test_enroll_rejects_an_empty_clip(wav):
    audio = wav(seconds=2)
    with pytest.raises(ValueError):
        review.enroll(audio, 5, 6, "Ana", "p")
    assert np.isfinite(review.enroll(audio, 0, 1.5, "Ana", "p")[0])
