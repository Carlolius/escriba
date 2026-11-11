"""Revisar los hablantes de una transcripción y alimentar la librería de voces.

Cada transcripción con identificación tiene un <audio>.speakers.json con un
"cluster" por voz detectada (nombre asignado, similitud, embedding y el
fragmento de audio de origen). Revisar es, para cada cluster: confirmar el
nombre (refuerza la librería), corregirlo (añade la muestra a la persona
correcta y renombra en el .txt) o saltarlo (no toca la librería). Cada decisión
se guarda al momento, así que se puede parar y retomar.

Esta capa no pregunta nada: el menú de terminal y la web deciden qué mostrar.
"""
import json
import re
from pathlib import Path

import numpy as np

from . import archivar, config, voiceprints

SUFIJO = ".speakers.json"


def leer(sidecar):
    return json.loads(Path(sidecar).read_text(encoding="utf-8"))


def ruta_txt(sidecar):
    sidecar = Path(sidecar)
    return sidecar.with_name(sidecar.name.removesuffix(SUFIJO) + ".txt")


def ruta_audio(sidecar):
    """El .wav si sigue ahí; si ya se archivó, el .opus."""
    sidecar = Path(sidecar)
    base = sidecar.name.removesuffix(SUFIJO)
    for ext in (".wav", ".opus"):
        if (sidecar.parent / (base + ext)).exists():
            return sidecar.parent / (base + ext)
    return None


def frases_de(texto, nombre, n=3):
    """Las n frases más largas que dijo `nombre` en la transcripción, en orden
    cronológico. Las cabeceras de hablante son '[Ns] Nombre:' tras una línea vacía."""
    frases, actual, anterior = [], None, ""
    for linea in texto.splitlines():
        m = re.match(r"^\[\d+s\] (.+):$", linea)
        if m and not anterior.strip():
            actual = m.group(1)
        elif actual == nombre and linea.strip():
            frase = re.sub(r"^\[\d+s\] ", "", linea).strip()
            if len(frase.split()) >= 5:
                frases.append(frase)
        anterior = linea
    elegidas = sorted(sorted(range(len(frases)), key=lambda i: -len(frases[i]))[:n])
    return [frases[i] if len(frases[i]) <= 140 else frases[i][:137] + "..." for i in elegidas]


def frases_por_cluster(sidecar, n=3):
    txt = ruta_txt(sidecar)
    texto = txt.read_text(encoding="utf-8") if txt.exists() else ""
    return {spk: frases_de(texto, info["nombre"], n) for spk, info in leer(sidecar)["clusters"].items()}


def pendientes(solo_proyecto=None):
    """[(proyecto, sidecar)] sin revisar, más recientes primero, buscando en el
    último directorio usado de cada proyecto. rglob porque las grabaciones de
    un mismo proyecto pueden acabar en subcarpetas distintas."""
    encontrados = {}
    for clave, directorio in config.cargar_estado().items():
        if not clave.startswith("ultimo_dir_"):
            continue
        proyecto = clave.removeprefix("ultimo_dir_")
        if solo_proyecto and proyecto != solo_proyecto:
            continue
        directorio = Path(directorio)
        if not directorio.exists():
            continue
        for s in directorio.rglob("*" + SUFIJO):
            try:
                data = leer(s)
            except (OSError, json.JSONDecodeError):
                continue
            if not data.get("revisado"):
                encontrados[s.resolve()] = data.get("proyecto", proyecto)
    orden = sorted(encontrados, key=lambda p: p.stat().st_mtime, reverse=True)
    return [(encontrados[s], s) for s in orden]


def nombres_conocidos(sidecar, proyecto):
    data = leer(sidecar)
    return sorted(
        {c["nombre"] for c in data["clusters"].values() if not c["nombre"].startswith("Hablante ")}
        | set(voiceprints.cargar_libreria(proyecto).keys())
    )


def decidir(sidecar, spk, nuevo_nombre, proyecto=None):
    """Guarda la decisión sobre un cluster. nuevo_nombre: el mismo nombre =
    confirmar, otro = corregir, "" o None = saltar.

    Devuelve {"muestras": n, "anadida": bool, "renombradas": n, "completa": bool}."""
    sidecar = Path(sidecar)
    data = leer(sidecar)
    proyecto = proyecto or data.get("proyecto")
    info = data["clusters"][spk]
    resultado = {"muestras": 0, "anadida": False, "renombradas": 0}

    if nuevo_nombre:
        emb = np.array(info["embedding"], dtype="float32")
        resultado["muestras"], resultado["anadida"] = voiceprints.anadir_muestra(
            proyecto, nuevo_nombre, emb, origen=info.get("origen"))
        txt = ruta_txt(sidecar)
        if nuevo_nombre != info["nombre"] and txt.exists():
            patron = rf"^(\[\d+s\]) {re.escape(info['nombre'])}:$"
            texto, n = re.subn(patron, lambda m: f"{m.group(1)} {nuevo_nombre}:",
                               txt.read_text(encoding="utf-8"), flags=re.MULTILINE)
            if n:
                txt.write_text(texto, encoding="utf-8")
            resultado["renombradas"] = n
        info["nombre"] = nuevo_nombre

    info["revisado"] = True
    data["revisado"] = all(c.get("revisado") for c in data["clusters"].values())
    config.escribir_json(sidecar, data)
    resultado["completa"] = data["revisado"]
    return resultado


def archivar_si_completa(sidecar):
    """Revisada la reunión, su WAV ya solo sirve de archivo: se pasa a Opus.
    Devuelve (ruta_opus, bytes_ahorrados) o None si no tocaba."""
    sidecar = Path(sidecar)
    wav = sidecar.with_name(sidecar.name.removesuffix(SUFIJO) + ".wav")
    if not wav.exists() or not archivar.listo_para_archivar(wav):
        return None
    opus, ahorro, _ = archivar.archivar(wav)
    return opus, ahorro


def enrolar(audio, inicio, fin, nombre, proyecto):
    """Añade a mano una muestra de voz (fragmento inicio-fin de un audio)."""
    from resemblyzer import VoiceEncoder

    from . import audio as audio_util

    datos, _ = audio_util.leer_fragmento(audio, inicio, fin)
    emb = VoiceEncoder(verbose=False).embed_utterance(datos)
    origen = {"audio": str(Path(audio).resolve()), "inicio": float(inicio), "fin": float(fin)}
    return voiceprints.anadir_muestra(proyecto, nombre, emb, origen=origen)
