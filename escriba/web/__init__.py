"""Interfaz web de escriba (NiceGUI). Se abre en el navegador y solo escucha
en este PC (127.0.0.1): nadie de la red puede entrar."""


def arrancar(puerto=8765, abrir=True):
    from nicegui import app, ui

    from . import ajustes, grabar, personas, revisar, transcribir  # noqa: F401  (registran las páginas)

    app.colors(primary="#2f4858", secondary="#86624a", accent="#b5835a")
    ui.run(host="127.0.0.1", port=puerto, title="Escriba", favicon="🪶", language="es",
           reload=False, show=abrir, show_welcome_message=False)
