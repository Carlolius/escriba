"""Utilidades de audio sin ffmpeg: duración, compresión a Opus y reproducción.

soundfile (libsndfile) lee y escribe WAV, FLAC y Ogg/Opus en Linux, Windows y
macOS sin instalar nada aparte, y soundcard reproduce por el altavoz del
sistema. Así el programa no depende de tener ffmpeg instalado.
"""
from pathlib import Path

import numpy as np
import soundfile as sf

from .progreso import Progreso

# compression_level de libsndfile para Opus. No es lineal: medido sobre una
# reunión real a 16 kHz, 0.84 da ~21 kbps y 0.89 ~16 kbps (el antiguo
# "ffmpeg -b:a 24k -application voip" daba ~13 kbps reales). Las huellas de voz
# salen iguales (similitud > 0,999 con el WAV).
NIVEL_ARCHIVO = 0.89
NIVEL_SUBIDA = 0.84
FRECUENCIAS_OPUS = (8000, 12000, 16000, 24000, 48000)
BLOQUE_S = 10


def duracion(ruta):
    try:
        return sf.info(str(ruta)).duration
    except Exception:
        return None


def _a_mono(bloque):
    return bloque.mean(axis=1) if bloque.ndim > 1 else bloque


def _remuestrear(bloque, sr_origen, sr_destino):
    """Interpolación lineal: suficiente para voz y sin depender de scipy."""
    n = int(round(len(bloque) * sr_destino / sr_origen))
    if n == 0:
        return bloque[:0]
    x = np.linspace(0, len(bloque) - 1, n)
    return np.interp(x, np.arange(len(bloque)), bloque).astype("float32")


def comprimir_opus(origen, destino, nivel=NIVEL_ARCHIVO, descripcion="Comprimiendo audio"):
    """Cualquier audio que lea soundfile -> Ogg/Opus mono, con barra de progreso."""
    with sf.SoundFile(str(origen)) as entrada:
        sr = entrada.samplerate
        sr_salida = sr if sr in FRECUENCIAS_OPUS else 16000
        total = entrada.frames / sr
        progreso = Progreso()
        try:
            with sf.SoundFile(str(destino), "w", samplerate=sr_salida, channels=1, format="OGG",
                              subtype="OPUS", compression_level=nivel) as salida:
                hecho = 0.0
                for bloque in entrada.blocks(blocksize=sr * BLOQUE_S, dtype="float32", always_2d=True):
                    bloque = _a_mono(bloque)
                    if sr_salida != sr:
                        bloque = _remuestrear(bloque, sr, sr_salida)
                    salida.write(bloque)
                    hecho += BLOQUE_S
                    progreso.actualizar(descripcion, min(hecho, total), total)
            progreso.actualizar(descripcion, total, total)
        finally:
            progreso.cerrar()


def leer_fragmento(ruta, inicio, fin):
    """(muestras mono float32, frecuencia) entre inicio y fin, en segundos."""
    with sf.SoundFile(str(ruta)) as f:
        sr = f.samplerate
        f.seek(int(inicio * sr))
        datos = f.read(int((fin - inicio) * sr), dtype="float32", always_2d=True)
    return _a_mono(datos), sr


def reproducir(ruta, inicio, fin):
    """Reproduce un fragmento por el altavoz por defecto. Bloquea hasta acabar;
    Ctrl+C lo corta (se reproduce en trozos para que el corte sea inmediato)."""
    import soundcard as sc

    datos, sr = leer_fragmento(Path(ruta), inicio, fin)
    trozo = sr // 4
    with sc.default_speaker().player(samplerate=sr, channels=1) as player:
        for i in range(0, len(datos), trozo):
            player.play(datos[i:i + trozo])
