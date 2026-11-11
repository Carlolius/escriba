"""Personas: la librería de voces de cada proyecto, su auditoría y muestras a mano."""
from pathlib import Path

from nicegui import run, ui

from .. import revisar, rutas, voiceprints
from .comun import dir_de_proyecto, elegir_ruta, marco, reproductor, selector_proyecto

EXPLICACION = {
    "confusion": "Dos personas con muestras muy parecidas: riesgo de confundirlas. "
                 "Si es la misma persona, reclasifica; si una muestra es mala, bórrala.",
    "duplicado": "Dos muestras casi idénticas de la misma persona: puedes borrar una.",
    "dispersion": "Dos muestras de la misma persona poco parecidas: puede que una sea de otra persona.",
}
TITULO = {"confusion": "Posible confusión", "duplicado": "Muestras casi duplicadas", "dispersion": "Muestras dispersas"}


def _etiqueta(muestra):
    origen = muestra.get("origen")
    if not origen:
        return "sin audio de origen"
    return f"{Path(origen['audio']).name} · {origen['inicio']:.0f}-{origen['fin']:.0f} s"


@ui.page("/personas")
def pagina():
    with marco("/personas"):
        ui.label("Personas").classes("text-2xl font-semibold")
        with ui.row().classes("w-full items-end gap-4"):
            proyecto = selector_proyecto(lambda p: recargar())
            ui.space()
            ui.button("Añadir muestra a mano", icon="add", on_click=lambda: anadir()).props("flat no-caps")
            ui.button("Deshacer último cambio", icon="undo", on_click=lambda: deshacer()).props("flat no-caps")
            ui.button("Reparar rutas", icon="build", on_click=lambda: reparar()).props("flat no-caps") \
                .tooltip("Si moviste reuniones de carpeta, busca sus audios para que se puedan volver a escuchar")
        with ui.tabs().classes("w-full") as pestanas:
            ui.tab("personas", label="Personas", icon="groups")
            pestana_auditoria = ui.tab("auditoria", label="Auditoría", icon="fact_check")
        with ui.tab_panels(pestanas, value="personas").classes("w-full"):
            with ui.tab_panel("personas"):
                lista = ui.column().classes("w-full gap-2")
            with ui.tab_panel("auditoria"):
                auditoria = ui.column().classes("w-full gap-3")

    vistos = set()  # hallazgos saltados en esta visita

    async def recargar():
        if not proyecto.value:
            return
        p = proyecto.value
        datos, hallazgos = await run.io_bound(lambda: (voiceprints.cargar_libreria_con_origen(p),
                                                       voiceprints.auditar_libreria(p)))
        pintar_personas(p, datos)
        pintar_auditoria(p, hallazgos, datos)

    def pintar_personas(p, datos):
        lista.clear()
        with lista:
            if not datos:
                ui.label("Este proyecto aún no tiene voces. Se añaden al revisar hablantes.").classes("texto-suave")
            for nombre, muestras in sorted(datos.items(), key=lambda x: x[0].lower()):
                with ui.expansion(f"{nombre} ({len(muestras)} muestras)", icon="person").classes("w-full"):
                    for m in muestras:
                        with ui.row().classes("w-full items-center gap-2 py-1 border-b border-gray-500/20"):
                            ui.label(_etiqueta(m)).classes("text-sm grow break-all")
                            reproductor(m.get("origen"))
                            _acciones_muestra(p, nombre, m["id"], datos)
                    ui.button(f"Borrar a {nombre} entero", icon="delete", color="negative",
                              on_click=lambda n=nombre: borrar_persona(p, n)).props("flat no-caps")

    def pintar_auditoria(p, hallazgos, datos):
        pendientes = [h for h in hallazgos if (h["tipo"], h["id_a"], h["id_b"]) not in vistos]
        pestana_auditoria.props(f'label="Auditoría ({len(pendientes)})"' if pendientes else 'label="Auditoría"')
        auditoria.clear()
        with auditoria:
            if not pendientes:
                ui.label("Sin hallazgos pendientes.").classes("texto-suave")
            orden = sorted(pendientes, key=lambda h: -h["similitud"] if h["tipo"] != "dispersion" else h["similitud"])
            for h in orden[:20]:
                _tarjeta_hallazgo(p, h, datos)
            if len(orden) > 20:
                ui.label(f"Y {len(orden) - 20} más: aparecen al resolver estos.").classes("texto-suave")

    def _tarjeta_hallazgo(p, h, datos):
        color = "negative" if h["tipo"] == "confusion" and h["similitud"] >= voiceprints.UMBRAL_DEFECTO else "orange"
        with ui.card().classes("w-full gap-2"):
            with ui.row().classes("items-center gap-2"):
                ui.badge(TITULO[h["tipo"]], color=color)
                ui.label(f"parecido {h['similitud']:.2f}").classes("texto-suave")
            ui.label(EXPLICACION[h["tipo"]]).classes("text-sm texto-suave")
            for lado in ("a", "b"):
                nombre, id_m = h[f"nombre_{lado}"], h[f"id_{lado}"]
                muestra = next((m for m in datos.get(nombre, []) if m["id"] == id_m), None)
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label(nombre).classes("font-medium w-32")
                    if muestra:
                        reproductor(muestra.get("origen"))
                        _acciones_muestra(p, nombre, id_m, datos)
            with ui.row():
                ui.button("Está bien así", icon="done",
                          on_click=lambda: correcto(p, h)).props("flat no-caps") \
                    .tooltip("No volver a avisar de este caso")
                ui.button("Ahora no", on_click=lambda: saltar(h)).props("flat no-caps")

    def _acciones_muestra(p, nombre, id_m, datos):
        with ui.button(icon="more_vert").props("flat round dense"):
            with ui.menu():
                ui.menu_item("Es de otra persona...", on_click=lambda: reclasificar(p, nombre, id_m, datos))
                ui.menu_item("Borrar esta muestra", on_click=lambda: borrar_muestra(p, nombre, id_m))

    async def reclasificar(p, nombre, id_m, datos):
        with ui.dialog() as d, ui.card().classes("w-96 max-w-full"):
            ui.label(f"Esta muestra está en {nombre}. ¿De quién es?")
            nuevo = ui.input("Persona", autocomplete=sorted(datos)).classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancelar", on_click=lambda: d.submit(None)).props("flat")
                ui.button("Mover", on_click=lambda: d.submit((nuevo.value or "").strip()))
        destino = await d
        if destino and destino != nombre:
            await run.io_bound(voiceprints.reclasificar_muestra, p, nombre, id_m, destino)
            ui.notify(f"Movida a {destino}", type="positive")
            await recargar()

    async def borrar_muestra(p, nombre, id_m):
        await run.io_bound(voiceprints.eliminar_muestra, p, nombre, id_m)
        ui.notify("Muestra borrada (se puede deshacer)", type="positive")
        await recargar()

    async def borrar_persona(p, nombre):
        if await _confirmar(f"¿Borrar a {nombre} y todas sus muestras?"):
            await run.io_bound(voiceprints.eliminar_persona, p, nombre)
            ui.notify(f"{nombre} borrado (se puede deshacer)", type="positive")
            await recargar()

    async def correcto(p, h):
        await run.io_bound(voiceprints.marcar_como_correcto, p, h["tipo"], h["id_a"], h["id_b"])
        await recargar()

    async def saltar(h):
        vistos.add((h["tipo"], h["id_a"], h["id_b"]))
        await recargar()

    async def deshacer():
        if not proyecto.value:
            return
        if not Path(voiceprints.ruta_libreria(proyecto.value) + ".bak").exists():
            ui.notify("No hay nada que deshacer todavía", type="info")
            return
        if await _confirmar("Se deshace el último borrado o cambio de persona (un solo paso atrás). ¿Seguir?"):
            await run.io_bound(voiceprints.restaurar_backup, proyecto.value)
            ui.notify("Deshecho", type="positive")
            await recargar()

    async def reparar():
        r = await run.io_bound(rutas.reparar)
        arregladas = sum(refs for _, _, refs in r["arregladas"])
        if not any(r.values()):
            ui.notify("Todas las muestras apuntan a audios que existen", type="positive")
        else:
            partes = [f"{len(r['arregladas'])} audios encontrados ({arregladas} referencias arregladas)"]
            if r["sin_encontrar"]:
                partes.append(f"{len(r['sin_encontrar'])} sin encontrar")
            if r["dudosas"]:
                partes.append(f"{len(r['dudosas'])} con varios candidatos (no se tocan)")
            ui.notify(", ".join(partes), type="positive" if r["arregladas"] else "warning", multi_line=True)
        await recargar()

    async def anadir():
        if not proyecto.value:
            return
        ruta = await elegir_ruta(dir_de_proyecto(proyecto.value), carpetas=False)
        if not ruta:
            return
        with ui.dialog() as d, ui.card().classes("w-96 max-w-full"):
            ui.label(ruta.name).classes("font-medium break-all")
            with ui.row().classes("w-full"):
                inicio = ui.number("Desde (s)", min=0, value=0).classes("w-24")
                fin = ui.number("Hasta (s)", min=0, value=10).classes("w-24")
            nombre = ui.input("Persona", autocomplete=sorted(voiceprints.cargar_libreria(proyecto.value))) \
                .classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancelar", on_click=lambda: d.submit(False)).props("flat")
                ui.button("Añadir", on_click=lambda: d.submit(True))
        if not await d or not (nombre.value or "").strip() or (fin.value or 0) <= (inicio.value or 0):
            return
        n, anadida = await run.io_bound(revisar.enrolar, ruta, inicio.value, fin.value, nombre.value.strip(),
                                        proyecto.value)
        ui.notify(f"{nombre.value}: {n} muestras" + ("" if anadida else " (ya había una casi idéntica)"),
                  type="positive")
        await recargar()

    ui.timer(0.1, recargar, once=True)


async def _confirmar(pregunta):
    with ui.dialog() as d, ui.card():
        ui.label(pregunta)
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancelar", on_click=lambda: d.submit(False)).props("flat")
            ui.button("Sí", color="negative", on_click=lambda: d.submit(True))
    return await d
