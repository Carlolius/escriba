"""Reparar rutas: muestras de voz que apuntan a un audio que ya no está ahí.

Pasa al mover reuniones de carpeta o al renombrar carpetas. La identificación
por voz sigue funcionando (la huella está en la librería), pero esas muestras
ya no se pueden escuchar. Se buscan los audios por nombre de archivo en las
carpetas de los proyectos (y las que se indiquen) y, si hay un único
candidato, se actualizan las rutas en las librerías, sus .bak y los sidecars.
"""
import json
from pathlib import Path

from . import archivar, config

EXTENSIONES = (".wav", ".opus", ".flac", ".ogg")


def _origenes(muestras):
    for m in muestras:
        origen = m.get("origen") if isinstance(m, dict) else None
        if origen and origen.get("audio"):
            yield origen["audio"]


def _carpetas(extra=()):
    vistas, carpetas = set(), []
    for d in [*archivar.directorios_del_estado(), *map(Path, extra)]:
        d = Path(d).expanduser()
        if d.is_dir() and d.resolve() not in vistas:
            vistas.add(d.resolve())
            carpetas.append(d)
    return carpetas


def rutas_rotas(extra=()):
    """{ruta que no existe: nº de referencias} en librerías y sidecars."""
    rotas = {}

    def apuntar(ruta):
        if not Path(ruta).exists():
            rotas[ruta] = rotas.get(ruta, 0) + 1

    for lib in config.dir_voiceprints().glob("*.json*"):
        if ".audit_confirmados" in lib.name:
            continue
        try:
            datos = json.loads(lib.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for muestras in datos.values():
            if isinstance(muestras, list):
                for ruta in _origenes(muestras):
                    apuntar(ruta)
    for carpeta in _carpetas(extra):
        for sidecar in carpeta.rglob("*.speakers.json"):
            try:
                clusters = json.loads(sidecar.read_text(encoding="utf-8")).get("clusters", {})
            except (OSError, json.JSONDecodeError):
                continue
            for ruta in _origenes(clusters.values()):
                apuntar(ruta)
    return rotas


def reparar(extra=(), simular=False):
    """Devuelve {"arregladas": [(viejo, nuevo, refs)], "sin_encontrar": [viejo],
    "dudosas": [(viejo, [candidatos])]}."""
    rotas = rutas_rotas(extra)
    resultado = {"arregladas": [], "sin_encontrar": [], "dudosas": []}
    if not rotas:
        return resultado

    por_nombre = {}
    for carpeta in _carpetas(extra):
        for p in carpeta.rglob("*"):
            if p.suffix.lower() in EXTENSIONES and p.is_file():
                por_nombre.setdefault(p.name, set()).add(p.resolve())

    for viejo in sorted(rotas):
        v = Path(viejo)
        candidatos = por_nombre.get(v.name, set())
        if not candidatos and v.suffix.lower() == ".wav":
            # Se archivó a Opus después de moverlo
            candidatos = por_nombre.get(v.with_suffix(".opus").name, set())
        if len(candidatos) == 1:
            nuevo = next(iter(candidatos))
            refs = rotas[viejo] if simular else archivar.actualizar_rutas(v, nuevo)
            resultado["arregladas"].append((viejo, str(nuevo), refs))
        elif candidatos:
            resultado["dudosas"].append((viejo, sorted(map(str, candidatos))))
        else:
            resultado["sin_encontrar"].append(viejo)
    return resultado
