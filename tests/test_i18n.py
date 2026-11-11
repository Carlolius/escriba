"""Every string the interface shows has its Spanish translation."""
import ast
import json
import string
from pathlib import Path

import pytest

from escriba import i18n

PACKAGE = Path(i18n.__file__).parent


def strings_in_code():
    """{text: "_" | "_n" | "N_"} for every literal passed to _(), _n() or N_()."""
    found = {}
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "_n", "N_"):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    found[node.args[0].value] = node.func.id
    return found


def fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_string_is_translated_and_none_is_left_over():
    catalog = json.loads((PACKAGE / "locales" / "es.json").read_text(encoding="utf-8"))
    code = strings_in_code()
    assert sorted(set(code) - set(catalog)) == [], "missing in es.json"
    assert sorted(set(catalog) - set(code)) == [], "in es.json but no longer in the code"
    for text, kind in code.items():
        translation = catalog[text]
        if kind == "_n":
            assert isinstance(translation, list) and len(translation) == 2, text
            for form in translation:
                assert fields(form) <= fields(text) | {"n"}, text
        else:
            assert isinstance(translation, str), text
            assert fields(translation) == fields(text), text


@pytest.mark.parametrize("lang", ["en", "es"])
def test_switching_language(lang):
    i18n.set_language(lang)
    assert i18n._("Record") == {"en": "Record", "es": "Grabar"}[lang]
    assert i18n._n("{n} pending finding", "{n} pending findings", 2) == {
        "en": "2 pending findings", "es": "2 hallazgos pendientes"}[lang]


def test_placeholders_may_share_a_name_with_the_parameters():
    # A failed job is printed with {name} and {text}: it used to raise TypeError
    assert i18n._("{text} and {n}", text="a", n=1) == "a and 1"
    assert i18n._n("{n} {text}", "{n} {text}s", 2, text="x", singular="s", plural="p") == "2 xs"
