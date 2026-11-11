"""Transcripción local: faster-whisper + diarización con pyannote.

Gratis y sin que el audio salga del PC, pero lento sin tarjeta NVIDIA (en un
Ryzen 5 5625U, ~1 h 15 por hora de audio con identificación de hablantes).
Necesita el extra "local" (faster-whisper, pyannote.audio) y, para separar
hablantes, HF_TOKEN con las condiciones de pyannote aceptadas.
"""
import warnings

import psutil

from . import config, hablantes
from .progreso import Progreso

BEAM_SIZE = 5


def hilos():
    # Núcleos físicos: con prioridad baja, usarlos todos no resta fluidez al
    # resto del PC, y los hilos lógicos extra apenas aceleran whisper.
    return psutil.cpu_count(logical=False) or 4


def transcribir(audio, salida, modelo="medium", idioma="auto", prompt="", diarizar=False,
                proyecto="", hablante_list=()):
    warnings.filterwarnings("ignore", category=UserWarning)  # ruido de pyannote/webrtcvad en el log
    from faster_whisper import WhisperModel

    progreso = Progreso()
    print(f"Cargando modelo {modelo}...", flush=True)
    model = WhisperModel(modelo, device="cpu", compute_type="int8", cpu_threads=hilos(), num_workers=1)

    kwargs = dict(beam_size=BEAM_SIZE, vad_filter=True, condition_on_previous_text=False)
    if idioma and idioma != "auto":
        kwargs["language"] = idioma
    if prompt:
        kwargs["initial_prompt"] = prompt

    segments_raw, info = model.transcribe(str(audio), **kwargs)
    print(f"Idioma detectado: {info.language} ({info.language_probability:.0%}), duración: {info.duration:.0f}s",
          flush=True)

    segments = []
    progreso.actualizar("Transcribiendo", 0, info.duration)  # arranca el reloj antes del primer segmento
    for s in segments_raw:
        segments.append((s.start, s.end, s.text.strip()))
        progreso.actualizar("Transcribiendo", s.end, info.duration)
    progreso.actualizar("Transcribiendo", info.duration, info.duration)

    speaker_turns, speaker_map = None, None
    if diarizar:
        speaker_turns = _diarizar(audio, hablante_list, progreso)
        progreso.cerrar()  # deja de redibujar las barras antes de imprimir los matches
        if speaker_turns:
            speaker_map = hablantes.nombrar_hablantes(str(audio), str(salida), speaker_turns, proyecto,
                                                      list(hablante_list))

    progreso.cerrar()
    hablantes.escribir_transcripcion(str(salida), segments, speaker_turns, speaker_map)


def _diarizar(audio, hablante_list, progreso):
    hf_token = config.leer_secreto("HF_TOKEN")
    if not hf_token:
        print("AVISO: falta HF_TOKEN: sin separar hablantes")
        return None
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print("AVISO: pyannote.audio no instalado: sin separar hablantes (instala el extra 'local')")
        return None
    print("Ejecutando diarización (suele tardar más que la transcripción)...", flush=True)
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=hf_token)
    kwargs = {"num_speakers": len(hablante_list)} if hablante_list else {}
    # Audio ya cargado en memoria: con una ruta, pyannote 4 lo leería con
    # torchcodec, que en Windows necesita las DLL de FFmpeg instaladas aparte
    import soundfile as sf
    import torch
    datos, sr = sf.read(str(audio), dtype="float32", always_2d=True)
    entrada = {"waveform": torch.from_numpy(datos.mean(axis=1, keepdims=True).T.copy()), "sample_rate": sr}
    diarization = pipeline(entrada, hook=progreso.hook_pyannote(), **kwargs)
    return [(t.start, t.end, s) for t, _, s in diarization.speaker_diarization.itertracks(yield_label=True)]
