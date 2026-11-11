import json
import shutil

from escriba import audio, config, revisar, rutas, voiceprints


def test_frases_de():
    texto = "\n[0s] Ana:\nHola, esto es una frase bastante larga.\n[2s] corta\n\n[5s] Bea:\nOtra frase de cinco palabras.\n"
    assert revisar.frases_de(texto, "Ana") == ["Hola, esto es una frase bastante larga."]
    assert revisar.frases_de(texto, "Bea") == ["Otra frase de cinco palabras."]


def test_pendientes_busca_en_la_carpeta_del_proyecto(reunion):
    wav, sidecar, _ = reunion
    assert revisar.pendientes() == []
    config.actualizar_estado(ultimo_dir_prueba=str(wav.parent))
    assert revisar.pendientes() == [("prueba", sidecar.resolve())]


def test_revisar_corregir_confirmar_y_archivar(reunion):
    wav, sidecar, txt = reunion
    r = revisar.decidir(sidecar, "SPEAKER_A", "Carlos")
    assert r["anadida"] and r["renombradas"] == 1 and not r["completa"]
    assert "[0s] Carlos:" in txt.read_text(encoding="utf-8")
    r = revisar.decidir(sidecar, "SPEAKER_B", "")  # no lo sé: no toca la librería
    assert r["completa"]
    assert set(voiceprints.cargar_libreria("prueba")) == {"Carlos"}

    dur = audio.duracion(wav)
    opus, ahorro = revisar.archivar_si_completa(sidecar)
    assert not wav.exists() and opus.suffix == ".opus" and ahorro > 0
    assert abs(audio.duracion(opus) - dur) < 0.5
    # Las referencias pasan al .opus, en la librería y en el sidecar
    origen = voiceprints.cargar_libreria_con_origen("prueba")["Carlos"][0]["origen"]
    assert origen["audio"] == str(opus)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["clusters"]["SPEAKER_A"]["origen"]["audio"] == str(opus)


def test_no_archiva_si_falta_revisar(reunion):
    wav, sidecar, _ = reunion
    revisar.decidir(sidecar, "SPEAKER_A", "Carlos")
    assert revisar.archivar_si_completa(sidecar) is None
    assert wav.exists()


def test_reparar_rutas_de_un_audio_movido(reunion, tmp_path):
    wav, sidecar, _ = reunion
    revisar.decidir(sidecar, "SPEAKER_A", "Carlos")
    config.actualizar_estado(ultimo_dir_prueba=str(wav.parent))
    nueva = wav.parent / "archivo" / wav.name
    nueva.parent.mkdir()
    for f in (wav, sidecar):
        shutil.move(f, nueva.parent / f.name)
    assert str(wav) in rutas.rutas_rotas()

    r = rutas.reparar()
    assert [(v, n) for v, n, _ in r["arregladas"]] == [(str(wav), str(nueva.resolve()))]
    assert rutas.rutas_rotas() == {}
    origen = voiceprints.cargar_libreria_con_origen("prueba")["Carlos"][0]["origen"]
    assert origen["audio"] == str(nueva.resolve())
