"""Installing local mode afterwards: the uv command it runs."""
import subprocess

from escriba import extras, i18n


def test_requirements_are_the_local_extra():
    names = " ".join(extras.requirements()).replace(".", "-")  # metadata may normalize the names
    assert "faster-whisper" in names and "pyannote-audio" in names


def test_install_pins_what_is_installed(monkeypatch):
    seen = {}

    class FakeProcess:
        stdout = iter(["Resolved 80 packages\n", "Installed 40 packages\n"])

        def __init__(self, cmd, **kwargs):
            seen["cmd"] = cmd
            constraints = cmd[cmd.index("--constraint") + 1]
            with open(constraints, encoding="utf-8") as f:
                seen["pins"] = f.read().split()

        def wait(self):
            return 0

    monkeypatch.setattr(extras, "find_uv", lambda: "uv")
    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    lines = []
    assert extras.install(lines.append)
    assert lines == ["Resolved 80 packages", "Installed 40 packages"]
    cmd = seen["cmd"]
    assert cmd[:3] == ["uv", "pip", "install"] and "--torch-backend" in cmd and "cpu" in cmd
    assert any(p.startswith("numpy==") for p in seen["pins"])
    assert not any(p.lower().startswith("escriba==") for p in seen["pins"])


def test_numbers_in_the_interface_language():
    i18n.set_language("es")
    assert i18n.number(1.5) == "1,5"
    assert i18n.number(3) == "3"
    i18n.set_language("en")
    assert i18n.number(1.5) == "1.5"
