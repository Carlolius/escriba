"""El programa arranca: órdenes de la línea de comandos y páginas de la web."""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from escriba import cli

ORDENES = ["grabar", "transcribir", "archivar", "enrolar", "reparar", "web", "datos"]


@pytest.mark.parametrize("orden", [None, *ORDENES])
def test_ayuda(orden, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main([orden, "--help"] if orden else ["--help"])
    assert e.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_datos(capsys, datos):
    cli.main(["datos"])
    salida = capsys.readouterr().out
    assert str(datos) in salida and "ASSEMBLYAI_API_KEY: falta" in salida


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _entorno_sin_pytest(datos):
    # Con PYTEST_CURRENT_TEST heredado, NiceGUI se cree en sus propias pruebas
    # y cambia de puerto
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    return dict(env, ESCRIBA_DATOS=str(datos))


def test_web_sirve_todas_las_paginas(datos):
    puerto = _puerto_libre()
    proc = subprocess.Popen([sys.executable, "-m", "escriba", "web", "--no-abrir", "--puerto", str(puerto)],
                            env=_entorno_sin_pytest(datos),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        url = f"http://127.0.0.1:{puerto}"
        for _ in range(120):
            try:
                urllib.request.urlopen(url, timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        for ruta in ["/", "/transcribir", "/revisar", "/personas", "/ajustes"]:
            with urllib.request.urlopen(url + ruta, timeout=30) as r:
                assert r.status == 200, ruta
                assert "Escriba" in r.read().decode("utf-8")
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "/fragmento/inventada", timeout=10)
    finally:
        proc.terminate()
        salida = proc.communicate(timeout=30)[0].decode("utf-8", "replace")
    assert "Traceback" not in salida, salida
