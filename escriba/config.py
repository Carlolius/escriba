"""Dónde guarda escriba sus datos, y lectura de estado, secretos y glosario.

Todo lo que es del usuario (librerías de voces, estado del menú, glosario,
claves) vive en su carpeta de datos, no junto al programa:
  Linux:   ~/.local/share/escriba
  Windows: %LOCALAPPDATA%\\escriba
  macOS:   ~/Library/Application Support/escriba
La variable de entorno ESCRIBA_DATOS la cambia (útil para pruebas).

Las grabaciones y transcripciones no se mueven: se quedan en las carpetas de
cada proyecto que elija el usuario.
"""
import json
import os
from pathlib import Path

import platformdirs

APP = "escriba"


def dir_datos():
    ruta = os.environ.get("ESCRIBA_DATOS")
    ruta = Path(ruta).expanduser() if ruta else platformdirs.user_data_path(APP, appauthor=False)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def dir_voiceprints():
    ruta = dir_datos() / "voiceprints"
    ruta.mkdir(exist_ok=True)
    return ruta


def ruta_glosario():
    ruta = dir_datos() / "glosario.txt"
    if not ruta.exists():
        ruta.write_text(GLOSARIO_INICIAL, encoding="utf-8")
    return ruta


def _ruta_estado():
    return dir_datos() / "estado.json"


def _ruta_secretos():
    return dir_datos() / "secretos.env"


def escribir_json(ruta, datos, indent=2):
    """Escritura atómica: el menú, la web y las tareas en segundo plano pueden
    leer el mismo archivo mientras otro lo escribe."""
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, indent=indent, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ruta)


# ── Estado (últimos proyectos y carpetas, transcripciones en curso) ──────────

def cargar_estado():
    ruta = _ruta_estado()
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def guardar_estado(estado):
    escribir_json(_ruta_estado(), estado)


def actualizar_estado(**cambios):
    """Lee, cambia y guarda: nunca se guarda un estado viejo que pise las
    tareas que haya apuntado otra ventana entretanto."""
    estado = cargar_estado()
    estado.update(cambios)
    guardar_estado(estado)
    return estado


def listar_proyectos():
    return sorted(
        p.stem for p in dir_voiceprints().glob("*.json")
        if not p.stem.endswith(".audit_confirmados")
    )


def crear_proyecto(nombre):
    ruta = dir_voiceprints() / f"{nombre}.json"
    if not ruta.exists():
        ruta.write_text("{}", encoding="utf-8")


# ── Secretos (claves de AssemblyAI y Hugging Face) ───────────────────────────

def _leer_env(ruta):
    valores = {}
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    clave, valor = linea.split("=", 1)
                    valores[clave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        pass
    return valores


def leer_secreto(nombre):
    """Primero la variable de entorno; si no, secretos.env de la carpeta de datos."""
    return os.environ.get(nombre) or _leer_env(_ruta_secretos()).get(nombre)


def guardar_secreto(nombre, valor):
    """Guarda (o borra, con valor vacío) una clave en secretos.env, cambiando
    solo su línea: el resto del archivo (otras claves, comentarios) se respeta.
    secretos.env puede ser un enlace a un .env que ya uses para otras cosas."""
    ruta = _ruta_secretos()
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        lineas = []
    nuevas, puesta = [], False
    for linea in lineas:
        if linea.strip().split("=", 1)[0].strip() == nombre and "=" in linea and not linea.lstrip().startswith("#"):
            if valor and not puesta:
                nuevas.append(f"{nombre}={valor}")
                puesta = True
            continue
        nuevas.append(linea)
    if valor and not puesta:
        nuevas.append(f"{nombre}={valor}")
    destino = ruta.resolve()  # si es un enlace, se escribe en el archivo enlazado
    destino.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
    if os.name == "posix":
        destino.chmod(0o600)


# ── Glosario (nombres propios y términos para mejorar la transcripción) ──────

def leer_glosario():
    """Líneas del glosario sin comentarios ni vacías. Cada línea puede llevar
    varios términos separados por comas."""
    ruta = ruta_glosario()
    if not ruta.exists():
        return []
    return [
        l.strip() for l in ruta.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]


GLOSARIO_INICIAL = """\
# Glosario: nombres propios y términos que salen en tus reuniones.
# Ayuda a que la transcripción los escriba bien. Uno o varios por línea,
# separados por comas. Las líneas que empiezan por # se ignoran.
"""
