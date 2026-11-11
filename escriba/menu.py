"""Menú interactivo de terminal para grabar, transcribir e identificar hablantes.

Toda la lógica está en el resto del paquete; aquí solo se pregunta y se
enseña. La interfaz web usa las mismas funciones.
"""
import os
import time
from pathlib import Path

import questionary
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.table import Table

from . import audio as audio_util
from . import config, grabar, revisar, tareas, voiceprints
from .transcribir import local_disponible

console = Console()

NUEVO_PROYECTO = "+ nuevo proyecto..."
OTRA_RUTA = "Escribir otra ruta..."


# ── Elecciones comunes ───────────────────────────────────────────────────────

def elegir_proyecto():
    proyectos = config.listar_proyectos()
    ultimo = config.cargar_estado().get("ultimo_proyecto")
    default = ultimo if ultimo in proyectos else None
    eleccion = questionary.select("Proyecto:", choices=proyectos + [NUEVO_PROYECTO], default=default).ask()
    if eleccion is None:
        return None
    if eleccion == NUEVO_PROYECTO:
        eleccion = questionary.text("Nombre del proyecto nuevo (ej. cliente_x):").ask()
        if not eleccion:
            return None
        config.crear_proyecto(eleccion)
    config.actualizar_estado(ultimo_proyecto=eleccion)
    return eleccion


def _dir_proyecto(proyecto):
    return config.cargar_estado().get(f"ultimo_dir_{proyecto}", str(Path.home()))


def elegir_audio(proyecto):
    default_dir = Path(_dir_proyecto(proyecto))
    pendientes = tareas.audios_pendientes(default_dir, limite=10)
    if pendientes:
        opciones = []
        for w, dur in pendientes:
            titulo = str(w.relative_to(default_dir))
            if dur:
                titulo += (f" · {tareas.formato_min(dur)} · ~{tareas.formato_min(dur * tareas.FACTOR_PROCESO)}"
                           " en local, minutos en la nube")
            opciones.append(questionary.Choice(titulo, value=str(w)))
        opciones.append(OTRA_RUTA)
        eleccion = questionary.select("Archivo de audio (sin transcribir todavía):", choices=opciones).ask()
        if eleccion is None:
            return None
        if eleccion != OTRA_RUTA:
            # No se toca ultimo_dir: si el audio estaba en una subcarpeta, recordarla
            # haría que la próxima búsqueda dejara fuera el resto del proyecto.
            return Path(eleccion)

    ruta = questionary.path("Archivo de audio:", default=str(default_dir) + os.sep).ask()
    if not ruta:
        return None
    ruta = Path(ruta).expanduser()
    config.actualizar_estado(**{f"ultimo_dir_{proyecto}": str(ruta.parent)})
    return ruta


def elegir_motor_idioma():
    """Devuelve (motor, modelo, idioma) o None."""
    motor = questionary.select(
        "¿Dónde transcribir?",
        choices=[
            questionary.Choice("En la nube (AssemblyAI): unos minutos, ~0,23 $ por hora de audio", value="nube"),
            questionary.Choice("Local: gratis y el audio no sale del PC, pero ~1 h 15 por hora de audio", value="local"),
        ],
        default="nube",
    ).ask()
    if motor is None:
        return None
    if motor == "local" and not local_disponible():
        console.print("[red]El modo local no está instalado[/red] (falta el extra 'local': faster-whisper y pyannote).")
        return None
    idioma = questionary.select(
        "Idioma:",
        choices=[
            questionary.Choice("auto (detectar solo; una reunión con gallego suele salir en castellano)", value="auto"),
            "es",
            questionary.Choice("gl (respeta la mezcla gallego/castellano; en la nube puede juntar hablantes)", value="gl"),
            "en",
            "otro...",
        ],
        default="auto",
    ).ask()
    if idioma == "otro...":
        idioma = questionary.text("Código de idioma (ej. fr, de):").ask()
    if not idioma:
        return None
    modelo = "medium"
    if motor == "local":
        modelo = questionary.select(
            "Modelo:",
            choices=[
                "medium",
                questionary.Choice("turbo (~25% más rápido, pero a veces se salta frases; se descarga la 1ª vez)",
                                   value="turbo"),
                questionary.Choice("large (se descarga la 1ª vez, ~3 GB)", value="large"),
                "small", "base", "tiny",
            ],
            default="medium",
        ).ask()
        if modelo is None:
            return None
    return motor, modelo, idioma


def _falta_clave(motor):
    from .transcribir import clave_que_falta
    if not (clave := clave_que_falta(motor)):
        return False
    console.print(f"[red]Falta {clave}.[/red] Ponla en {config.dir_datos() / 'secretos.env'} "
                  f"(una línea {clave}=...) y vuelve a intentarlo.")
    return True


# ── Grabar y transcribir ─────────────────────────────────────────────────────

def _barra(nivel):
    # RMS de voz suele andar por 0,01-0,1: escala logarítmica para que se vea
    import math
    llenas = 0 if nivel <= 0 else max(0, min(20, int((math.log10(nivel) + 4) * 5)))
    return "█" * llenas + "·" * (20 - llenas)


def accion_grabar():
    proyecto = elegir_proyecto()
    if not proyecto:
        return
    directorio = questionary.path(
        "¿Dónde guardar la grabación?", default=_dir_proyecto(proyecto) + "/", only_directories=True
    ).ask()
    if not directorio:
        return
    directorio = Path(directorio).expanduser()
    directorio.mkdir(parents=True, exist_ok=True)
    config.actualizar_estado(**{f"ultimo_dir_{proyecto}": str(directorio)})

    descripcion = questionary.text("Descripción de la reunión (ej. seguimiento_semanal):").ask()
    if descripcion is None:
        return
    audio = directorio / f"{grabar.nombre_por_defecto(descripcion or 'reunion')}.wav"

    try:
        g, aviso = grabar.desde_preferencias(audio)
    except Exception as e:
        console.print(f"[red]No se puede grabar: {e}[/red]")
        return
    if aviso:
        console.print(f"[yellow]{escape(aviso)}[/yellow]")
    console.print("[dim]Avisa a los demás de que grabas la reunión.[/dim]")
    console.print(f"[bold]Grabando[/bold] {audio.name}\n  Lo que suena: {g.loop.name}\n  Micrófono:    {g.mic.name}")
    g.empezar()
    try:
        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while True:
                s = int(g.segundos)
                texto = (f"[bold red]●[/bold red] {s // 60}:{s % 60:02d}   "
                         f"sistema {_barra(g.niveles['sistema'])}   micro {_barra(g.niveles['micro'])}"
                         "   [dim]Ctrl+C para parar[/dim]")
                for aviso in g.avisos + g.errores:
                    texto += f"\n[yellow]{escape(aviso)}[/yellow]"
                live.update(texto)
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    g.parar()
    console.print(f"[green]Grabado:[/green] {audio} ({tareas.formato_min(g.segundos)})")

    if not questionary.confirm("¿Transcribir e identificar ahora?", default=False).ask():
        console.print("[dim]Puedes transcribirlo luego con \"Transcribir + identificar\".[/dim]")
        return
    _transcribir(proyecto, audio)


def accion_transcribir():
    proyecto = elegir_proyecto()
    if not proyecto:
        return
    audio = elegir_audio(proyecto)
    if not audio or not audio.exists():
        console.print("[red]Archivo no encontrado.[/red]")
        return
    _transcribir(proyecto, audio)


def _transcribir(proyecto, audio):
    eleccion = elegir_motor_idioma()
    if eleccion is None:
        return
    motor, modelo, idioma = eleccion
    if _falta_clave(motor):
        return
    en_bg = questionary.select(
        "¿Cómo transcribir?",
        choices=[
            questionary.Choice("Primer plano (esperar aquí a que termine)", value=False),
            questionary.Choice("Segundo plano (misma calidad; puedes grabar otra reunión mientras tanto)", value=True),
        ],
    ).ask()
    if en_bg is None:
        return
    if en_bg:
        tareas.lanzar(audio, proyecto, motor, modelo, idioma)
        console.print("[dim]Transcribiendo en segundo plano. El progreso se ve arriba del menú principal.\n"
                      "Cuando termine, revísalo en \"Revisar hablantes\".[/dim]")
        return

    from . import transcribir
    try:
        transcribir.transcribir(audio, motor=motor, modelo=modelo, idioma=idioma, diarizar=True, proyecto=proyecto)
    except KeyboardInterrupt:
        console.print("[yellow]Transcripción cancelada.[/yellow]")
        return
    except Exception as e:
        console.print(f"[red]Error: {escape(str(e))}[/red]")
        return
    sidecar = audio.with_suffix(revisar.SUFIJO)
    if sidecar.exists():
        mostrar_clusters(sidecar)
        if questionary.confirm("¿Revisar los hablantes ahora?", default=False).ask():
            revisar_sidecar(sidecar, proyecto)


def mostrar_en_curso():
    """Imprime las transcripciones en segundo plano; devuelve cuántas siguen."""
    n = 0
    for t, est, texto in tareas.revisar_en_curso():
        nombre = Path(t["audio"]).stem
        if est == "en_curso":
            console.print(f"[cyan]En curso:[/cyan] {nombre} · {texto}")
            n += 1
        elif est == "terminada":
            console.print(f"[green]Terminada:[/green] {nombre} ({texto})")
        else:
            console.print(f"[red]Falló:[/red] {nombre} · {texto}")
    return n


# ── Revisar hablantes ────────────────────────────────────────────────────────

def mostrar_clusters(sidecar):
    data = revisar.leer(sidecar)
    tabla = Table(title=f"Hablantes: {Path(sidecar).name}")
    for col in ("Cluster", "Nombre asignado", "Similitud", "Duración hablada"):
        tabla.add_column(col)
    for spk, info in data["clusters"].items():
        sim = info["similitud"]
        estilo = "yellow" if info["nombre"].startswith("Hablante ") else "green"
        tabla.add_row(spk, f"[{estilo}]{escape(info['nombre'])}[/{estilo}]",
                      f"{sim:.2f}" if sim is not None else "-", f"{info['duracion_hablada']:.0f}s")
    console.print(tabla)


def reproducir_muestra(origen):
    if not origen:
        console.print("[yellow]Esta muestra no tiene audio de origen guardado.[/yellow]")
        return
    ruta = Path(origen["audio"])
    if not ruta.exists():
        console.print(f"[yellow]No se encuentra el audio original: {ruta}[/yellow]")
        return
    console.print(f"[dim]▶ {ruta.name} [{origen['inicio']:.1f}s-{origen['fin']:.1f}s] (Ctrl+C para cortar)[/dim]")
    try:
        audio_util.reproducir(ruta, origen["inicio"], origen["fin"])
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"[yellow]No se pudo reproducir: {escape(str(e))}[/yellow]")


def _pedir_nombre(pregunta, conocidos):
    if conocidos:
        return questionary.autocomplete(pregunta, choices=conocidos).ask()
    return questionary.text(pregunta).ask()


def revisar_sidecar(sidecar, proyecto):
    """Revisa los hablantes uno a uno; cada decisión se guarda al momento, así
    que Esc para sin perder nada y la próxima vez retoma donde se quedó."""
    data = revisar.leer(sidecar)
    frases = revisar.frases_por_cluster(sidecar)
    ya = sum(1 for c in data["clusters"].values() if c.get("revisado"))
    if ya:
        console.print(f"[dim]Retomando: {ya} hablante(s) ya revisados la otra vez.[/dim]")

    cambios = 0
    completa = data.get("revisado", False)
    for spk, info in data["clusters"].items():
        if info.get("revisado"):
            continue
        actual = info["nombre"]
        console.print(f"\n[bold]{spk}[/bold] ({escape(actual)}) dijo, entre otras cosas:")
        for frase in frases.get(spk) or ["(no hay frases largas suyas en la transcripción)"]:
            console.print(f"  [dim]«{escape(frase)}»[/dim]")

        nuevo = None
        while nuevo is None:
            eleccion = questionary.select(
                f"{spk} ({info['duracion_hablada']:.0f}s hablados) → asignado como '{actual}'",
                choices=[
                    questionary.Choice("Reproducir", value="play"),
                    questionary.Choice("Confirmar (y reforzar la muestra)", value="ok"),
                    questionary.Choice("Corregir nombre", value="corregir"),
                    questionary.Choice("Saltar (no lo identifico; no se guarda nada en la librería)", value="saltar"),
                ],
            ).ask()
            if eleccion is None:
                faltan = sum(1 for c in revisar.leer(sidecar)["clusters"].values() if not c.get("revisado"))
                console.print(f"[yellow]Revisión parada. Faltan {faltan} hablante(s); "
                              f"sigue pendiente en \"Revisar hablantes\".[/yellow]")
                return
            if eleccion == "play":
                reproducir_muestra(info.get("origen"))
            elif eleccion == "saltar":
                nuevo = ""
            elif eleccion == "ok":
                nuevo = actual
            else:
                # Esc o nombre vacío: volver al menú de este mismo hablante
                nuevo = _pedir_nombre("Nombre correcto:", revisar.nombres_conocidos(sidecar, proyecto)) or None

        r = revisar.decidir(sidecar, spk, nuevo, proyecto)
        completa = r["completa"]
        if nuevo:
            cambios += 1
            if r["anadida"]:
                console.print(f"  [green]✓[/green] {escape(nuevo)}: {r['muestras']} muestras en {proyecto}")
            else:
                console.print(f"  [dim]{escape(nuevo)} ya tenía una muestra casi idéntica: no se añade otra "
                              f"({r['muestras']} muestras)[/dim]")
            if r["renombradas"]:
                console.print(f"  [dim]Renombrado en la transcripción ({r['renombradas']} apariciones)[/dim]")

    console.print(f"[bold green]Revisión completa: {cambios} hablante(s) confirmados o corregidos.[/bold green]")
    if completa:
        console.print("\nComprimiendo el audio a Opus para archivarlo (no cierres todavía)...")
        try:
            if hecho := revisar.archivar_si_completa(sidecar):
                console.print(f"[dim]Audio archivado como {hecho[0].name} ({hecho[1] / 1e6:.0f} MB menos).[/dim]")
        except Exception as e:  # el WAV se queda tal cual si algo falla
            console.print(f"[yellow]No se pudo comprimir: {escape(str(e))}[/yellow]")


def revisar_hablantes(solo_proyecto=None):
    pendientes = revisar.pendientes(solo_proyecto)
    if not pendientes:
        console.print("[green]No hay transcripciones pendientes de revisar.[/green]")
        return
    opciones = []
    for proyecto, s in pendientes[:15]:
        titulo = s.name.removesuffix(revisar.SUFIJO) + ("" if solo_proyecto else f" · {proyecto}")
        opciones.append(questionary.Choice(titulo, value=(proyecto, s)))
    eleccion = questionary.select("¿Qué transcripción revisar?", choices=opciones).ask()
    if not eleccion:
        return
    proyecto, sidecar = eleccion
    mostrar_clusters(sidecar)
    revisar_sidecar(sidecar, proyecto)


# ── Personas (librería de voces) ─────────────────────────────────────────────

def _etiqueta_muestra(muestra):
    origen = muestra.get("origen")
    if origen:
        dur = origen["fin"] - origen["inicio"]
        return f"{dur:.0f}s de {Path(origen['audio']).name} [{origen['inicio']:.0f}s-{origen['fin']:.0f}s]"
    return "sin origen guardado (no se puede reproducir)"


def _buscar_muestra(proyecto, nombre, id_muestra):
    datos = voiceprints.cargar_libreria_con_origen(proyecto)
    return next((m for m in datos.get(nombre, []) if m["id"] == id_muestra), None)


def _reclasificar(proyecto, nombre, id_muestra):
    nuevo = _pedir_nombre(f"{nombre}: ¿a qué persona pertenece de verdad? (nombre nuevo si no está en la lista)",
                          sorted(voiceprints.cargar_libreria(proyecto).keys()))
    if not nuevo or nuevo == nombre:
        return False
    voiceprints.reclasificar_muestra(proyecto, nombre, id_muestra, nuevo)
    console.print(f"[green]✓[/green] Movida a {escape(nuevo)}")
    return True


def _gestionar_muestra(proyecto, nombre, id_muestra):
    while True:
        muestra = _buscar_muestra(proyecto, nombre, id_muestra)
        if muestra is None:
            console.print("[dim]Esa muestra ya no existe (se borró o se movió).[/dim]")
            return
        accion = questionary.select(
            f"{nombre}: {_etiqueta_muestra(muestra)}",
            choices=["Reproducir", "Reclasificar a otra persona", "Borrar esta muestra", "Volver"],
        ).ask()
        if accion is None or accion == "Volver":
            return
        if accion == "Reproducir":
            reproducir_muestra(muestra.get("origen"))
        elif accion == "Borrar esta muestra":
            voiceprints.eliminar_muestra(proyecto, nombre, id_muestra)
            console.print("[green]✓[/green] Muestra eliminada")
            return
        elif _reclasificar(proyecto, nombre, id_muestra):
            return


def _personas_ver_resumen(proyecto):
    datos = voiceprints.cargar_libreria_con_origen(proyecto)
    if not datos:
        console.print(f"[yellow]El proyecto {proyecto} aún no tiene voces guardadas.[/yellow]")
        return
    tabla = Table(title=f"Proyecto: {proyecto}")
    for col in ("Persona", "Muestras", "Con audio reproducible"):
        tabla.add_column(col)
    for nombre, muestras in sorted(datos.items()):
        con_audio = sum(1 for m in muestras if m.get("origen"))
        tabla.add_row(escape(nombre), str(len(muestras)), f"{con_audio}/{len(muestras)}")
    console.print(tabla)


def _personas_explorar(proyecto):
    while True:
        datos = voiceprints.cargar_libreria_con_origen(proyecto)
        if not datos:
            console.print(f"[yellow]El proyecto {proyecto} aún no tiene voces guardadas.[/yellow]")
            return
        opciones = [questionary.Choice(f"{n} ({len(m)} muestras)", value=n) for n, m in sorted(datos.items())]
        nombre = questionary.select("Persona:", choices=opciones + ["Volver"]).ask()
        if nombre is None or nombre == "Volver":
            return
        while True:
            muestras = voiceprints.cargar_libreria_con_origen(proyecto).get(nombre, [])
            if not muestras:
                console.print(f"[dim]{escape(nombre)} ya no tiene muestras.[/dim]")
                break
            opciones_m = [questionary.Choice(_etiqueta_muestra(m), value=m["id"]) for m in muestras]
            id_muestra = questionary.select(f"{nombre}: elige una muestra:", choices=opciones_m + ["Volver"]).ask()
            if id_muestra is None or id_muestra == "Volver":
                break
            _gestionar_muestra(proyecto, nombre, id_muestra)


def _personas_borrar_entera(proyecto):
    datos = voiceprints.cargar_libreria(proyecto)
    if not datos:
        console.print(f"[yellow]El proyecto {proyecto} aún no tiene voces guardadas.[/yellow]")
        return
    eleccion = questionary.select("¿Borrar a quién?", choices=sorted(datos.keys()) + ["Cancelar"]).ask()
    if not eleccion or eleccion == "Cancelar":
        return
    n = len(datos[eleccion])
    if questionary.confirm(f"¿Seguro que quieres borrar a {eleccion} y sus {n} muestras?", default=False).ask():
        voiceprints.eliminar_persona(proyecto, eleccion)
        console.print(f"[green]✓[/green] {escape(eleccion)} eliminado del proyecto {proyecto}")


def _personas_restaurar_backup(proyecto):
    if not Path(voiceprints.ruta_libreria(proyecto) + ".bak").exists():
        console.print("[yellow]No hay backup disponible (todavía no se ha borrado/reclasificado nada).[/yellow]")
        return
    if questionary.confirm(
        "Esto deshace el último borrado o reclasificación (un solo paso atrás). ¿Restaurar?", default=False
    ).ask():
        voiceprints.restaurar_backup(proyecto)
        console.print(f"[green]✓[/green] Proyecto {proyecto} restaurado al estado anterior al último cambio.")


def _personas_enrolar_manual(proyecto):
    audio = elegir_audio(proyecto)
    if not audio or not audio.exists():
        console.print("[red]Archivo no encontrado.[/red]")
        return
    inicio = questionary.text("Inicio (segundos):").ask()
    fin = questionary.text("Fin (segundos):").ask()
    nombre = questionary.text("Nombre de la persona:").ask()
    if not (inicio and fin and nombre):
        return
    n, anadida = revisar.enrolar(audio, float(inicio), float(fin), nombre, proyecto)
    if anadida:
        console.print(f"[green]✓[/green] {escape(nombre)}: {n} muestras en {proyecto}")
    else:
        console.print(f"[dim]{escape(nombre)} ya tenía una muestra casi idéntica: no se añade otra ({n} muestras)[/dim]")


def _personas_reparar():
    from . import rutas

    r = rutas.reparar()
    for viejo, nuevo, refs in r["arregladas"]:
        console.print(f"[green]✓[/green] {escape(Path(viejo).name)} → {escape(str(Path(nuevo).parent))} ({refs})")
    for viejo, _ in r["dudosas"]:
        console.print(f"[yellow]Varios candidatos para {escape(viejo)}: no se toca[/yellow]")
    for viejo in r["sin_encontrar"]:
        console.print(f"[yellow]No encontrado: {escape(viejo)}[/yellow]")
    if not any(r.values()):
        console.print("[green]Todas las muestras apuntan a audios que existen.[/green]")


def _personas_auditar(proyecto):
    """Un único menú plano por hallazgo: "Siguiente" es la opción por defecto,
    así que si todo está bien basta con pulsar Enter. Recalcula tras cada
    acción, así que un hallazgo arreglado desaparece solo de la lista.
    "Siguiente" solo lo salta en esta sesión; "Marcar como correcto" lo guarda
    para no volver a avisar nunca."""
    vistos = set()

    def clave(p):
        return (p["tipo"], p["id_a"], p["id_b"])

    while True:
        pendientes = [p for p in voiceprints.auditar_libreria(proyecto) if clave(p) not in vistos]
        if not pendientes:
            if vistos:
                console.print(f"[bold green]No quedan hallazgos por revisar[/bold green] ({len(vistos)} saltados "
                              "esta sesión; volverán a aparecer si no se arreglan).")
            else:
                console.print(f"[green]Sin hallazgos pendientes en el proyecto {proyecto}[/green]")
            return

        p = max(pendientes, key=lambda p: p["similitud"] if p["tipo"] in ("confusion", "duplicado") else -p["similitud"])
        a, b = escape(p["nombre_a"]), escape(p["nombre_b"])
        console.print(f"[dim]{len(pendientes)} hallazgo(s) pendientes[/dim]")
        if p["tipo"] == "confusion":
            color = "red" if p["similitud"] >= voiceprints.UMBRAL_DEFECTO else "yellow"
            console.print(f"[{color}]Posible confusión[/{color}]: {a} / {b} (similitud {p['similitud']:.2f})")
        elif p["tipo"] == "duplicado":
            console.print(f"[cyan]Muestras casi duplicadas[/cyan]: {a} (similitud {p['similitud']:.2f}); "
                          "probablemente puedes borrar una")
        else:
            console.print(f"[yellow]Muestras dispersas[/yellow]: {a} (similitud {p['similitud']:.2f})")

        lados = {"A": (p["nombre_a"], p["id_a"]), "B": (p["nombre_b"], p["id_b"])}
        opciones = [questionary.Choice("Siguiente (sin cambios)", value=("siguiente", None))]
        for verbo in ("Reproducir", "Borrar", "Reclasificar"):
            for lado, (nombre, _) in lados.items():
                opciones.append(questionary.Choice(f"{verbo} {lado} ({nombre})", value=(verbo, lado)))
        opciones += [questionary.Choice("Marcar como correcto (no volver a avisar)", value=("correcto", None)),
                     questionary.Choice("Salir de la auditoría", value=("salir", None))]
        accion = questionary.select("¿Qué hacemos?", choices=opciones, default=opciones[0]).ask()

        if accion is None or accion[0] == "salir":
            return
        verbo, lado = accion
        if verbo == "siguiente":
            vistos.add(clave(p))
        elif verbo == "correcto":
            voiceprints.marcar_como_correcto(proyecto, p["tipo"], p["id_a"], p["id_b"])
            console.print("[green]✓[/green] Marcado como correcto, no volverá a aparecer.")
        else:
            nombre, id_muestra = lados[lado]
            if verbo == "Reproducir":
                m = _buscar_muestra(proyecto, nombre, id_muestra)
                reproducir_muestra(m.get("origen") if m else None)
            elif verbo == "Borrar":
                voiceprints.eliminar_muestra(proyecto, nombre, id_muestra)
                console.print(f"[green]✓[/green] Muestra de {escape(nombre)} eliminada.")
            else:
                _reclasificar(proyecto, nombre, id_muestra)
        console.print()


def menu_personas():
    proyecto = elegir_proyecto()
    if not proyecto:
        return
    acciones = {
        "Ver resumen": lambda: _personas_ver_resumen(proyecto),
        "Auditar y corregir": lambda: _personas_auditar(proyecto),
        "Corregir hablantes (transcripción reciente)": lambda: revisar_hablantes(solo_proyecto=proyecto),
        "Explorar por persona (reproducir / reclasificar / borrar)": lambda: _personas_explorar(proyecto),
        "Añadir muestra manual": lambda: _personas_enrolar_manual(proyecto),
        "Borrar persona entera": lambda: _personas_borrar_entera(proyecto),
        "Restaurar backup (deshacer último borrado/cambio)": lambda: _personas_restaurar_backup(proyecto),
        "Reparar rutas (audios movidos de carpeta)": _personas_reparar,
    }
    while True:
        n = len(voiceprints.auditar_libreria(proyecto))
        aviso = f" ({n} hallazgo(s) de auditoría pendientes)" if n else ""
        eleccion = questionary.select(f"Personas, proyecto '{proyecto}'{aviso}:",
                                      choices=list(acciones) + ["Volver al menú principal"]).ask()
        if eleccion is None or eleccion == "Volver al menú principal":
            return
        acciones[eleccion]()
        console.print()


# ── Menú principal ───────────────────────────────────────────────────────────

def main():
    console.print("[bold cyan]Escriba[/bold cyan]: grabación, transcripción e identificación de reuniones\n")
    while True:
        n_en_curso = mostrar_en_curso()
        n_pendientes = len(revisar.pendientes())
        revisar_txt = "Revisar hablantes" + (f" ({n_pendientes} pendientes)" if n_pendientes else " (nada pendiente)")
        opciones = {
            "Grabar reunión": accion_grabar,
            "Transcribir + identificar": accion_transcribir,
            revisar_txt: revisar_hablantes,
            "Personas": menu_personas,
        }
        if n_en_curso:
            opciones["Actualizar progreso"] = lambda: None  # el bucle vuelve a pintar el progreso
        eleccion = questionary.select("¿Qué quieres hacer?", choices=list(opciones) + ["Salir"]).ask()
        if eleccion is None or eleccion == "Salir":
            break
        opciones[eleccion]()
        console.print()
