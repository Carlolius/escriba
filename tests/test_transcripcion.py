"""Partes de la transcripción que no necesitan red ni modelos."""
import os

from escriba import config, hablantes, nube, tareas, transcribir


def test_escribir_transcripcion_con_hablantes(tmp_path):
    salida = tmp_path / "r.txt"
    segmentos = [(0.0, 2.0, "Hola."), (2.0, 4.0, "¿Qué tal?"), (5.0, 7.0, "Bien.")]
    turnos = [(0.0, 4.1, "A"), (4.5, 8.0, "B")]
    hablantes.escribir_transcripcion(str(salida), segmentos, turnos, {"A": "Ana", "B": "Bea"})
    assert salida.read_text(encoding="utf-8") == "\n[0s] Ana:\nHola.\n[2s] ¿Qué tal?\n\n[5s] Bea:\nBien.\n"


def test_segmentos_desde_palabras_de_assemblyai():
    palabras = [
        {"text": "Hola", "start": 0, "end": 300, "speaker": "A"},
        {"text": "todos.", "start": 300, "end": 600, "speaker": "A"},
        {"text": "Buenas", "start": 900, "end": 1200, "speaker": "B"},
    ]
    assert nube.segmentos_desde_palabras(palabras) == [(0.0, 0.6, "Hola todos."), (0.9, 1.2, "Buenas")]


def test_glosario_para_la_nube_y_para_whisper():
    config.ruta_glosario().write_text("Ana, Acme S.L.\nuna frase demasiado larga para ser un término clave\n",
                                      encoding="utf-8")
    assert nube.leer_glosario() == ["Ana", "Acme S.L."]
    assert transcribir.prompt_glosario().startswith("Reunión de trabajo. Términos y nombres propios: Ana, Acme")


def test_clave_que_falta():
    assert transcribir.clave_que_falta("nube") == "ASSEMBLYAI_API_KEY"
    config.guardar_secreto("ASSEMBLYAI_API_KEY", "x")
    assert transcribir.clave_que_falta("nube") is None


def test_progreso_desde_log(tmp_path):
    log = tmp_path / "t.log"
    casos = [
        ("Cargando modelo medium...\n", "cargando modelo..."),
        ("Transcribiendo: 50% (1:00, quedan ~1:00)\n", "transcribiendo 50% (paso 1/2) · quedan ~5 min"),
        ("Identificando hablantes: 40% (2:00, quedan ~3:00)\n", "identificando hablantes 40% (paso 2/2) · quedan ~3 min"),
        ("Subiendo audio: 35% (0:05)\n", "subiendo audio 35% (nube)"),
        ("Procesando en la nube (processing): 0:42\n", "procesando en la nube (0:42)"),
    ]
    for linea, esperado in casos:
        log.write_text(linea, encoding="utf-8")
        assert tareas.progreso_desde_log(log) == esperado


def test_audios_pendientes(wav):
    a = wav("a.wav")
    b = wav("b.wav", carpeta=a.parent / "sub")
    a.with_suffix(".txt").write_text("ya transcrito", encoding="utf-8")
    pendientes = tareas.audios_pendientes(a.parent)
    assert [p for p, _ in pendientes] == [b]
    assert abs(pendientes[0][1] - 5.0) < 0.01


def test_prioridad_baja_no_falla():
    transcribir.prioridad_baja()
    if os.name != "nt":
        assert os.nice(0) > 0
