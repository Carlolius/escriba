"""Renaming and deleting projects."""
import json

import pytest

from conftest import emb
from escriba import config, projects, review, voiceprints


@pytest.fixture
def project(meeting):
    """The "test" project with a person and the meeting's folder."""
    audio, sidecar, _txt = meeting
    config.create_project("test")
    voiceprints.add_sample("test", "Ana", emb(1))
    config.set_project_dir("test", audio.parent)
    config.update_state(last_project="test")
    return sidecar


def test_rename_moves_everything(project):
    voiceprints.delete_person("test", "Ana")   # leaves a .bak to undo
    assert projects.rename("test", "acme") == 1
    assert config.list_projects() == ["acme"]
    assert voiceprints.has_backup("acme")
    state = config.load_state()
    assert state["last_project"] == "acme" and "acme" in state["project_dirs"]
    assert json.loads(project.read_text())["project"] == "acme"
    assert review.pending() and review.pending()[0][0] == "acme"


def test_rename_refuses_bad_or_taken_names(project):
    config.create_project("other")
    with pytest.raises(ValueError):
        projects.rename("test", "Other")
    with pytest.raises(ValueError):
        projects.rename("test", "a/b")
    assert set(config.list_projects()) == {"test", "other"}


def test_delete_keeps_the_recordings(project):
    projects.delete("test")
    assert config.list_projects() == []
    assert "last_project" not in config.load_state()
    assert project.exists() and project.with_name("meeting.wav").exists()
    assert review.pending() == []


def test_refuses_while_transcribing(project, monkeypatch):
    config.update_state(jobs=[{"audio": "x.wav", "log": "x.log", "pid": 1, "project": "test"}])
    monkeypatch.setattr("escriba.jobs.is_alive", lambda pid: True)
    with pytest.raises(RuntimeError):
        projects.rename("test", "acme")
    with pytest.raises(RuntimeError):
        projects.delete("test")


def test_summary(project):
    assert projects.summary() == [{"name": "test", "folder": config.project_dir("test"), "people": 1,
                                   "samples": 1}]
