"""The program starts: command-line commands and web pages, in both languages."""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from escriba import cli, config, i18n

COMMANDS = ["record", "transcribe", "archive", "enroll", "repair", "web", "data"]


@pytest.mark.parametrize("command", [None, *COMMANDS])
def test_help(command, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main([command, "--help"] if command else ["--help"])
    assert e.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_help_in_spanish_and_lang_is_remembered(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--lang", "es", "transcribe", "--help"])
    assert "idioma de la reunión" in capsys.readouterr().out
    assert config.load_state()["language"] == "es"
    i18n._current = None  # as in a new process
    assert i18n.language() == "es"


def test_data(capsys, data):
    cli.main(["data"])
    out = capsys.readouterr().out
    assert str(data) in out and "ASSEMBLYAI_API_KEY: missing" in out


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env_without_pytest(data, lang):
    # With an inherited PYTEST_CURRENT_TEST, NiceGUI thinks it's in its own
    # tests and changes port
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    return dict(env, ESCRIBA_DATA=str(data), ESCRIBA_LANG=lang)


@pytest.mark.parametrize("lang, settings", [("en", "Appearance"), ("es", "Apariencia")])
def test_web_serves_every_page(data, lang, settings, meeting):
    # With a project and a meeting, so the pages draw their content and not the "no projects" note
    config.create_project("test")
    config.set_project_dir("test", meeting[0].parent)
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "escriba", "web", "--no-browser", "--port", str(port)],
                            env=_env_without_pytest(data, lang),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        url = f"http://127.0.0.1:{port}"
        for _attempt in range(120):
            try:
                urllib.request.urlopen(url, timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        for path in ["/", "/meetings", "/transcribe", "/review", "/people", "/settings"]:
            with urllib.request.urlopen(url + path, timeout=30) as r:
                assert r.status == 200, path
                page = r.read().decode("utf-8")
                assert "Escriba" in page
                if path == "/settings":
                    assert settings in page
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "/clip/made-up", timeout=10)
    finally:
        proc.terminate()
        out = proc.communicate(timeout=30)[0].decode("utf-8", "replace")
    assert "Traceback" not in out, out
