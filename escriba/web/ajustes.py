"""Ajustes: claves, glosario, dispositivos de grabación y carpeta de datos."""
from nicegui import run, ui

from .. import config, grabar
from ..transcribir import local_disponible
from .comun import marco

CLAVES = [
    ("ASSEMBLYAI_API_KEY", "Clave de AssemblyAI",
     "Para transcribir en la nube. Se crea en assemblyai.com (la cuenta nueva trae 50 $ de crédito)."),
    ("HF_TOKEN", "Token de Hugging Face",
     "Para separar hablantes en este PC. Se crea en hf.co/settings/tokens y hay que aceptar las condiciones de "
     "pyannote/speaker-diarization-3.1 y pyannote/speaker-diarization-community-1."),
]
POR_DEFECTO = "(el del sistema)"


@ui.page("/ajustes")
def pagina():
    with marco("/ajustes"):
        ui.label("Ajustes").classes("text-2xl font-semibold")

        with ui.card().classes("w-full gap-3"):
            ui.label("Claves").classes("text-lg font-medium")
            for clave, titulo, ayuda in CLAVES:
                _campo_clave(clave, titulo, ayuda)
            secretos = config.dir_datos() / "secretos.env"
            if secretos.is_symlink():
                ui.label(f"Se guardan en {secretos.resolve()} (secretos.env es un enlace).") \
                    .classes("text-sm texto-suave")
            if not local_disponible():
                ui.label("El modo «en este PC» no está instalado: solo se puede transcribir en la nube.") \
                    .classes("text-sm texto-suave")

        with ui.card().classes("w-full gap-3"):
            ui.label("Grabación").classes("text-lg font-medium")
            dispositivos = ui.column().classes("w-full")

        with ui.card().classes("w-full gap-2"):
            ui.label("Apariencia").classes("text-lg font-medium")
            ui.toggle({"sistema": "Como el sistema", "claro": "Claro", "oscuro": "Oscuro"},
                      value=config.cargar_estado().get("tema", "sistema"),
                      on_change=lambda e: cambiar_tema(e.value))

        with ui.card().classes("w-full gap-2"):
            ui.label("Glosario").classes("text-lg font-medium")
            ui.label("Nombres de personas, empresas y términos que salen en tus reuniones, separados por comas "
                     "o uno por línea. Ayuda a que se escriban bien en los dos modos.").classes("text-sm texto-suave")
            glosario = ui.textarea(value=config.ruta_glosario().read_text(encoding="utf-8")) \
                .props("outlined autogrow").classes("w-full font-mono text-sm")
            ui.button("Guardar glosario", icon="save", on_click=lambda: guardar_glosario()).classes("self-start")

        with ui.card().classes("w-full gap-1"):
            ui.label("Tus datos").classes("text-lg font-medium")
            ui.label(f"Voces, glosario, claves y estado: {config.dir_datos()}").classes("font-mono text-sm break-all")
            ui.label("Las voces son datos biométricos de otras personas: no las compartas.") \
                .classes("text-sm texto-suave")

    def cambiar_tema(valor):
        config.actualizar_estado(tema=valor)
        ui.dark_mode({"claro": False, "oscuro": True}.get(valor))

    def guardar_glosario():
        config.ruta_glosario().write_text(glosario.value, encoding="utf-8")
        ui.notify("Glosario guardado", type="positive")

    async def cargar_dispositivos():
        try:
            disp = await run.io_bound(grabar.listar_dispositivos)
        except Exception as e:
            with dispositivos:
                ui.label(f"No se pueden listar los dispositivos de audio: {e}").classes("text-negative")
            return
        estado = config.cargar_estado()
        with dispositivos:
            for clave, titulo, lista in (("altavoz", "Lo que suena (salida)", disp["altavoces"]),
                                         ("micro", "Micrófono", disp["micros"])):
                defecto = next((n for n, d in lista if d), "")
                # "" = el del sistema (una clave None no sobrevive al viaje al navegador)
                opciones = {"": f"{POR_DEFECTO}: {defecto}"} | {n: n for n, _ in lista}
                actual = estado.get(clave) if estado.get(clave) in opciones else ""
                ui.select(opciones, label=titulo, value=actual,
                          on_change=lambda e, c=clave: guardar_dispositivo(c, e.value)).classes("w-full")

    def guardar_dispositivo(clave, valor):
        config.actualizar_estado(**{clave: valor or None})
        ui.notify("Guardado: se usará en la próxima grabación", type="positive")

    ui.timer(0.1, cargar_dispositivos, once=True)


def _campo_clave(clave, titulo, ayuda):
    puesta = bool(config.leer_secreto(clave))
    with ui.column().classes("w-full gap-1"):
        with ui.row().classes("w-full items-end gap-2"):
            campo = ui.input(titulo, password=True, password_toggle_button=True,
                             placeholder="configurada (escribe para cambiarla)" if puesta else "") \
                .classes("grow")
            estado = ui.badge("configurada" if puesta else "falta", color="positive" if puesta else "orange")
            ui.button("Guardar", on_click=lambda: guardar()).props("flat")
        ui.label(ayuda).classes("text-sm texto-suave")

    def guardar():
        valor = (campo.value or "").strip()
        if not valor:
            ui.notify("Escribe la clave antes de guardar", type="warning")
            return
        config.guardar_secreto(clave, valor)
        campo.set_value("")
        campo.props('placeholder="configurada (escribe para cambiarla)"')
        estado.set_text("configurada")
        estado.props("color=positive")
        ui.notify(f"{titulo} guardada", type="positive")
