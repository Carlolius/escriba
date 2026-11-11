"""Comprime a Opus los audios de reuniones ya transcritas y revisadas.

Un .wav se archiva cuando ya tiene su .txt y, si tiene .speakers.json, ese
sidecar está revisado. Se convierte a .opus (mono, ~16 kbps: ~15 veces menos
que el WAV, sin diferencia audible en voz ni en las huellas de voz), se
comprueba que dure lo mismo, se actualizan las rutas que apuntaban al .wav
(muestras de las librerías de voces y sus .bak, y el sidecar) y se borra el .wav.

Se llama solo al terminar de revisar los hablantes de una reunión; para
convertir de golpe lo ya revisado: escriba archivar (ver --help).
"""
import json
from pathlib import Path

from . import audio as audio_util
from . import config


def ruta_sidecar(wav):
    return wav.with_suffix(".speakers.json")


def listo_para_archivar(wav):
    if not wav.with_suffix(".txt").exists():
        return False
    sidecar = ruta_sidecar(wav)
    if not sidecar.exists():
        return True
    try:
        return bool(json.loads(sidecar.read_text(encoding="utf-8")).get("revisado"))
    except (OSError, json.JSONDecodeError):
        return False


def _cambiar_rutas_en_muestras(muestras, viejo, nuevo):
    cambios = 0
    for m in muestras:
        origen = m.get("origen") if isinstance(m, dict) else None
        if origen and Path(origen["audio"]).resolve() == viejo:
            origen["audio"] = str(nuevo)
            cambios += 1
    return cambios


def actualizar_rutas(viejo, nuevo):
    """Cambia viejo -> nuevo en las muestras de todas las librerías de voces
    (también en los .bak, para que "Restaurar backup" no resucite rutas muertas)
    y en el sidecar de la propia reunión. Devuelve cuántas referencias cambió."""
    viejo, nuevo = Path(viejo).resolve(), Path(nuevo).resolve()
    total = 0
    for ruta in sorted(config.dir_voiceprints().glob("*.json*")):
        if ".audit_confirmados" in ruta.name:
            continue
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        cambios = sum(_cambiar_rutas_en_muestras(m, viejo, nuevo) for m in datos.values() if isinstance(m, list))
        if cambios:
            ruta.write_text(json.dumps(datos), encoding="utf-8")
            total += cambios

    # El sidecar puede seguir junto a la ruta vieja o haberse movido con el audio
    for sidecar in {ruta_sidecar(viejo), ruta_sidecar(nuevo)}:
        if not sidecar.exists():
            continue
        datos = json.loads(sidecar.read_text(encoding="utf-8"))
        cambios = _cambiar_rutas_en_muestras(datos.get("clusters", {}).values(), viejo, nuevo)
        if cambios:
            config.escribir_json(sidecar, datos)
            total += cambios
    return total


def archivar(wav):
    """Convierte wav -> opus, actualiza referencias y borra el wav.
    Devuelve (ruta_opus, bytes_ahorrados, referencias_cambiadas)."""
    wav = Path(wav).resolve()
    opus = wav.with_suffix(".opus")
    tmp = opus.with_name(opus.name + ".tmp")
    dur_wav = audio_util.duracion(wav)
    audio_util.comprimir_opus(wav, tmp)
    dur_opus = audio_util.duracion(tmp) or 0
    if abs(dur_wav - dur_opus) > 0.5:
        tmp.unlink()
        raise RuntimeError(f"{wav.name}: duración distinta tras convertir ({dur_wav:.1f}s vs {dur_opus:.1f}s)")
    tmp.rename(opus)
    ahorro = wav.stat().st_size - opus.stat().st_size
    referencias = actualizar_rutas(wav, opus)
    wav.unlink()
    return opus, ahorro, referencias


def directorios_del_estado():
    """Últimos directorios de cada proyecto (los mismos que recorre el menú)."""
    return [Path(v) for k, v in config.cargar_estado().items() if k.startswith("ultimo_dir_")]


def archivar_directorios(dirs, simular=False):
    wavs = sorted({w.resolve() for d in dirs if d.exists() for w in d.rglob("*.wav")})
    candidatos = [w for w in wavs if listo_para_archivar(w)]
    for w in wavs:
        if w not in candidatos:
            print(f"  se queda en WAV (sin transcribir o sin revisar): {w}")

    total_ahorro = 0
    for w in candidatos:
        if simular:
            print(f"  convertiría: {w} ({w.stat().st_size / 1e6:.0f} MB)")
            continue
        print(f"{w.name}:", flush=True)
        opus, ahorro, refs = archivar(w)
        total_ahorro += ahorro
        print(f"  ✓ {opus.name}: -{ahorro / 1e6:.0f} MB, {refs} referencia(s) actualizadas")
    if not simular:
        print(f"{len(candidatos)} audio(s) archivados, {total_ahorro / 1e6:.0f} MB liberados")
