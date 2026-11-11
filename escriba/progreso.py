"""Progreso de transcripción, diarización, compresión y subida.

En una terminal pinta barras con rich (porcentaje, tiempo transcurrido y
restante). Si la salida va a un log (segundo plano), escribe una línea cada 5%
para poder seguirlo con tail -f.
"""
import sys
import time


def _mmss(segundos):
    segundos = int(segundos)
    return f"{segundos // 60}:{segundos % 60:02d}"


class Progreso:
    def __init__(self):
        self.tty = sys.stdout.isatty()
        self._tareas = {}  # nombre -> (id rich | inicio, último % impreso)
        if self.tty:
            from rich.progress import (
                BarColumn, Progress, TaskProgressColumn, TextColumn,
                TimeElapsedColumn, TimeRemainingColumn,
            )
            self._rich = Progress(
                TextColumn("{task.description:<24}"), BarColumn(), TaskProgressColumn(),
                TimeElapsedColumn(), TextColumn("quedan"), TimeRemainingColumn(),
            )
            self._rich.start()

    def actualizar(self, nombre, completado, total):
        if not total:
            return
        if self.tty:
            if nombre not in self._tareas:
                self._tareas[nombre] = self._rich.add_task(nombre, total=total)
            self._rich.update(self._tareas[nombre], completed=completado, total=total)
            return

        inicio, ultimo = self._tareas.setdefault(nombre, (time.time(), -5))
        pct = min(100, int(100 * completado / total))
        if pct - ultimo < 5 and pct < 100:
            return
        if pct == ultimo:
            return
        transcurrido = time.time() - inicio
        resto = f", quedan ~{_mmss(transcurrido * (100 - pct) / pct)}" if 0 < pct < 100 else ""
        print(f"{nombre}: {pct}% ({_mmss(transcurrido)}{resto})", flush=True)
        self._tareas[nombre] = (inicio, pct)

    def hook_pyannote(self):
        """Hook para Pipeline(...)(audio, hook=...): solo los pasos que reportan avance."""
        nombres = {"segmentation": "Segmentando voces", "embeddings": "Identificando hablantes"}

        def hook(paso, artefacto, file=None, total=None, completed=None):
            if total is not None and completed is not None and paso in nombres:
                self.actualizar(nombres[paso], completed, total)
        return hook

    def cerrar(self):
        if self.tty:
            self._rich.stop()
