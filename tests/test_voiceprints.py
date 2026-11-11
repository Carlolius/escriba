from conftest import emb

from escriba import voiceprints as vp


def test_add_without_duplicating():
    assert vp.add_sample("p", "Ana", emb(1)) == (1, True)
    assert vp.add_sample("p", "Ana", emb(1)) == (1, False)  # almost identical: not added
    assert vp.add_sample("p", "Ana", emb(2)) == (2, True)
    assert vp.identify(emb(2), vp.load_library("p"))[0] == "Ana"
    assert vp.identify(emb(99), vp.load_library("p"))[0] is None


def test_move_delete_and_undo():
    vp.add_sample("p", "Ana", emb(1))
    vp.add_sample("p", "Ana", emb(2))
    ids = [s["id"] for s in vp.load_samples("p")["Ana"]]
    vp.move_sample("p", "Ana", ids[0], "Bea")
    lib = vp.load_samples("p")
    assert len(lib["Ana"]) == 1 and lib["Bea"][0]["id"] == ids[0]
    vp.delete_person("p", "Bea")
    assert "Bea" not in vp.load_library("p")
    assert vp.has_backup("p") and vp.restore_backup("p")
    assert "Bea" in vp.load_library("p")


def test_audit_finds_confusions_and_can_mark_them_fine():
    base = emb(5)
    close = base + emb(6) * 0.05
    vp.add_sample("p", "Ana", base)
    vp.add_sample("p", "Bea", close / (close ** 2).sum() ** 0.5)
    assert {f["kind"] for f in vp.audit_library("p")} == {"confusion"}
    f = vp.audit_library("p")[0]
    vp.mark_as_ok("p", f["kind"], f["id_a"], f["id_b"])
    assert vp.audit_library("p") == []
