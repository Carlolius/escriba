"""escriba's web interface (NiceGUI). It opens in the browser and only listens
on this PC (127.0.0.1): nobody on the network can reach it."""


def run(port=8765, open_browser=True):
    from nicegui import app, ui

    from .. import i18n
    from . import meetings, people, projects, record, review, settings, transcribe  # noqa: F401  (they register the pages)
    from .common import COLORS, LOGO, STATIC

    from starlette.middleware.trustedhost import TrustedHostMiddleware

    # Only requests addressed to this PC: a web page using DNS rebinding
    # can't drive escriba from the browser (read transcripts, delete...)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    def stop_recording():
        """Closing escriba (Ctrl+C, closing the window) ends the recording
        properly, so the WAV is complete."""
        if record.STATE["recording"]:
            record.STATE["recording"].stop()

    app.on_shutdown(stop_recording)
    app.add_static_files("/static", STATIC)
    app.colors(**COLORS)
    ui.run(host="127.0.0.1", port=port, title="Escriba", favicon=LOGO,
           language="es" if i18n.language() == "es" else "en-US",
           reload=False, show=open_browser, show_welcome_message=False)
