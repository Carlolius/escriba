"""escriba's web interface (NiceGUI). It opens in the browser and only listens
on this PC (127.0.0.1): nobody on the network can reach it."""


def run(port=8765, open_browser=True):
    from nicegui import app, ui

    from .. import i18n
    from . import meetings, people, record, review, settings, transcribe  # noqa: F401  (they register the pages)
    from .common import COLORS, LOGO, STATIC

    app.add_static_files("/static", STATIC)
    app.colors(**COLORS)
    ui.run(host="127.0.0.1", port=port, title="Escriba", favicon=LOGO,
           language="es" if i18n.language() == "es" else "en-US",
           reload=False, show=open_browser, show_welcome_message=False)
