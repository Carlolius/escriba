"""Revisar hablantes: confirmar, corregir o saltar cada voz de una transcripción."""
from nicegui import run, ui

from .. import revisar
from .comun import marco, reproductor


@ui.page("/revisar")
def pagina():
    with marco("/revisar"):
        contenido = ui.column().classes("w-full gap-4")

    async def lista():
        contenido.clear()
        with contenido:
            ui.label("Revisar hablantes").classes("text-2xl font-semibold")
            ui.label("Confirmar o corregir cada voz enseña a reconocerla la próxima vez.") \
                .classes("texto-suave -mt-3")
            cargando = ui.spinner()
        pendientes = await run.io_bound(revisar.pendientes)
        cargando.delete()
        with contenido:
            if not pendientes:
                ui.label("No hay transcripciones pendientes de revisar.").classes("texto-suave")
            with ui.list().props("bordered separator").classes("w-full"):
                for proyecto, sidecar in pendientes:
                    nombre = sidecar.name.removesuffix(revisar.SUFIJO)
                    with ui.item(on_click=lambda p=proyecto, s=sidecar: reunion(p, s)).props("clickable"):
                        with ui.item_section():
                            ui.item_label(nombre)
                            ui.item_label(proyecto).props("caption")
                        with ui.item_section().props("side"):
                            ui.icon("chevron_right")

    async def reunion(proyecto, sidecar):
        contenido.clear()
        with contenido:
            with ui.row().classes("items-center gap-2"):
                ui.button(icon="arrow_back", on_click=lista).props("flat round")
                ui.label(sidecar.name.removesuffix(revisar.SUFIJO)).classes("text-xl font-semibold break-all")
                ui.badge(proyecto).props("outline")
            transcripcion = ui.expansion("Ver transcripción", icon="article").classes("w-full")
            hablantes = ui.column().classes("w-full gap-3")
        datos = await run.io_bound(_cargar, sidecar, proyecto)

        def pintar_transcripcion():
            transcripcion.clear()
            txt = revisar.ruta_txt(sidecar)
            with transcripcion:
                texto = txt.read_text(encoding="utf-8") if txt.exists() else "(sin transcripción)"
                ui.label(texto).classes("whitespace-pre-wrap text-sm max-h-96 overflow-auto")

        def pintar():
            hablantes.clear()
            data = revisar.leer(sidecar)
            with hablantes:
                for spk, info in data["clusters"].items():
                    _tarjeta(spk, info, datos["frases"].get(spk, []), datos["conocidos"], decidir)
                if data.get("revisado"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("task_alt", color="positive", size="md")
                        ui.label("Reunión revisada").classes("text-lg")
                        ui.button("Volver a la lista", on_click=lista).props("flat no-caps")

        async def decidir(spk, nombre):
            r = await run.io_bound(revisar.decidir, sidecar, spk, nombre, proyecto)
            if nombre:
                if nombre not in datos["conocidos"]:
                    datos["conocidos"].append(nombre)
                extra = f", renombrado en {r['renombradas']} sitios" if r["renombradas"] else ""
                ui.notify(f"{nombre}: {r['muestras']} muestras{extra}", type="positive")
            pintar()
            if r["renombradas"]:
                pintar_transcripcion()
            if r["completa"]:
                # El botón que disparó esto ya no existe (pintar() rehace las
                # tarjetas): el aviso se cuelga de algo que sigue en la página
                with contenido:
                    await _archivar(sidecar)

        pintar_transcripcion()
        pintar()

    ui.timer(0.1, lista, once=True)


def _cargar(sidecar, proyecto):
    return {"frases": revisar.frases_por_cluster(sidecar), "conocidos": revisar.nombres_conocidos(sidecar, proyecto)}


async def _archivar(sidecar):
    aviso = ui.notification("Comprimiendo el audio a Opus para archivarlo...", spinner=True, timeout=None)
    try:
        hecho = await run.io_bound(revisar.archivar_si_completa, sidecar)
    except Exception as e:  # el WAV se queda tal cual si algo falla
        aviso.message, aviso.type = f"No se pudo comprimir: {e}", "warning"
    else:
        aviso.message = f"Audio archivado ({hecho[1] / 1e6:.0f} MB menos)" if hecho else "Listo"
        aviso.type = "positive"
    aviso.spinner = False
    aviso.timeout = 4


def _tarjeta(spk, info, frases, conocidos, decidir):
    revisado = info.get("revisado")
    sin_nombre = info["nombre"].startswith("Hablante ")
    with ui.card().classes("w-full gap-2" + (" opacity-60" if revisado else "")):
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(info["nombre"]).classes("text-lg font-medium")
            if revisado:
                ui.badge("revisado", color="positive")
            elif sin_nombre:
                ui.badge("sin identificar", color="orange")
            ui.space()
            sim = info.get("similitud")
            detalle = f"{info['duracion_hablada']:.0f} s hablados"
            if sim is not None:
                detalle += f" · parecido {sim:.2f}"
            ui.label(detalle).classes("text-sm texto-suave")
        for frase in frases or ["(no hay frases largas suyas en la transcripción)"]:
            ui.label(f"«{frase}»").classes("italic texto-suave")
        reproductor(info.get("origen"))
        if revisado:
            return
        with ui.row().classes("w-full items-end gap-2"):
            nombre = ui.input("¿Quién es?", value="" if sin_nombre else info["nombre"],
                              autocomplete=conocidos).classes("grow")
            nombre.on("keydown.enter", lambda: confirmar())
            ui.button("Confirmar", icon="check", on_click=lambda: confirmar())
            ui.button("No lo sé", on_click=lambda: decidir(spk, "")).props("flat no-caps") \
                .tooltip("Se marca como revisado sin guardar nada en la librería de voces")

    async def confirmar():
        valor = (nombre.value or "").strip()
        if not valor:
            ui.notify("Escribe quién es, o pulsa «No lo sé»", type="warning")
            return
        await decidir(spk, valor)

