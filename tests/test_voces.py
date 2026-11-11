from conftest import emb

from escriba import voiceprints as vp


def test_anadir_y_no_duplicar():
    assert vp.anadir_muestra("p", "Ana", emb(1)) == (1, True)
    assert vp.anadir_muestra("p", "Ana", emb(1)) == (1, False)  # casi idéntica: no se añade
    assert vp.anadir_muestra("p", "Ana", emb(2)) == (2, True)
    assert vp.identificar(emb(2), vp.cargar_libreria("p"))[0] == "Ana"
    assert vp.identificar(emb(99), vp.cargar_libreria("p"))[0] is None


def test_reclasificar_borrar_y_deshacer():
    vp.anadir_muestra("p", "Ana", emb(1))
    vp.anadir_muestra("p", "Ana", emb(2))
    ids = [m["id"] for m in vp.cargar_libreria_con_origen("p")["Ana"]]
    vp.reclasificar_muestra("p", "Ana", ids[0], "Bea")
    lib = vp.cargar_libreria_con_origen("p")
    assert len(lib["Ana"]) == 1 and lib["Bea"][0]["id"] == ids[0]
    vp.eliminar_persona("p", "Bea")
    assert "Bea" not in vp.cargar_libreria("p")
    assert vp.restaurar_backup("p")
    assert "Bea" in vp.cargar_libreria("p")


def test_auditoria_detecta_duplicados_y_confusiones():
    base = emb(5)
    casi = base + emb(6) * 0.05
    vp.anadir_muestra("p", "Ana", base)
    vp.anadir_muestra("p", "Bea", casi / (casi ** 2).sum() ** 0.5)
    tipos = {h["tipo"] for h in vp.auditar_libreria("p")}
    assert "confusion" in tipos
    h = vp.auditar_libreria("p")[0]
    vp.marcar_como_correcto("p", h["tipo"], h["id_a"], h["id_b"])
    assert vp.auditar_libreria("p") == []
