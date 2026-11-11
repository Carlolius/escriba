"""Transcripciones en segundo plano: lanzarlas, saber si siguen vivas y leer su
progreso del log. Lo usan el menú de terminal y la interfaz web.

Cada tarea es un proceso aparte (python -m escriba transcribir ...) que sigue
aunque se cierre el menú o el navegador, y escribe su salida en
<audio>_transcribir.log. El estado guarda {"audio", "log", "pid"} de cada una.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import psutil

from . import config

# Medido en oct 2026 (Ryzen 5 5625U, medium + diarización): 5 min de audio
# tardan ~114 s en transcribirse y ~250 s en diarizarse.
FACTOR_PROCESO = 1.25      # tiempo total / duración del audio
RATIO_DIARIZACION = 2.2    # tiempo de diarización / tiempo de transcripción

RE_PROGRESO = re.compile(
    r"^(Transcribiendo|Segmentando voces|Identificando hablantes): (\d+)% "
    r"\((\d+):(\d+)(?:, quedan ~(\d+):(\d+))?\)"
)
RE_NUBE_FASE = re.compile(r"^(Comprimiendo audio|Subiendo audio): (\d+)% ")
RE_NUBE_ESPERA = re.compile(r"^Procesando en la nube \(\w+\): (\d+:\d+)")


def formato_min(segundos):
    minutos = max(1, round(segundos / 60))
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60:02d} min"


def comando(audio, proyecto, motor, modelo, idioma):
    cmd = [sys.executable, "-m", "escriba", "transcribir", str(audio), "--proyecto", proyecto,
           "--idioma", idioma]
    if motor == "nube":
        cmd.append("--nube")
    else:
        cmd += ["--local", "--modelo", modelo]
    return cmd


def entorno():
    """El hijo tiene que encontrar el paquete aunque no esté instalado, y
    escribir el log en UTF-8 (en Windows sería cp1252 y fallaría con "→")."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    raiz = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = raiz + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def lanzar(audio, proyecto, motor="nube", modelo="medium", idioma="auto"):
    """Arranca la transcripción en segundo plano y la apunta en el estado."""
    audio = Path(audio).resolve()
    log = audio.with_name(audio.stem + "_transcribir.log")
    opciones = {}
    if os.name == "nt":
        # Sin ventana de consola y fuera del grupo de Ctrl+C del menú
        opciones["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        # Que un Ctrl+C posterior en el menú (p. ej. al grabar otra reunión) no lo mate
        opciones["start_new_session"] = True
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(comando(audio, proyecto, motor, modelo, idioma), stdout=f,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=entorno(), **opciones)
    estado = config.cargar_estado()
    estado.setdefault("en_curso", []).append({"audio": str(audio), "log": str(log), "pid": proc.pid})
    config.guardar_estado(estado)
    return log


def sigue_vivo(pid):
    """Comprobar la línea de comandos evita confundirla con otro proceso que
    haya reutilizado el PID (o con la antigua transcribir.sh)."""
    try:
        p = psutil.Process(pid)
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        cmd = " ".join(p.cmdline())
    except (psutil.Error, OSError):
        return False
    return "escriba" in cmd and "transcribir" in cmd


def progreso_desde_log(log):
    """Texto del tipo 'transcribiendo 45% (paso 1/2) · quedan ~38 min' a partir
    de las líneas de % que escribe progreso.py en el log."""
    try:
        lineas = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "sin log"
    for linea in reversed(lineas):
        # Fases del modo nube (nube.py)
        if linea.startswith("Idioma detectado:") and "· modelo" in linea:
            return "identificando por voz (nube ya terminada)"
        if m := RE_NUBE_ESPERA.match(linea):
            return f"procesando en la nube ({m.group(1)})"
        if m := RE_NUBE_FASE.match(linea):
            return f"{m.group(1).lower()} {m.group(2)}% (nube)"
        m = RE_PROGRESO.match(linea)
        if not m:
            continue
        fase, pct = m.group(1), int(m.group(2))
        transcurrido = int(m.group(3)) * 60 + int(m.group(4))
        if fase == "Transcribiendo":
            if pct == 0:
                return "transcribiendo 0% (paso 1/2)"
            # Quedan el resto de la transcripción + la diarización entera, que se
            # estima a partir de lo que va a durar la transcripción.
            total_transcripcion = transcurrido * 100 / pct
            restante = total_transcripcion - transcurrido + total_transcripcion * RATIO_DIARIZACION
            return f"transcribiendo {pct}% (paso 1/2) · quedan ~{formato_min(restante)}"
        if fase == "Segmentando voces":
            return "identificando hablantes 0% (paso 2/2)"
        if m.group(5) is None:
            return f"identificando hablantes {pct}% (paso 2/2)"
        restante = int(m.group(5)) * 60 + int(m.group(6))
        return f"identificando hablantes {pct}% (paso 2/2) · quedan ~{formato_min(restante)}"
    if any(l.startswith("Ejecutando diarización") for l in lineas):
        return "preparando identificación de hablantes (paso 2/2)"
    if any(l.startswith("Comprimiendo para subir") for l in lineas):
        return "comprimiendo audio (nube)"
    if any(l.startswith("Cargando modelo") for l in lineas):
        return "cargando modelo..."
    return "empezando..."


def revisar_en_curso():
    """[(tarea, "en_curso" | "terminada" | "fallo", texto)]. Las acabadas se
    devuelven una vez y se quitan del estado."""
    estado = config.cargar_estado()
    tareas = estado.get("en_curso", [])
    resultado, seguimos = [], []
    for t in tareas:
        if sigue_vivo(t["pid"]):
            resultado.append((t, "en_curso", progreso_desde_log(t["log"])))
            seguimos.append(t)
        elif Path(t["audio"]).with_suffix(".txt").exists():
            resultado.append((t, "terminada", "lista para revisar hablantes"))
        else:
            resultado.append((t, "fallo", f"mira {t['log']}"))
    if len(seguimos) != len(tareas):
        # Releer justo antes de guardar: otra ventana pudo lanzar una tarea entretanto
        estado = config.cargar_estado()
        acabados = {t["pid"] for t, est, _ in resultado if est != "en_curso"}
        estado["en_curso"] = [t for t in estado.get("en_curso", []) if t["pid"] not in acabados]
        config.guardar_estado(estado)
    return resultado


def audios_pendientes(directorio, limite=30):
    """[(ruta, duración)] de los WAV sin transcribir (ni transcribiéndose) bajo
    `directorio`, más recientes primero. rglob: las grabaciones de un proyecto
    pueden estar en subcarpetas."""
    from . import audio as audio_util

    directorio = Path(directorio)
    if not directorio.is_dir():
        return []
    en_curso = audios_en_curso()
    wavs = sorted(directorio.rglob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    pendientes = [w for w in wavs if not w.with_suffix(".txt").exists() and str(w.resolve()) not in en_curso]
    return [(w, audio_util.duracion(w)) for w in pendientes[:limite]]


def audios_en_curso():
    return {t["audio"] for t in config.cargar_estado().get("en_curso", [])}
