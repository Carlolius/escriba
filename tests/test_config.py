import os

import pytest

from escriba import config


def test_carpeta_de_datos_de_la_variable(datos):
    assert config.dir_datos() == datos
    assert config.dir_voiceprints() == datos / "voiceprints"


def test_secretos_guardar_y_leer():
    assert config.leer_secreto("ASSEMBLYAI_API_KEY") is None
    config.guardar_secreto("ASSEMBLYAI_API_KEY", "abc")
    assert config.leer_secreto("ASSEMBLYAI_API_KEY") == "abc"
    config.guardar_secreto("ASSEMBLYAI_API_KEY", "")
    assert config.leer_secreto("ASSEMBLYAI_API_KEY") is None


def test_secretos_respetan_el_resto_del_archivo(datos):
    ruta = datos / "secretos.env"
    datos.mkdir(parents=True, exist_ok=True)
    ruta.write_text("# mis claves\nOTRA=1\nHF_TOKEN=viejo\n", encoding="utf-8")
    config.guardar_secreto("HF_TOKEN", "nuevo")
    config.guardar_secreto("ASSEMBLYAI_API_KEY", "x")
    assert ruta.read_text(encoding="utf-8") == "# mis claves\nOTRA=1\nHF_TOKEN=nuevo\nASSEMBLYAI_API_KEY=x\n"


@pytest.mark.skipif(os.name == "nt", reason="enlaces simbólicos")
def test_secretos_a_traves_de_un_enlace(datos, tmp_path):
    real = tmp_path / "otro.env"
    real.write_text("A=1\n", encoding="utf-8")
    datos.mkdir(parents=True, exist_ok=True)
    (datos / "secretos.env").symlink_to(real)
    config.guardar_secreto("HF_TOKEN", "t")
    assert (datos / "secretos.env").is_symlink()
    assert real.read_text(encoding="utf-8") == "A=1\nHF_TOKEN=t\n"


def test_la_variable_de_entorno_manda(monkeypatch):
    config.guardar_secreto("HF_TOKEN", "archivo")
    monkeypatch.setenv("HF_TOKEN", "entorno")
    assert config.leer_secreto("HF_TOKEN") == "entorno"


def test_glosario_se_crea_vacio_y_se_lee():
    assert config.leer_glosario() == []  # solo comentarios
    config.ruta_glosario().write_text("# x\nAna, Pedro\n\nAcme\n", encoding="utf-8")
    assert config.leer_glosario() == ["Ana, Pedro", "Acme"]


def test_estado_y_proyectos():
    assert config.cargar_estado() == {}
    config.actualizar_estado(ultimo_proyecto="p")
    config.actualizar_estado(tema="oscuro")
    assert config.cargar_estado() == {"ultimo_proyecto": "p", "tema": "oscuro"}
    config.crear_proyecto("p")
    config.crear_proyecto("otro")
    assert config.listar_proyectos() == ["otro", "p"]
