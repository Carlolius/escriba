"""Piezas compartidas por todas las páginas: el marco (cabecera y navegación),
los fragmentos de audio, el explorador de carpetas y el diálogo de transcribir."""
import io
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

import soundfile as sf
from fastapi import Response
from nicegui import app, run, ui

from .. import audio as audio_util
from .. import config, tareas
from ..transcribir import clave_que_falta, local_disponible

SECCIONES = [
    ("/", "Grabar", "mic"),
    ("/transcribir", "Transcribir", "subtitles"),
    ("/revisar", "Revisar", "record_voice_over"),
    ("/personas", "Personas", "groups"),
    ("/ajustes", "Ajustes", "settings"),
]

IDIOMAS = {
    "auto": "Detectar solo",
    "es": "Castellano",
    "gl": "Gallego (respeta la mezcla con castellano)",
    "en": "Inglés",
    "ca": "Catalán",
    "pt": "Portugués",
    "fr": "Francés",
    "de": "Alemán",
}
MODELOS = {
    "medium": "medium (recomendado)",
    "turbo": "turbo: ~25% más rápido, a veces se salta frases",
    "large": "large: el más preciso y lento (~3 GB)",
    "small": "small",
    "base": "base",
    "tiny": "tiny",
}


# ── Marco de página ──────────────────────────────────────────────────────────

COLOR_CABECERA = "#2f4858"
# En oscuro el azul tinta no se lee sobre negro: se aclara el color principal
# (botones planos, pestañas, barras) y los botones rellenos pasan a texto oscuro.
CSS = """
.texto-suave { color: #5b6770; }
body.body--dark .texto-suave { color: #a9b5bd; }
body.body--dark { --q-primary: #8db7d1 !important; }  /* NiceGUI lo pone en línea en <body> */
body.body--dark .q-btn.bg-primary { color: #10212b !important; }
"""

@contextmanager
def marco(ruta_actual):
    """Cabecera con navegación y estado (grabando, transcripciones en marcha);
    lo de dentro del with va a la columna central."""
    from . import grabar as pagina_grabar

    ui.page_title("Escriba")
    tema = config.cargar_estado().get("tema", "sistema")
    ui.dark_mode({"claro": False, "oscuro": True}.get(tema))  # None = el del sistema
    ui.add_css(CSS)
    with ui.header().classes("items-center gap-1 px-4 py-2").style(f"background-color: {COLOR_CABECERA}"):
        ui.label("Escriba").classes("text-lg font-semibold mr-4")
        for ruta, titulo, icono in SECCIONES:
            b = ui.button(titulo, icon=icono, on_click=lambda r=ruta: ui.navigate.to(r)).props("flat no-caps")
            b.classes("text-white" + (" bg-white/20" if ruta == ruta_actual else ""))
        ui.space()
        grabando = ui.label().classes("text-white font-medium")
        en_marcha = ui.label().classes("text-white/90 text-sm")

    def refrescar_cabecera():
        g = pagina_grabar.ESTADO["g"]
        grabando.visible = g is not None
        if g:
            s = int(g.segundos)
            grabando.set_text(f"● Grabando {s // 60}:{s % 60:02d}")
        n = len(tareas.audios_en_curso())
        en_marcha.visible = n > 0
        en_marcha.set_text(f"{n} transcripción{'es' if n > 1 else ''} en marcha")

    ui.timer(1.0, refrescar_cabecera)
    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
        yield


# ── Fragmentos de audio ──────────────────────────────────────────────────────
# La web nunca recibe rutas: cada fragmento que se enseña se apunta aquí con
# una ficha aleatoria, y /fragmento/<ficha> solo sirve lo apuntado.

_FRAGMENTOS = {}
_MAX_FRAGMENTOS = 5000


def reproductor(origen):
    """ui.audio para {"audio", "inicio", "fin"}, o un aviso si no se puede."""
    if not origen:
        return ui.label("Sin audio de origen guardado").classes("text-sm texto-suave")
    if not Path(origen["audio"]).exists():
        return ui.label(f"No se encuentra {Path(origen['audio']).name}").classes("text-sm texto-suave")
    if len(_FRAGMENTOS) > _MAX_FRAGMENTOS:
        _FRAGMENTOS.clear()
    ficha = secrets.token_urlsafe(16)
    _FRAGMENTOS[ficha] = (origen["audio"], float(origen["inicio"]), float(origen["fin"]))
    return ui.audio(f"/fragmento/{ficha}").props("preload=none").classes("w-full max-w-sm h-10")


def _wav_de(ruta, inicio, fin):
    datos, sr = audio_util.leer_fragmento(ruta, inicio, fin)
    buf = io.BytesIO()
    sf.write(buf, datos, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@app.get("/fragmento/{ficha}")
async def _servir_fragmento(ficha: str):
    if ficha not in _FRAGMENTOS:
        return Response(status_code=404)
    datos = await run.io_bound(_wav_de, *_FRAGMENTOS[ficha])
    return Response(datos, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# ── Proyecto y carpetas ──────────────────────────────────────────────────────

def selector_proyecto(on_change, etiqueta="Proyecto"):
    """Select de proyectos con opción de crear uno nuevo. Llama a on_change(nombre)."""
    proyectos = config.listar_proyectos()
    ultimo = config.cargar_estado().get("ultimo_proyecto")
    valor = ultimo if ultimo in proyectos else (proyectos[0] if proyectos else None)

    def cambiar(e):
        if e.value:
            config.crear_proyecto(e.value)  # no hace nada si ya existe
            config.actualizar_estado(ultimo_proyecto=e.value)
            on_change(e.value)

    sel = ui.select(proyectos, label=etiqueta, value=valor, with_input=True, new_value_mode="add-unique",
                    on_change=cambiar).classes("min-w-48")
    sel.tooltip("Elige uno, o escribe un nombre nuevo y pulsa Enter para crearlo")
    return sel


def dir_de_proyecto(proyecto):
    return config.cargar_estado().get(f"ultimo_dir_{proyecto}") or str(Path.home())


def _raices():
    if os.name == "nt":
        import psutil
        return [p.mountpoint for p in psutil.disk_partitions()]
    return ["/"]


async def elegir_ruta(inicial, carpetas=True, extensiones=(".wav", ".opus", ".flac", ".ogg")):
    """Explorador de carpetas del PC (el navegador no puede elegirlas).
    Con carpetas=False también enseña archivos de audio. Devuelve la ruta o None."""
    actual = {"ruta": Path(inicial).expanduser() if inicial else Path.home()}
    if not actual["ruta"].is_dir():
        actual["ruta"] = Path.home()

    with ui.dialog() as dialogo, ui.card().classes("w-[36rem] max-w-full"):
        ruta_txt = ui.label().classes("font-mono text-sm break-all")
        lista = ui.list().props("dense separator").classes("w-full h-80 overflow-auto")
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancelar", on_click=lambda: dialogo.submit(None)).props("flat")
            if carpetas:
                ui.button("Elegir esta carpeta", on_click=lambda: dialogo.submit(actual["ruta"]))

    def pintar():
        ruta = actual["ruta"]
        ruta_txt.set_text(str(ruta))
        lista.clear()
        try:
            hijos = sorted((p for p in ruta.iterdir() if not p.name.startswith(".")), key=lambda p: p.name.lower())
        except OSError:
            hijos = []
        with lista:
            if ruta.parent != ruta:
                _item("..", "arrow_upward", lambda: ir(ruta.parent))
            elif os.name == "nt":
                for raiz in _raices():
                    _item(raiz, "storage", lambda r=raiz: ir(Path(r)))
            for p in hijos:
                if p.is_dir():
                    _item(p.name, "folder", lambda p=p: ir(p))
                elif not carpetas and p.suffix.lower() in extensiones:
                    _item(p.name, "audio_file", lambda p=p: dialogo.submit(p))

    def ir(ruta):
        actual["ruta"] = ruta
        pintar()

    pintar()
    return await dialogo


def _item(texto, icono, accion):
    with ui.item(on_click=accion).props("clickable"):
        with ui.item_section().props("avatar"):
            ui.icon(icono, color="grey-7")
        ui.item_section(texto)


# ── Transcribir ──────────────────────────────────────────────────────────────

async def dialogo_transcribir(audio, proyecto):
    """Pregunta motor/idioma/modelo y lanza la transcripción en segundo plano.
    Devuelve True si se lanzó."""
    local = local_disponible()
    dur = await run.io_bound(audio_util.duracion, audio)
    with ui.dialog() as dialogo, ui.card().classes("w-[30rem] max-w-full gap-3"):
        ui.label(Path(audio).name).classes("text-lg font-medium break-all")
        if dur:
            ui.label(f"{tareas.formato_min(dur)} de audio · proyecto {proyecto}").classes("texto-suave")
        motor = ui.toggle({"nube": "En la nube", "local": "En este PC"}, value="nube")
        if not local:
            motor.props("disable")
        explicacion = ui.label().classes("text-sm texto-suave")
        idioma = ui.select(IDIOMAS, label="Idioma", value="auto").classes("w-full")
        modelo = ui.select(MODELOS, label="Modelo", value="medium").classes("w-full")
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancelar", on_click=lambda: dialogo.submit(None)).props("flat")
            ui.button("Transcribir", icon="play_arrow", on_click=lambda: dialogo.submit(True))

    def explicar():
        modelo.visible = motor.value == "local"
        if motor.value == "nube":
            texto = "AssemblyAI: unos minutos, ~0,23 $ por hora de audio. El audio sale del PC y se borra al acabar."
        else:
            espera = f" (~{tareas.formato_min(dur * tareas.FACTOR_PROCESO)} para este audio)" if dur else ""
            texto = f"Gratis y el audio no sale del PC, pero lento{espera}."
        if not local:
            texto += " El modo en este PC no está instalado."
        explicacion.set_text(texto)

    motor.on_value_change(explicar)
    explicar()
    if not await dialogo:
        return False
    if clave := clave_que_falta(motor.value):
        ui.notify(f"Falta la clave {clave}: ponla en Ajustes", type="negative")
        return False
    await run.io_bound(tareas.lanzar, audio, proyecto, motor.value, modelo.value, idioma.value)
    ui.notify(f"Transcribiendo {Path(audio).name} en segundo plano", type="positive")
    return True
