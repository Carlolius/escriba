"""Transcribe: a project's untranscribed audio and the running transcriptions."""
from datetime import datetime
from pathlib import Path

from nicegui import run, ui

from .. import config, jobs
from ..i18n import _
from .common import choose_path, frame, project_dir, project_selector, title, transcribe_dialog


@ui.page("/transcribe")
def page():
    with frame("/transcribe"):
        title(_("Transcribe"))

        with ui.card().classes("w-full gap-2"):
            ui.label(_("Running")).classes("text-lg font-medium")
            running = ui.column().classes("w-full gap-1")

        with ui.card().classes("w-full gap-3"):
            with ui.row().classes("w-full items-end gap-4"):
                project = project_selector(lambda p: load())
                ui.space()
                ui.button(_("Another file..."), icon="audio_file", on_click=lambda: other_file()) \
                    .props("flat no-caps")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="grey-7")
                folder = ui.label().classes("font-mono text-sm break-all")
                ui.button(_("Change"), on_click=lambda: change_folder()).props("flat dense no-caps")
            listing = ui.column().classes("w-full gap-1")

    async def load():
        if not project.value:
            return
        folder.set_text(project_dir(project.value))
        listing.clear()
        with listing:
            ui.spinner()
        todo = await run.io_bound(jobs.untranscribed, folder.text)
        listing.clear()
        with listing:
            if not todo:
                ui.label(_("No untranscribed audio in this folder.")).classes("soft-text")
            for path, dur in todo:
                with ui.row().classes("w-full items-center gap-3 py-1 border-b border-gray-500/20"):
                    with ui.column().classes("grow gap-0"):
                        ui.label(str(path.relative_to(folder.text))).classes("break-all")
                        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                        ui.label(f"{jobs.format_minutes(dur)} · {date}" if dur else date).classes("text-sm soft-text")
                    ui.button(_("Transcribe"), icon="play_arrow", on_click=lambda p=path: transcribe(p)) \
                        .props("flat no-caps")

    async def transcribe(path):
        if await transcribe_dialog(path, project.value):
            await load()
            await draw_running()

    async def change_folder():
        if path := await choose_path(folder.text):
            config.set_project_dir(project.value, path)
            await load()

    async def other_file():
        if path := await choose_path(folder.text, folders=False):
            await transcribe(path)

    # check_jobs() reports each finished job only once: they're kept here to
    # keep showing them while the page is open
    finished = []

    async def draw_running():
        new = await run.io_bound(jobs.check_jobs)
        for job, status, _text in new:
            if status == "done":
                ui.notify(_("Done: {name}", name=Path(job["audio"]).name), type="positive")
            elif status == "failed":
                ui.notify(_("Failed: {name}", name=Path(job["audio"]).name), type="negative")
        finished.extend(x for x in new if x[1] != "running")
        shown = [x for x in new if x[1] == "running"] + finished
        running.clear()
        with running:
            if not shown:
                ui.label(_("Nothing right now.")).classes("soft-text")
            for job, status, text in shown:
                name = Path(job["audio"]).name
                with ui.row().classes("w-full items-center gap-2"):
                    if status == "running":
                        ui.spinner(size="sm")
                        ui.label(name).classes("font-medium")
                        ui.label(text).classes("soft-text")
                    elif status == "done":
                        ui.icon("check_circle", color="positive")
                        ui.label(_("{name}: done", name=name)).classes("font-medium")
                        ui.button(_("Review speakers"), on_click=lambda: ui.navigate.to("/review")) \
                            .props("flat dense no-caps")
                    else:
                        ui.icon("error", color="negative")
                        ui.label(_("{name}: failed", name=name)).classes("font-medium")
                        _log_button(job["log"])

    ui.timer(0.1, load, once=True)
    ui.timer(3.0, draw_running)


def _log_button(path):
    def show():
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")[-6000:]
        except OSError as e:
            text = str(e)
        with ui.dialog() as d, ui.card().classes("w-[48rem] max-w-full"):
            ui.code(text, language=None).classes("w-full max-h-96 overflow-auto")
            ui.button(_("Close"), on_click=d.close).props("flat")
        d.open()

    ui.button(_("See log"), on_click=show).props("flat dense no-caps")
