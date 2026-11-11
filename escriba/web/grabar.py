"""Portada: grabar una reunión."""
import math
from pathlib import Path

from nicegui import run, ui

from .. import config, grabar, tareas
from .comun import dialogo_transcribir, dir_de_proyecto, elegir_ruta, marco, selector_proyecto

# Una sola tarjeta de sonido: la grabación es del servidor, no de la pestaña.
# Sigue aunque se cierre el navegador, y cualquier pestaña puede pararla.
ESTADO = {"g": None, "proyecto": None, "ultima": None}


def _nivel(rms):
    """RMS de voz suele andar por 0,01-0,1: escala logarítmica de 0 a 1."""
    return 0.0 if rms <= 0 else max(0.0, min(1.0, (math.log10(rms) + 4) / 4))


@ui.page("/")
def pagina():
    with marco("/"):
        ui.label("Grabar reunión").classes("text-2xl font-semibold")
        ui.label("Graba lo que suena en el PC (la gente de la llamada) y tu micrófono, mezclados.") \
            .classes("texto-suave -mt-3")

        with ui.card().classes("w-full gap-3") as preparar:
            with ui.row().classes("w-full items-end gap-4"):
                proyecto = selector_proyecto(lambda p: carpeta.set_text(dir_de_proyecto(p)))
                descripcion = ui.input("Descripción", placeholder="seguimiento_semanal").classes("grow")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="grey-7")
                carpeta = ui.label(dir_de_proyecto(proyecto.value) if proyecto.value else "").classes(
                    "font-mono text-sm break-all")
                ui.button("Cambiar", on_click=lambda: cambiar_carpeta()).props("flat dense no-caps")
            ui.label("Avisa a los demás de que grabas la reunión antes de empezar.") \
                .classes("text-sm texto-suave")
            boton = ui.button("Empezar a grabar", icon="fiber_manual_record", color="red",
                              on_click=lambda: empezar()).classes("self-start")

        with ui.card().classes("w-full gap-3") as grabando:
            with ui.row().classes("items-center gap-3"):
                ui.icon("fiber_manual_record", color="red").classes("animate-pulse text-2xl")
                tiempo = ui.label().classes("text-3xl font-mono")
                archivo = ui.label().classes("texto-suave break-all")
            ui.label("Lo que suena").classes("text-sm texto-suave")
            nivel_sistema = ui.linear_progress(value=0, show_value=False).props("instant-feedback rounded size=10px")
            ui.label("Micrófono").classes("text-sm texto-suave")
            nivel_micro = ui.linear_progress(value=0, show_value=False, color="teal") \
                .props("instant-feedback rounded size=10px")
            avisos = ui.label().classes("text-orange-9")
            ui.button("Parar", icon="stop", on_click=lambda: parar()).classes("self-start")

        with ui.card().classes("w-full gap-2") as hecho:
            ultima = ui.label().classes("font-medium break-all")
            with ui.row():
                ui.button("Transcribir", icon="subtitles", on_click=lambda: transcribir_ultima())
                ui.button("Grabar otra", on_click=lambda: (ESTADO.update(ultima=None), refrescar())).props("flat")

    async def cambiar_carpeta():
        if not proyecto.value:
            ui.notify("Elige antes un proyecto", type="warning")
            return
        if ruta := await elegir_ruta(dir_de_proyecto(proyecto.value)):
            config.actualizar_estado(**{f"ultimo_dir_{proyecto.value}": str(ruta)})
            carpeta.set_text(str(ruta))

    async def empezar():
        if not proyecto.value:
            ui.notify("Elige o crea un proyecto", type="warning")
            return
        if ESTADO["g"]:
            return
        destino = Path(carpeta.text) / f"{grabar.nombre_por_defecto(descripcion.value or 'reunion')}.wav"
        if destino.exists():
            ui.notify(f"Ya existe {destino.name}: cambia la descripción", type="warning")
            return
        boton.disable()
        try:
            g, aviso = await run.io_bound(grabar.desde_preferencias, destino)
            g.empezar()
        except Exception as e:
            ui.notify(f"No se puede grabar: {e}", type="negative", multi_line=True)
            return
        finally:
            boton.enable()
        if aviso:
            ui.notify(aviso, type="warning")
        config.actualizar_estado(**{f"ultimo_dir_{proyecto.value}": carpeta.text})
        ESTADO.update(g=g, proyecto=proyecto.value, ultima=None)
        refrescar()

    async def parar():
        g = ESTADO["g"]
        if not g:
            return
        ESTADO["g"] = None
        ruta = await run.io_bound(g.parar)
        ESTADO["ultima"] = (ruta, g.segundos)
        refrescar()

    async def transcribir_ultima():
        ruta, _ = ESTADO["ultima"]
        if await dialogo_transcribir(ruta, ESTADO["proyecto"]):
            ESTADO["ultima"] = None
            refrescar()

    def refrescar():
        g = ESTADO["g"]
        preparar.visible = g is None and ESTADO["ultima"] is None
        grabando.visible = g is not None
        hecho.visible = g is None and ESTADO["ultima"] is not None
        if g:
            s = int(g.segundos)
            tiempo.set_text(f"{s // 60}:{s % 60:02d}")
            archivo.set_text(g.destino.name)
            nivel_sistema.set_value(_nivel(g.niveles["sistema"]))
            nivel_micro.set_value(_nivel(g.niveles["micro"]))
            avisos.set_text("  ".join(g.avisos + g.errores))
        elif ESTADO["ultima"]:
            ruta, segundos = ESTADO["ultima"]
            ultima.set_text(f"Grabado {ruta.name} ({tareas.formato_min(segundos)})")

    refrescar()
    ui.timer(0.2, refrescar)
