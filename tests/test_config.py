import os

import pytest

from escriba import config


def test_data_folder_from_the_variable(data):
    assert config.data_dir() == data
    assert config.voiceprints_dir() == data / "voiceprints"


def test_save_and_read_secrets():
    assert config.read_secret("ASSEMBLYAI_API_KEY") is None
    config.save_secret("ASSEMBLYAI_API_KEY", "abc")
    assert config.read_secret("ASSEMBLYAI_API_KEY") == "abc"
    config.save_secret("ASSEMBLYAI_API_KEY", "")
    assert config.read_secret("ASSEMBLYAI_API_KEY") is None


def test_secrets_keep_the_rest_of_the_file(data):
    path = data / "secrets.env"
    data.mkdir(parents=True, exist_ok=True)
    path.write_text("# my keys\nOTHER=1\nHF_TOKEN=old\n", encoding="utf-8")
    config.save_secret("HF_TOKEN", "new")
    config.save_secret("ASSEMBLYAI_API_KEY", "x")
    assert path.read_text(encoding="utf-8") == "# my keys\nOTHER=1\nHF_TOKEN=new\nASSEMBLYAI_API_KEY=x\n"


@pytest.mark.skipif(os.name == "nt", reason="symbolic links")
def test_secrets_through_a_link(data, tmp_path):
    real = tmp_path / "other.env"
    real.write_text("A=1\n", encoding="utf-8")
    data.mkdir(parents=True, exist_ok=True)
    (data / "secrets.env").symlink_to(real)
    config.save_secret("HF_TOKEN", "t")
    assert (data / "secrets.env").is_symlink()
    assert real.read_text(encoding="utf-8") == "A=1\nHF_TOKEN=t\n"


def test_the_environment_variable_wins(monkeypatch):
    config.save_secret("HF_TOKEN", "file")
    monkeypatch.setenv("HF_TOKEN", "environment")
    assert config.read_secret("HF_TOKEN") == "environment"


def test_glossary_is_created_empty_and_read():
    assert config.read_glossary() == []  # comments only
    config.glossary_path().write_text("# x\nAna, Pedro\n\nAcme\n", encoding="utf-8")
    assert config.read_glossary() == ["Ana, Pedro", "Acme"]


def test_state_and_projects():
    assert config.load_state() == {}
    config.update_state(last_project="p")
    config.update_state(theme="dark")
    config.set_project_dir("p", "/x")
    assert config.load_state() == {"last_project": "p", "theme": "dark", "project_dirs": {"p": "/x"}}
    assert config.project_dir("p") == "/x" and config.project_dir("other") is None
    config.create_project("p")
    config.create_project("other")
    assert config.list_projects() == ["other", "p"]
