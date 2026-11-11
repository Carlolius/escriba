"""Interface language: English (the source strings) or Spanish.

Every user-facing string in the code is written in English and wrapped in _():

    _("Saved: {path}", path=out)

Translations live in escriba/locales/<lang>.json, keyed by the English text.
A missing translation falls back to English. tests/test_i18n.py checks that
every string in the code has its Spanish translation.

The language is, in order: ESCRIBA_LANG, the "language" setting (Settings page,
terminal menu or --lang), and the system language.
"""
import json
import locale
import os
from functools import cache
from pathlib import Path

LANGUAGES = {"en": "English", "es": "Español"}
_current = None


def N_(text):
    """Marks a string for translation without translating it yet (for
    module-level constants, translated with _() when shown)."""
    return text


def system_language():
    if os.name == "nt":
        try:
            import ctypes
            # Primary language ID of the Windows display language (0x0A = Spanish)
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x0A:
                return "es"
            return "en"
        except (AttributeError, OSError):
            pass
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if value := os.environ.get(var):
            return "es" if value.lower().startswith("es") else "en"
    code = (locale.getlocale()[0] or "").lower()
    return "es" if code.startswith(("es", "spanish")) else "en"


def language():
    global _current
    if _current is None:
        from . import config
        chosen = os.environ.get("ESCRIBA_LANG") or config.load_state().get("language")
        _current = chosen if chosen in LANGUAGES else system_language()
    return _current


def set_language(code):
    """code: "en", "es" or None/"auto" (system language). Only for this process;
    config.update_state(language=...) saves it."""
    global _current
    _current = code if code in LANGUAGES else system_language()


@cache
def _catalog(lang):
    path = Path(__file__).parent / "locales" / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


DECIMAL_COMMA = {"es"}


def number(x, digits=1):
    """A decimal number as written in the interface language: 1.5 / 1,5."""
    text = f"{x:.{digits}f}"
    return text.replace(".", ",") if language() in DECIMAL_COMMA else text


def _(text, /, **values):
    lang = language()
    if lang != "en":
        text = _catalog(lang).get(text, text)
    return text.format(**values) if values else text


def _n(singular, plural, n, /, **values):
    """Plural forms (English and Spanish share the rule: 1 vs. the rest).
    The catalog stores both forms under the singular: "x": ["sing", "plural"]."""
    forms = (singular, plural)
    if language() != "en":
        forms = _catalog(language()).get(singular, forms)
    return forms[0 if n == 1 else 1].format(n=n, **values)
