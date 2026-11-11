"""Transcribir: audios pendientes de un proyecto y transcripciones en marcha."""
from datetime import datetime
from pathlib import Path

from nicegui import run, ui

from .. import config, tareas
from .comun import dialogo_transcribir, dir_de_proyecto, elegir_ruta, marco, selector_proyecto


@ui.page("/transcribir")
def pagina():
    with marco("/transcribir"):
        ui.label("Transcribir").classes("text-2xl font-semibold")

        with ui.card().classes("w-full gap-2"):
            ui.label("En marcha").classes("text-lg font-medium")
            en_marcha = ui.column().classes("w-full gap-1")

        with ui.card().classes("w-full gap-3"):
            with ui.row().classes("w-full items-end gap-4"):
                proyecto = selector_proyecto(lambda p: cargar())
                ui.space()
                ui.button("Otro archivo...", icon="audio_file", on_click=lambda: otro_archivo()).props("flat no-caps")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="grey-7")
                carpeta = ui.label().classes("font-mono text-sm break-all")
                ui.button("Cambiar", on_click=lambda: cambiar_carpeta()).props("flat dense no-caps")
            lista = ui.column().classes("w-full gap-1")

    async def cargar():
        if not proyecto.value:
            return
        carpeta.set_text(dir_de_proyecto(proyecto.value))
        lista.clear()
        with lista:
            ui.spinner()
        audios = await run.io_bound(tareas.audios_pendientes, carpeta.text)
        lista.clear()
        with lista:
            if not audios:
                ui.label("No hay audios sin transcribir en esta carpeta.").classes("texto-suave")
            for ruta, dur in audios:
                with ui.row().classes("w-full items-center gap-3 py-1 border-b border-gray-500/20"):
                    with ui.column().classes("grow gap-0"):
                        ui.label(str(ruta.relative_to(carpeta.text))).classes("break-all")
                        fecha = datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                        detalle = f"{tareas.formato_min(dur)} · {fecha}" if dur else fecha
                        ui.label(detalle).classes("text-sm texto-suave")
                    ui.button("Transcribir", icon="play_arrow", on_click=lambda r=ruta: transcribir(r)) \
                        .props("flat no-caps")

    async def transcribir(ruta):
        if await dialogo_transcribir(ruta, proyecto.value):
            await cargar()
            await pintar_en_marcha()

    async def cambiar_carpeta():
        if ruta := await elegir_ruta(carpeta.text):
            config.actualizar_estado(**{f"ultimo_dir_{proyecto.value}": str(ruta)})
            await cargar()

    async def otro_archivo():
        if ruta := await elegir_ruta(carpeta.text, carpetas=False):
            await transcribir(ruta)

    # revisar_en_curso() avisa de cada tarea acabada una sola vez: se guardan
    # aquí para seguir enseñándolas mientras la página esté abierta
    acabadas = []

    async def pintar_en_marcha():
        nuevas = await run.io_bound(tareas.revisar_en_curso)
        for t, est, _ in nuevas:
            if est != "en_curso":
                ui.notify(f"{'Terminada' if est == 'terminada' else 'Falló'}: {Path(t['audio']).name}",
                          type="positive" if est == "terminada" else "negative")
        acabadas.extend(x for x in nuevas if x[1] != "en_curso")
        resultado = [x for x in nuevas if x[1] == "en_curso"] + acabadas
        en_marcha.clear()
        with en_marcha:
            if not resultado:
                ui.label("Nada ahora mismo.").classes("texto-suave")
            for t, est, texto in resultado:
                nombre = Path(t["audio"]).name
                with ui.row().classes("w-full items-center gap-2"):
                    if est == "en_curso":
                        ui.spinner(size="sm")
                        ui.label(nombre).classes("font-medium")
                        ui.label(texto).classes("texto-suave")
                    elif est == "terminada":
                        ui.icon("check_circle", color="positive")
                        ui.label(f"{nombre}: terminada").classes("font-medium")
                        ui.button("Revisar hablantes", on_click=lambda: ui.navigate.to("/revisar")) \
                            .props("flat dense no-caps")
                    else:
                        ui.icon("error", color="negative")
                        ui.label(f"{nombre}: falló").classes("font-medium")
                        _ver_log(t["log"])

    ui.timer(0.1, cargar, once=True)
    ui.timer(3.0, pintar_en_marcha)


def _ver_log(ruta):
    def abrir():
        try:
            texto = Path(ruta).read_text(encoding="utf-8", errors="replace")[-6000:]
        except OSError as e:
            texto = str(e)
        with ui.dialog() as d, ui.card().classes("w-[48rem] max-w-full"):
            ui.code(texto, language=None).classes("w-full max-h-96 overflow-auto")
            ui.button("Cerrar", on_click=d.close).props("flat")
        d.open()

    ui.button("Ver log", on_click=abrir).props("flat dense no-caps")
