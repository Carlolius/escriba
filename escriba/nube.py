"""Transcribe e identifica hablantes en la nube con AssemblyAI.

Mucho más rápido que el modo local (minutos en vez de ~1 h por hora de audio)
a cambio de ~0,23 $/hora de audio y de que el audio salga del PC. Se transcribe
y diariza allí; la identificación por voz contra la librería del proyecto y el
.txt/.speakers.json se hacen aquí igual que en local (hablantes.py), así que
"Revisar hablantes" funciona igual.

Pasos: comprimir a Opus (se sube ~10 veces menos) -> subir -> transcribir con
tu glosario como palabras clave -> descargar -> borrar la transcripción de
AssemblyAI (no se queda allí ni el audio ni el texto).

Necesita la clave ASSEMBLYAI_API_KEY (ver config.leer_secreto).
"""
import sys
import tempfile
import time
from pathlib import Path

import requests

from . import audio as audio_util
from . import config, hablantes
from .progreso import Progreso

API = "https://api.assemblyai.com/v2"
PRECIO_HORA = 0.23  # $ (universal-3-5-pro 0,21 + diarización 0,02), oct 2026
TAM_TROZO = 256 * 1024


def leer_glosario():
    """Términos del glosario como keyterms (máx. 6 palabras cada uno)."""
    terminos = []
    for linea in config.leer_glosario():
        for t in linea.split(","):
            t = t.strip()
            if t and len(t.split()) <= 6:
                terminos.append(t)
    return terminos


def subir(sesion, ruta):
    total = ruta.stat().st_size
    progreso = Progreso()

    def trozos():
        enviado = 0
        with open(ruta, "rb") as f:
            while trozo := f.read(TAM_TROZO):
                enviado += len(trozo)
                progreso.actualizar("Subiendo audio", enviado, total)
                yield trozo

    try:
        r = sesion.post(f"{API}/upload", data=trozos(), timeout=600)
        r.raise_for_status()
    finally:
        progreso.cerrar()
    return r.json()["upload_url"]


def esperar(sesion, id_transcripcion):
    """AssemblyAI no da porcentaje: se enseña el estado y el tiempo que lleva."""
    inicio, ultimo_estado, ultimo_aviso = time.time(), None, 0.0
    tty = sys.stdout.isatty()
    while True:
        r = sesion.get(f"{API}/transcript/{id_transcripcion}", timeout=60)
        r.raise_for_status()
        datos = r.json()
        estado = datos["status"]
        if estado in ("completed", "error"):
            if tty:
                print()
            return datos
        transcurrido = int(time.time() - inicio)
        texto = f"Procesando en la nube ({estado}): {transcurrido // 60}:{transcurrido % 60:02d}"
        if tty:
            print(f"\r{texto}   ", end="", flush=True)
        elif estado != ultimo_estado or time.time() - ultimo_aviso >= 15:
            print(texto, flush=True)
            ultimo_aviso = time.time()
        ultimo_estado = estado
        time.sleep(3)


def segmentos_desde_palabras(palabras):
    """Agrupa palabras en frases (fin de frase, cambio de hablante o 30 s) para
    que el .txt tenga marcas [Ns] tan frecuentes como en el modo local."""
    segmentos, actual = [], []
    for p in palabras:
        if actual and (p.get("speaker") != actual[0].get("speaker") or p["end"] - actual[0]["start"] > 30000):
            segmentos.append(actual)
            actual = []
        actual.append(p)
        if p["text"].endswith((".", "?", "!", "…")):
            segmentos.append(actual)
            actual = []
    if actual:
        segmentos.append(actual)
    return [(s[0]["start"] / 1000, s[-1]["end"] / 1000, " ".join(p["text"] for p in s)) for s in segmentos]


class ErrorNube(RuntimeError):
    pass


def transcribir(audio, salida, idioma="auto", diarizar=False, proyecto="", hablante_list=()):
    clave = config.leer_secreto("ASSEMBLYAI_API_KEY")
    if not clave:
        raise ErrorNube("Falta la clave de AssemblyAI (ASSEMBLYAI_API_KEY)")
    audio = Path(audio)
    hablante_list = list(hablante_list)
    sesion = requests.Session()
    sesion.headers["authorization"] = clave

    with tempfile.TemporaryDirectory() as tmp:
        comprimido = Path(tmp) / "subida.opus"
        print("Comprimiendo para subir...", flush=True)
        audio_util.comprimir_opus(audio, comprimido, nivel=audio_util.NIVEL_SUBIDA)
        url = subir(sesion, comprimido)

    peticion = {"audio_url": url, "speech_models": ["universal-3-5-pro", "universal-2"], "punctuate": True}
    if idioma and idioma != "auto":
        peticion["language_code"] = idioma
    else:
        peticion["language_detection"] = True
    if diarizar:
        peticion["speaker_labels"] = True
        if hablante_list and not proyecto:
            peticion["speakers_expected"] = len(hablante_list)
    if terminos := leer_glosario():
        peticion["keyterms_prompt"] = terminos

    r = sesion.post(f"{API}/transcript", json=peticion, timeout=60)
    if r.status_code >= 400 and "keyterms_prompt" in peticion:
        # keyterms solo lo admite universal-3-5-pro; si el idioma cae a otro modelo, sin glosario
        print(f"AVISO: AssemblyAI no acepta el glosario ({r.json().get('error', r.text)}); se reintenta sin él")
        del peticion["keyterms_prompt"]
        r = sesion.post(f"{API}/transcript", json=peticion, timeout=60)
    r.raise_for_status()
    id_transcripcion = r.json()["id"]

    datos = esperar(sesion, id_transcripcion)
    if datos["status"] == "error":
        sesion.delete(f"{API}/transcript/{id_transcripcion}", timeout=60)
        raise ErrorNube(f"Error de AssemblyAI: {datos.get('error')}")

    duracion = datos.get("audio_duration") or 0
    print(
        f"Idioma detectado: {datos.get('language_code')} · modelo {datos.get('speech_model_used')} · "
        f"duración: {duracion:.0f}s · coste aprox. {duracion / 3600 * PRECIO_HORA:.2f} $",
        flush=True,
    )

    palabras = datos.get("words") or []
    segments = segmentos_desde_palabras(palabras)
    speaker_turns = None
    if diarizar and datos.get("utterances"):
        speaker_turns = [(u["start"] / 1000, u["end"] / 1000, f"SPEAKER_{u['speaker']}") for u in datos["utterances"]]

    # Ya tenemos todo: se borra de AssemblyAI (texto y audio subido)
    try:
        sesion.delete(f"{API}/transcript/{id_transcripcion}", timeout=60).raise_for_status()
    except requests.RequestException as e:
        print(f"AVISO: no se pudo borrar la transcripción {id_transcripcion} de AssemblyAI: {e}")

    speaker_map = None
    if speaker_turns:
        speaker_map = hablantes.nombrar_hablantes(str(audio), str(salida), speaker_turns, proyecto, hablante_list)
    hablantes.escribir_transcripcion(str(salida), segments, speaker_turns, speaker_map)

