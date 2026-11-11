"""Línea de comandos de escriba. Sin argumentos abre el menú interactivo.

  escriba                      menú interactivo
  escriba web                  interfaz en el navegador
  escriba grabar [NOMBRE]      grabar una reunión (Ctrl+C para parar)
  escriba transcribir AUDIO    transcribir (e identificar hablantes)
  escriba archivar [DIR ...]   comprimir a Opus lo ya revisado
  escriba enrolar AUDIO INI FIN NOMBRE PROYECTO
  escriba reparar [DIR ...]    arreglar muestras de audios movidos de carpeta
  escriba datos                dónde están tus datos y claves

Cada orden tiene su propia ayuda: escriba <orden> --help
"""
import argparse
import sys
import time
import warnings
from pathlib import Path

from . import config


def _utf8():
    # En Windows, con la salida redirigida a un archivo, Python usaría cp1252
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_grabar(a):
    from . import grabar

    if a.listar:
        disp = grabar.listar_dispositivos()
        print("Salidas (lo que suena; usa con --altavoz):")
        for nombre, defecto in disp["altavoces"]:
            print(f"  {nombre}{' (por defecto)' if defecto else ''}")
        print("\nMicrófonos (usa con --micro):")
        for nombre, defecto in disp["micros"]:
            print(f"  {nombre}{' (por defecto)' if defecto else ''}")
        return
    destino = Path(a.dir).expanduser() / f"{a.nombre or grabar.nombre_por_defecto()}.wav"
    g = grabar.Grabacion(destino, altavoz=a.altavoz, micro=a.micro)
    print(f"Grabando en: {destino}\n  Lo que suena: {g.loop.name}\n  Micrófono:    {g.mic.name}\nCtrl+C para parar.")
    g.empezar()
    try:
        while True:
            time.sleep(1)
            print(f"\r{int(g.segundos) // 60}:{int(g.segundos) % 60:02d}  " + "  ".join(g.avisos), end="", flush=True)
    except KeyboardInterrupt:
        pass
    g.parar()
    print(f"\nGuardado: {destino}")
    if a.transcribir:
        from . import transcribir
        transcribir.transcribir(destino, motor="local" if a.local else "nube", diarizar=bool(a.proyecto),
                                proyecto=a.proyecto or "")


def cmd_transcribir(a):
    from . import transcribir

    hablantes = [h.strip() for h in a.hablantes.split(",") if h.strip()]
    diarizar = a.diarizar or bool(a.proyecto) or bool(hablantes)
    try:
        transcribir.transcribir(a.audio, motor="local" if a.local else "nube", modelo=a.modelo, idioma=a.idioma,
                                diarizar=diarizar, proyecto=a.proyecto, hablantes=hablantes, prompt=a.prompt)
    except Exception as e:
        sys.exit(f"Error: {e}")


def cmd_archivar(a):
    from . import archivar

    dirs = [Path(d).expanduser() for d in a.dirs] or archivar.directorios_del_estado()
    archivar.archivar_directorios(dirs, simular=a.simular)


def cmd_enrolar(a):
    from . import revisar

    n, anadida = revisar.enrolar(a.audio, a.inicio, a.fin, a.nombre, a.proyecto)
    if anadida:
        print(f"Añadida muestra de {a.nombre} al proyecto {a.proyecto} ({n} muestras en total)")
    else:
        print(f"Ya había una muestra casi idéntica de {a.nombre}: no se añade otra ({n} muestras en total)")


def cmd_web(a):
    import socket
    import webbrowser

    url = f"http://127.0.0.1:{a.puerto}"
    with socket.socket() as s:
        ya_abierta = s.connect_ex(("127.0.0.1", a.puerto)) == 0
    if ya_abierta:
        # Segundo clic en el acceso directo: escriba ya está en marcha
        print(f"Escriba ya está abierta en {url}")
        if not a.no_abrir:
            webbrowser.open(url)
        return

    from . import web

    print(f"Escriba en {url}\nDeja esta ventana abierta mientras la uses; al cerrarla se cierra Escriba "
          "(y se para lo que esté grabando).")
    web.arrancar(puerto=a.puerto, abrir=not a.no_abrir)


def cmd_reparar(a):
    from . import rutas

    r = rutas.reparar(extra=a.dirs, simular=a.simular)
    verbo = "se arreglaría" if a.simular else "arreglado"
    for viejo, nuevo, refs in r["arregladas"]:
        print(f"  {verbo}: {viejo}\n        -> {nuevo} ({refs} referencias)")
    for viejo, candidatos in r["dudosas"]:
        print(f"  varios candidatos para {viejo}: " + ", ".join(candidatos))
    for viejo in r["sin_encontrar"]:
        print(f"  no encontrado: {viejo}")
    if not any(r.values()):
        print("Todas las muestras apuntan a audios que existen.")


def cmd_datos(a):
    print(f"Carpeta de datos: {config.dir_datos()}")
    print(f"  Voces:    {config.dir_voiceprints()}")
    print(f"  Glosario: {config.ruta_glosario()}")
    for clave in ("ASSEMBLYAI_API_KEY", "HF_TOKEN"):
        print(f"  {clave}: {'configurada' if config.leer_secreto(clave) else 'falta'}")


def parser():
    p = argparse.ArgumentParser(prog="escriba", description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="orden", metavar="orden")

    g = sub.add_parser("grabar", help="grabar una reunión",
                       description="Graba lo que suena en el PC + tu micrófono, mezclado, a un WAV mono de 16 kHz.")
    g.add_argument("nombre", nargs="?", help="nombre del archivo, sin .wav (por defecto: fecha_reunion_HHMM)")
    g.add_argument("--dir", default=".", help="carpeta donde guardar (por defecto, la actual)")
    g.add_argument("--listar", action="store_true", help="lista salidas y micrófonos y sale")
    g.add_argument("--altavoz", help="salida cuyo sonido grabar (por defecto, la del sistema)")
    g.add_argument("--micro", help="micrófono (por defecto, el del sistema)")
    g.add_argument("--transcribir", action="store_true", help="transcribir al terminar")
    g.add_argument("--local", action="store_true", help="con --transcribir: en local en vez de en la nube")
    g.add_argument("--proyecto", help="con --transcribir: identificar hablantes por voz con este proyecto")
    g.set_defaults(func=cmd_grabar)

    t = sub.add_parser("transcribir", help="transcribir un audio",
                       description="Transcribe un audio y deja el .txt (y el .speakers.json si se identifican "
                                   "hablantes) junto a él.")
    t.add_argument("audio")
    motor = t.add_mutually_exclusive_group()
    motor.add_argument("--nube", action="store_true",
                       help="AssemblyAI (por defecto): unos minutos, ~0,23 $/hora; necesita ASSEMBLYAI_API_KEY")
    motor.add_argument("--local", action="store_true",
                       help="faster-whisper + pyannote en este PC: gratis pero lento; necesita el extra 'local'")
    t.add_argument("--modelo", default="medium", help="solo local: tiny/base/small/medium/large/turbo (medium)")
    t.add_argument("--idioma", default="auto", help="es, gl, en... (por defecto auto)")
    t.add_argument("--diarizar", action="store_true", help="separar hablantes (implícito con --proyecto)")
    t.add_argument("--proyecto", default="", help="identificar hablantes por voz con la librería de este proyecto")
    t.add_argument("--hablantes", default="", help='"A,B": nombres en orden de aparición para quien no se reconozca')
    t.add_argument("--prompt", default=None, help="solo local: prompt inicial (por defecto, el glosario)")
    t.set_defaults(func=cmd_transcribir)

    ar = sub.add_parser("archivar", help="comprimir a Opus lo ya revisado",
                        description="Pasa a Opus los WAV ya transcritos y revisados y actualiza las referencias.")
    ar.add_argument("dirs", nargs="*", help="carpetas (por defecto, las últimas de cada proyecto)")
    ar.add_argument("--simular", action="store_true", help="solo lista lo que haría")
    ar.set_defaults(func=cmd_archivar)

    e = sub.add_parser("enrolar", help="añadir a mano una muestra de voz",
                       description="Añade el fragmento INICIO-FIN (segundos) de un audio como muestra de voz.")
    e.add_argument("audio")
    e.add_argument("inicio", type=float)
    e.add_argument("fin", type=float)
    e.add_argument("nombre")
    e.add_argument("proyecto")
    e.set_defaults(func=cmd_enrolar)

    w = sub.add_parser("web", help="interfaz en el navegador",
                       description="Abre escriba en el navegador. Solo se puede entrar desde este PC.")
    w.add_argument("--puerto", type=int, default=8765, help="puerto local (por defecto 8765)")
    w.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    w.set_defaults(func=cmd_web)

    r = sub.add_parser("reparar", help="arreglar muestras de audios movidos de carpeta",
                       description="Busca por nombre los audios que se movieron de carpeta (en las carpetas de "
                                   "los proyectos y en las que indiques) y actualiza las rutas de las muestras.")
    r.add_argument("dirs", nargs="*", help="carpetas donde buscar además de las de los proyectos")
    r.add_argument("--simular", action="store_true", help="solo dice lo que haría")
    r.set_defaults(func=cmd_reparar)

    d = sub.add_parser("datos", help="dónde están tus datos y qué claves hay")
    d.set_defaults(func=cmd_datos)
    return p


def main(argv=None):
    _utf8()
    # Ruido de pyannote/webrtcvad (pkg_resources obsoleto, etc.) que ensucia los logs
    warnings.filterwarnings("ignore", category=UserWarning)
    args = parser().parse_args(argv)
    if not args.orden:
        from . import menu
        return menu.main()
    return args.func(args)
