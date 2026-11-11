"""Grabación de reuniones: mezcla lo que suena en el PC con tu micrófono.

Usa soundcard, que en Windows graba "lo que suena" por WASAPI loopback y en
Linux por el monitor de PipeWire/PulseAudio, así que el mismo código vale para
los dos. Cada fuente se graba en su propio hilo y un tercer hilo las mezcla y
escribe un WAV mono de 16 kHz (lo que necesitan whisper y la identificación
por voz) mientras se graba, así que si algo se cuelga lo grabado ya está en
disco.
"""
import queue
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000
TROZO = SR // 10           # cada fuente entrega trozos de 0,1 s
DESFASE_MAX = SR           # si una fuente va >1 s por detrás, se rellena con silencio
AVISO_MICRO_MUDO_S = 10    # micro a cero absoluto durante este tiempo -> aviso


def _sc():
    import soundcard
    return soundcard


def _loopback_de(altavoz):
    """El "micrófono" que captura lo que suena por ese altavoz."""
    sc = _sc()
    candidatos = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    for m in candidatos:
        if m.id == altavoz.id or m.id.startswith(altavoz.id) or altavoz.name in m.name:
            return m
    return None


def listar_dispositivos():
    """{"altavoces": [(nombre, es_defecto)], "micros": [(nombre, es_defecto)]}"""
    sc = _sc()
    spk_def, mic_def = sc.default_speaker(), sc.default_microphone()
    return {
        "altavoces": [(s.name, s.id == spk_def.id) for s in sc.all_speakers()],
        "micros": [(m.name, m.id == mic_def.id) for m in sc.all_microphones()],
    }


def _buscar(lista, nombre):
    return next((d for d in lista if d.name == nombre or d.id == nombre), None)


def resolver_dispositivos(altavoz=None, micro=None):
    """(loopback, micro) a partir de nombres; None = el de por defecto."""
    sc = _sc()
    spk = _buscar(sc.all_speakers(), altavoz) if altavoz else sc.default_speaker()
    if spk is None:
        raise ValueError(f"No encuentro la salida de audio '{altavoz}'")
    loop = _loopback_de(spk)
    if loop is None:
        raise ValueError(f"No se puede grabar lo que suena por '{spk.name}' (sin loopback)")
    mic = _buscar(sc.all_microphones(), micro) if micro else sc.default_microphone()
    if mic is None:
        raise ValueError(f"No encuentro el micrófono '{micro}'")
    return loop, mic


class Grabacion:
    """g = Grabacion(ruta); g.empezar(); ... g.parar()

    Mientras graba: g.segundos, g.niveles ({"sistema", "micro"}: volumen RMS
    del último trozo) y g.avisos (lista de textos, p. ej. micro silenciado)."""

    def __init__(self, destino, altavoz=None, micro=None):
        self.destino = Path(destino)
        self.loop, self.mic = resolver_dispositivos(altavoz, micro)
        self.niveles = {"sistema": 0.0, "micro": 0.0}
        self.avisos = []
        self.errores = []
        self._colas = {"sistema": queue.Queue(), "micro": queue.Queue()}
        self._vivas = {"sistema": True, "micro": True}
        self._parar = threading.Event()
        self._hilos = []
        self._escritas = 0
        self._micro_mudo_desde = None

    @property
    def segundos(self):
        return self._escritas / SR

    def empezar(self):
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        self._archivo = sf.SoundFile(str(self.destino), "w", samplerate=SR, channels=1, subtype="PCM_16")
        for nombre, disp in (("sistema", self.loop), ("micro", self.mic)):
            self._hilos.append(threading.Thread(target=self._capturar, args=(nombre, disp), daemon=True))
        self._hilos.append(threading.Thread(target=self._mezclar, daemon=True))
        for h in self._hilos:
            h.start()

    def parar(self):
        self._parar.set()
        for h in self._hilos:
            h.join(timeout=5)
        self._archivo.close()
        return self.destino

    def _capturar(self, nombre, disp):
        try:
            # blocksize: sin él, PulseAudio entrega en bloques de ~2 s y al parar se pierden
            with disp.recorder(samplerate=SR, channels=1, blocksize=TROZO) as r:
                while not self._parar.is_set():
                    datos = r.record(numframes=TROZO)
                    datos = datos[:, 0] if datos.ndim > 1 else datos
                    self.niveles[nombre] = float(np.sqrt(np.mean(datos ** 2))) if len(datos) else 0.0
                    self._colas[nombre].put(datos.astype("float32"))
        except Exception as e:  # dispositivo desconectado, etc.: la otra fuente sigue
            self.errores.append(f"{nombre}: {e}")
        finally:
            self._vivas[nombre] = False
            self.niveles[nombre] = 0.0

    def _mezclar(self):
        pendiente = {"sistema": np.zeros(0, "float32"), "micro": np.zeros(0, "float32")}
        ultimo_flush = time.time()
        while True:
            terminando = self._parar.is_set()
            # Antes de vaciar las colas: si ya no hay capturas vivas, lo que quede
            # en las colas es lo último y se puede cerrar tras escribirlo.
            capturando = any(h.is_alive() for h in self._hilos[:2])
            for nombre, cola in self._colas.items():
                trozos = []
                while True:
                    try:
                        trozos.append(cola.get_nowait())
                    except queue.Empty:
                        break
                if trozos:
                    pendiente[nombre] = np.concatenate([pendiente[nombre], *trozos])

            a, b = pendiente["sistema"], pendiente["micro"]
            # Una fuente muerta o atascada no puede frenar a la otra: se rellena con silencio
            for x, y, nombre in ((a, b, "sistema"), (b, a, "micro")):
                if len(y) - len(x) > DESFASE_MAX or (not self._vivas[nombre] and len(y) > len(x)) or terminando:
                    pendiente[nombre] = np.concatenate([x, np.zeros(max(0, len(y) - len(x)), "float32")])
            a, b = pendiente["sistema"], pendiente["micro"]

            n = min(len(a), len(b))
            if n:
                self._archivo.write(np.clip(a[:n] + b[:n], -1.0, 1.0))
                self._escritas += n
                pendiente["sistema"], pendiente["micro"] = a[n:], b[n:]
                self._vigilar_micro(b[:n])
            if time.time() - ultimo_flush > 5:
                self._archivo.flush()  # cabecera al día: si se corta, el WAV sigue sirviendo
                ultimo_flush = time.time()
            if terminando and not capturando:
                break
            time.sleep(0.1)

    def _vigilar_micro(self, datos):
        if np.any(datos != 0):
            self._micro_mudo_desde = None
            return
        if self._micro_mudo_desde is None:
            self._micro_mudo_desde = self._escritas
        elif (self._escritas - self._micro_mudo_desde) / SR > AVISO_MICRO_MUDO_S:
            aviso = "El micrófono no recoge nada: ¿está silenciado o es el que toca?"
            if aviso not in self.avisos:
                self.avisos.append(aviso)


def desde_preferencias(destino):
    """Grabacion con el altavoz y el micro elegidos en Ajustes. Si ya no
    existen (auriculares desconectados...), con los del sistema y un aviso.
    Devuelve (grabacion, aviso | None)."""
    from . import config

    estado = config.cargar_estado()
    altavoz, micro = estado.get("altavoz"), estado.get("micro")
    try:
        return Grabacion(destino, altavoz=altavoz, micro=micro), None
    except ValueError as e:
        if not (altavoz or micro):
            raise
        return Grabacion(destino), f"{e}: se usan los del sistema"


def nombre_por_defecto(descripcion=""):
    from datetime import datetime
    ahora = datetime.now()
    return f"{ahora:%Y-%m-%d}_{descripcion.strip() or 'reunion_' + ahora.strftime('%H%M')}"
