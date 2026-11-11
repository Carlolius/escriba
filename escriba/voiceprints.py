"""Identificación de hablantes por voiceprint (librería de voces por proyecto).

Cada persona puede tener varias muestras (embeddings de resemblyzer) enroladas en
distintas condiciones de grabación. La identificación usa la similitud máxima
entre el embedding del cluster y todas las muestras guardadas de cada persona.

Cada muestra se guarda como:
  {"id": "abc123...", "embedding": [...], "origen": {"audio", "inicio", "fin"} | None}

"id" es estable (no cambia si se borran o mueven otras muestras) y es lo que usan
eliminar_muestra/reclasificar_muestra para referirse a una muestra concreta.
Las muestras guardadas antes de este esquema (lista plana de floats, sin id ni
origen) se migran solas la primera vez que se leen.
"""
import json
import os
import shutil
import uuid

import numpy as np

from . import config

UMBRAL_DEFECTO = 0.87
UMBRAL_DUPLICADO = 0.93


def ruta_libreria(proyecto):
    return str(config.dir_voiceprints() / f"{proyecto}.json")


def _respaldar(ruta):
    """Copia de seguridad de un solo paso antes de una operación destructiva
    (borrar, reclasificar). Se sobreescribe cada vez — guarda el estado justo
    antes del último cambio, no un historial completo."""
    if os.path.exists(ruta):
        shutil.copy2(ruta, ruta + ".bak")


def restaurar_backup(proyecto):
    """Deshace el último borrado/reclasificación restaurando la copia .bak de la librería."""
    ruta = ruta_libreria(proyecto)
    backup = ruta + ".bak"
    if not os.path.exists(backup):
        return False
    shutil.copy2(backup, ruta)
    return True


def _normalizar_muestra(m):
    """Acepta el formato antiguo (lista de floats) o el nuevo (dict); devuelve
    siempre un dict con "id", "embedding" y "origen", generando lo que falte."""
    if isinstance(m, dict):
        cambiado = False
        if "id" not in m:
            m = {**m, "id": uuid.uuid4().hex[:10]}
            cambiado = True
        if "origen" not in m:
            m["origen"] = None
            cambiado = True
        return m, cambiado
    return {"id": uuid.uuid4().hex[:10], "embedding": m, "origen": None}, True


def _leer_y_migrar(ruta):
    """Devuelve (datos_normalizados, hubo_cambios)."""
    if not os.path.exists(ruta):
        return {}, False
    with open(ruta, encoding="utf-8") as f:
        crudo = json.load(f)
    datos = {}
    cambiado = False
    for nombre, muestras in crudo.items():
        normalizadas = []
        for m in muestras:
            nm, c = _normalizar_muestra(m)
            normalizadas.append(nm)
            cambiado = cambiado or c
        datos[nombre] = normalizadas
    return datos, cambiado


def _guardar(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _cargar_y_migrar_si_hace_falta(ruta):
    datos, cambiado = _leer_y_migrar(ruta)
    if cambiado:
        _guardar(ruta, datos)
    return datos


def cargar_libreria(proyecto):
    """Para cálculo de similitud: nombre -> lista de embeddings (np.array)."""
    datos = _cargar_y_migrar_si_hace_falta(ruta_libreria(proyecto))
    return {
        nombre: [np.array(m["embedding"], dtype="float32") for m in muestras]
        for nombre, muestras in datos.items()
    }


def cargar_libreria_con_origen(proyecto):
    """Para gestión/reproducción: nombre -> lista de {"id", "embedding", "origen"}."""
    return _cargar_y_migrar_si_hace_falta(ruta_libreria(proyecto))


def cos_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def identificar(embedding, libreria, umbral=UMBRAL_DEFECTO):
    """Devuelve (nombre, similitud) del mejor match, o (None, similitud) si no supera el umbral."""
    mejor_nombre, mejor_sim = None, 0.0
    for nombre, muestras in libreria.items():
        sim = max(cos_sim(embedding, m) for m in muestras)
        if sim > mejor_sim:
            mejor_sim, mejor_nombre = sim, nombre
    if mejor_sim >= umbral:
        return mejor_nombre, mejor_sim
    return None, mejor_sim


def anadir_muestra(proyecto, nombre, embedding, origen=None):
    """origen, si se conoce: {"audio": ruta, "inicio": segundos, "fin": segundos}.

    Si la nueva muestra es casi idéntica a una que ya se tiene guardada
    (similitud >= UMBRAL_DUPLICADO — mismas condiciones repetidas: mismo canal,
    mismo idioma, mismo día...), no se añade una entrada nueva. Así la librería
    no crece sin límite solo por confirmar la misma condición una y otra vez;
    solo crece con muestras que de verdad aportan una condición distinta.

    Devuelve (n_muestras, se_anadio) — n_muestras es el total actual para esa
    persona; se_anadio indica si esta llamada añadió una muestra nueva o no."""
    ruta = ruta_libreria(proyecto)
    datos = _cargar_y_migrar_si_hace_falta(ruta)
    existentes = datos.get(nombre, [])

    if existentes:
        mejor = max(cos_sim(embedding, np.array(m["embedding"], dtype="float32")) for m in existentes)
        if mejor >= UMBRAL_DUPLICADO:
            return len(existentes), False

    nueva = {"id": uuid.uuid4().hex[:10], "embedding": embedding.tolist(), "origen": origen}
    datos.setdefault(nombre, []).append(nueva)
    _guardar(ruta, datos)
    return len(datos[nombre]), True


def eliminar_persona(proyecto, nombre):
    ruta = ruta_libreria(proyecto)
    datos = _cargar_y_migrar_si_hace_falta(ruta)
    if nombre not in datos:
        return False
    _respaldar(ruta)
    del datos[nombre]
    _guardar(ruta, datos)
    return True


def _buscar_indice(muestras, id_muestra):
    return next((i for i, m in enumerate(muestras) if m["id"] == id_muestra), None)


def eliminar_muestra(proyecto, nombre, id_muestra):
    ruta = ruta_libreria(proyecto)
    datos = _cargar_y_migrar_si_hace_falta(ruta)
    muestras = datos.get(nombre, [])
    idx = _buscar_indice(muestras, id_muestra)
    if idx is None:
        return False
    _respaldar(ruta)
    muestras.pop(idx)
    if not muestras:
        del datos[nombre]
    _guardar(ruta, datos)
    return True


def reclasificar_muestra(proyecto, nombre_actual, id_muestra, nombre_nuevo):
    """Mueve una muestra de una persona a otra (o a un nombre nuevo), conservando
    su embedding y origen."""
    ruta = ruta_libreria(proyecto)
    datos = _cargar_y_migrar_si_hace_falta(ruta)
    muestras = datos.get(nombre_actual, [])
    idx = _buscar_indice(muestras, id_muestra)
    if idx is None:
        return False
    _respaldar(ruta)
    muestra = muestras.pop(idx)
    if not muestras:
        del datos[nombre_actual]
    datos.setdefault(nombre_nuevo, []).append(muestra)
    _guardar(ruta, datos)
    return True


def ruta_confirmados(proyecto):
    return str(config.dir_voiceprints() / f"{proyecto}.audit_confirmados.json")


def cargar_confirmados(proyecto):
    """Hallazgos de auditoría que el usuario ya marcó como correctos — no volver
    a mostrarlos aunque la similitud siga igual. Persiste en disco entre sesiones."""
    ruta = ruta_confirmados(proyecto)
    if not os.path.exists(ruta):
        return set()
    with open(ruta, encoding="utf-8") as f:
        return {tuple(x) for x in json.load(f)}


def _clave_hallazgo(tipo, id_a, id_b):
    return (tipo,) + tuple(sorted((id_a, id_b)))


def marcar_como_correcto(proyecto, tipo, id_a, id_b):
    ruta = ruta_confirmados(proyecto)
    confirmados = cargar_confirmados(proyecto)
    confirmados.add(_clave_hallazgo(tipo, id_a, id_b))
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump([list(c) for c in confirmados], f)


def auditar_libreria(proyecto, umbral_confusion=0.80, incluir_confirmados=False):
    """Detecta tres tipos de problema en la librería, señalando siempre el par de
    muestras (por id) más representativo de cada hallazgo:
    - 'dispersion': dos muestras de la misma persona poco parecidas entre sí
      (posible mezcla de dos condiciones de grabación distintas, o de dos personas).
    - 'duplicado': dos muestras de la misma persona casi idénticas entre sí
      (misma condición repetida — no aportan nada nuevo, se puede borrar una).
    - 'confusion': dos muestras de personas distintas muy parecidas entre sí
      (riesgo real de identificar mal, sobre todo si superan UMBRAL_DEFECTO).

    Por defecto no incluye los que el usuario ya marcó como correctos (ver
    marcar_como_correcto) — pásalos con incluir_confirmados=True si hace falta.
    """
    datos = cargar_libreria_con_origen(proyecto)
    confirmados = set() if incluir_confirmados else cargar_confirmados(proyecto)
    problemas = []

    def emb(m):
        return np.array(m["embedding"], dtype="float32")

    for nombre, muestras in datos.items():
        if len(muestras) < 2:
            continue
        peor = mejor = None
        for i, a in enumerate(muestras):
            for b in muestras[i + 1:]:
                sim = cos_sim(emb(a), emb(b))
                if peor is None or sim < peor[0]:
                    peor = (sim, a["id"], b["id"])
                if mejor is None or sim > mejor[0]:
                    mejor = (sim, a["id"], b["id"])

        sim, id_a, id_b = peor
        if sim < UMBRAL_DEFECTO:
            problemas.append({
                "tipo": "dispersion", "similitud": sim,
                "nombre_a": nombre, "id_a": id_a,
                "nombre_b": nombre, "id_b": id_b,
            })

        sim, id_a, id_b = mejor
        if sim >= UMBRAL_DUPLICADO:
            problemas.append({
                "tipo": "duplicado", "similitud": sim,
                "nombre_a": nombre, "id_a": id_a,
                "nombre_b": nombre, "id_b": id_b,
            })

    nombres = list(datos.keys())
    for i, n1 in enumerate(nombres):
        for n2 in nombres[i + 1:]:
            mejor = None
            for a in datos[n1]:
                for b in datos[n2]:
                    sim = cos_sim(emb(a), emb(b))
                    if mejor is None or sim > mejor[0]:
                        mejor = (sim, a["id"], b["id"])
            if mejor and mejor[0] >= umbral_confusion:
                sim, id_a, id_b = mejor
                problemas.append({
                    "tipo": "confusion", "similitud": sim,
                    "nombre_a": n1, "id_a": id_a,
                    "nombre_b": n2, "id_b": id_b,
                })

    if confirmados:
        problemas = [p for p in problemas if _clave_hallazgo(p["tipo"], p["id_a"], p["id_b"]) not in confirmados]

    return problemas
