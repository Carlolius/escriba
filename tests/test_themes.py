"""Color themes: complete, valid and readable."""
import re

import pytest

from escriba import themes


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("key", themes.THEMES)
def test_complete_and_valid(key):
    theme = themes.THEMES[key]
    assert theme["name"] and len(theme["header"]) == 3
    for variant in ("light", "dark"):
        assert set(theme[variant]) == set(themes.KEYS)
    for color in [*theme["header"], *theme["light"].values(), *theme["dark"].values()]:
        assert re.fullmatch(r"#[0-9a-f]{6}", color), color


@pytest.mark.parametrize("key", themes.THEMES)
def test_readable(key):
    """WCAG: 4.5 for text, 3 for secondary text, buttons and status colors."""
    theme = themes.THEMES[key]
    for variant in ("light", "dark"):
        c = theme[variant]
        assert contrast(c["text"], c["bg"]) >= 4.5 and contrast(c["text"], c["card"]) >= 4.5, variant
        assert contrast(c["soft"], c["card"]) >= 3, variant
        assert contrast(c["on_primary"], c["primary"]) >= 3, variant
        for name in ("primary", "positive", "negative", "warning"):
            assert contrast(c[name], c["card"]) >= 3, (variant, name)
        # text on filled buttons and badges: white in light, the background in dark
        on = "#ffffff" if variant == "light" else c["bg"]
        for name in ("positive", "negative", "warning", "info"):
            assert contrast(on, c[name]) >= 3, (variant, name, "filled")
    assert all(contrast("#ffffff", color) >= 4 for color in theme["header"])  # white text on the header


def test_unknown_falls_back_to_default():
    assert themes.get("nope") is themes.THEMES[themes.DEFAULT]
    assert themes.get(None) is themes.THEMES[themes.DEFAULT]


def test_css_has_both_variants():
    css = themes.css("gruvbox")
    assert themes.THEMES["gruvbox"]["light"]["bg"] in css and themes.THEMES["gruvbox"]["dark"]["bg"] in css
    assert "body.body--dark" in css and "--q-primary" in css
