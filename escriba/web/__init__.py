"""escriba's web interface (NiceGUI). It opens in the browser and only listens
on this PC (127.0.0.1): nobody on the network can reach it."""


def run(port=8765, open_browser=True):
    from nicegui import app, ui

    from .. import i18n
    from . import people, record, review, settings, transcribe  # noqa: F401  (they register the pages)

    app.colors(primary="#2f4858", secondary="#86624a", accent="#b5835a")
    ui.run(host="127.0.0.1", port=port, title="Escriba", favicon="🪶",
           language="es" if i18n.language() == "es" else "en-US",
           reload=False, show=open_browser, show_welcome_message=False)
