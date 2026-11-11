"""Transcribe: the running transcriptions (of every project) and the current
project's untranscribed audio."""
import time
from datetime import datetime
from pathlib import Path

from nicegui import run, ui

from .. import config, jobs
from ..i18n import N_, _
from .common import choose_path, frame, no_project, project_dir, shown_path, title, transcribe_dialog

STEP_NAMES = {"compress": N_("Compress"), "upload": N_("Upload"), "cloud": N_("In the cloud"),
              "transcribe": N_("Transcribe"), "speakers": N_("Who speaks")}
ENGINES = {"cloud": (N_("Cloud"), "cloud"), "local": (N_("This PC"), "computer")}


def _steps(info):
    """A row of steps: done ones with a tick, the current one highlighted."""
    steps = jobs.STEPS[info["engine"]]
    current = steps.index(info["step"])
    with ui.row().classes("items-center gap-1 flex-wrap"):
        for i, step in enumerate(steps):
            if i:
                ui.element("div").classes("w-4 h-[2px] " + ("bg-primary" if i <= current else "bg-gray-400/40"))
            if i < current:
                ui.chip(_(STEP_NAMES[step]), icon="check", color="positive", text_color="white").props("dense")
            elif i == current:
                ui.chip(_(STEP_NAMES[step]), icon="autorenew", color="primary", text_color="white") \
                    .props("dense").classes("font-medium")
            else:
                ui.chip(_(STEP_NAMES[step])).props("dense outline").classes("opacity-60")


def _minutes(seconds):
    return jobs.format_minutes(seconds) if seconds else ""


def _running_card(job, info):
    name = Path(job["audio"]).name
    with ui.card().classes("w-full gap-3"):
        with ui.row().classes("w-full items-center gap-4 no-wrap"):
            if info["pct"] is None:
                ui.spinner("audio", size="3.2rem", color="primary")
            else:
                with ui.circular_progress(info["pct"], min=0, max=100, size="3.6rem", color="primary",
                                          show_value=False).props('thickness=0.18 track-color="grey-4"'):
                    ui.label(f"{info['pct']}%").classes("text-sm font-semibold")
            with ui.column().classes("grow gap-1 min-w-0"):
                ui.label(name).classes("font-medium break-all")
                with ui.row().classes("items-center gap-2"):
                    if job.get("project"):
                        ui.badge(job["project"], color="secondary").props("rounded")
                    engine_name, engine_icon = ENGINES[info["engine"]]
                    with ui.row().classes("items-center gap-1 text-xs soft-text"):
                        ui.icon(engine_icon, size="xs")
                        ui.label(_(engine_name))
            with ui.column().classes("items-end gap-0 shrink-0"):
                if info["left"]:
                    ui.label(_("~{time} left", time=_minutes(info["left"]))).classes("text-lg font-semibold")
                if info["elapsed"]:
                    ui.label(_("{time} in this step", time=_minutes(info["elapsed"]))).classes("text-xs soft-text")
        _steps(info)
        bar = ui.linear_progress(value=(info["pct"] or 0) / 100, show_value=False, color="primary") \
            .props("rounded size=8px")
        if info["pct"] is None:
            bar.props("indeterminate")
        ui.label(info["text"]).classes("text-sm soft-text")


def _finished_card(job, status):
    name = Path(job["audio"]).name
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center gap-3"):
            if status == "done":
                ui.icon("check_circle", color="positive", size="md")
                with ui.column().classes("grow gap-0"):
                    ui.label(_("{name}: done", name=name)).classes("font-medium break-all")
                    if job.get("project"):
                        ui.label(job["project"]).classes("text-xs soft-text")
                ui.button(_("Review speakers"), icon="record_voice_over",
                          on_click=lambda: _review(job)).props("unelevated no-caps")
            else:
                ui.icon("error", color="negative", size="md")
                ui.label(_("{name}: failed", name=name)).classes("font-medium grow break-all")
                _log_button(job["log"])


def _review(job):
    if job.get("project"):
        config.update_state(last_project=job["project"])
    ui.navigate.to("/review")


@ui.page("/transcribe")
def page():
    with frame("/transcribe") as project:
        folder = {"path": ""}
        title(_("Transcribe"))
        ui.label(_("Running")).classes("text-lg font-medium -mb-2")
        running = ui.column().classes("w-full gap-3")
        if not project:
            no_project()
        with ui.card().classes("w-full gap-3") as waiting:
            with ui.row().classes("w-full items-center gap-4"):
                ui.label(_("Waiting to be transcribed in {project}", project=project)).classes("text-lg font-medium")
                ui.space()
                ui.button(_("Another file..."), icon="audio_file", on_click=lambda: other_file()) \
                    .props("flat no-caps")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="primary")
                folder_label = ui.label().classes("font-mono text-sm break-all")
                ui.button(_("Change"), on_click=lambda: change_folder()).props("flat dense no-caps")
            listing = ui.column().classes("w-full gap-1")
        waiting.visible = project is not None

    async def load():
        if not project:
            return
        folder["path"] = project_dir(project)
        folder_label.set_text(shown_path(folder["path"]))
        listing.clear()
        with listing:
            ui.spinner()
        todo = await run.io_bound(jobs.untranscribed, folder["path"])
        listing.clear()
        with listing:
            if not todo:
                ui.label(_("No untranscribed audio in this folder.")).classes("soft-text")
            for path, dur in todo:
                with ui.row().classes("w-full items-center gap-3 py-1 line-below"):
                    ui.icon("graphic_eq", color="primary")
                    with ui.column().classes("grow gap-0"):
                        ui.label(str(path.relative_to(folder["path"]))).classes("break-all")
                        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                        ui.label(f"{jobs.format_minutes(dur)} · {date}" if dur else date).classes("text-sm soft-text")
                    ui.button(_("Transcribe"), icon="play_arrow", on_click=lambda p=path: transcribe(p)) \
                        .props("flat no-caps")

    async def transcribe(path):
        if await transcribe_dialog(path, project):
            await load()
            await draw_running()

    async def change_folder():
        if path := await choose_path(folder["path"]):
            config.set_project_dir(project, path)
            await load()

    async def other_file():
        if path := await choose_path(folder["path"], folders=False):
            await transcribe(path)

    # Finished jobs shown: the ones the user hadn't been told about when the
    # page opened, and the ones that end while it's open
    opened = time.time()
    shown = {"signature": None, "pids": set(), "told": set()}

    def read():
        all_jobs = jobs.check_jobs()
        infos = {job["pid"]: jobs.progress_info(job["log"], job.get("engine"))
                 for job, status, _text in all_jobs if status == "running"}
        return all_jobs, infos

    async def draw_running():
        all_jobs, infos = await run.io_bound(read)
        finished = []
        for job, status, text in all_jobs:
            if status == "running":
                continue
            pid = job["pid"]
            if job.get("ended", 0) >= opened and pid not in shown["told"]:
                name = Path(job["audio"]).name
                if status == "done":
                    ui.notify(_("Done: {name}", name=name), type="positive")
                else:
                    ui.notify(_("Failed: {name}", name=name), type="negative")
            if pid in shown["pids"] or not job.get("seen") or job.get("ended", 0) >= opened:
                shown["pids"].add(pid)
                finished.append((job, status, text))
        new_told = {job["pid"] for job, _status, _text in finished} - shown["told"]
        shown["told"] |= new_told
        if new_told:
            await run.io_bound(jobs.mark_seen, new_told)
        active = [job for job, status, _text in all_jobs if status == "running"]
        # Redrawn only when something changed, so nothing blinks
        signature = ([(j["pid"], infos[j["pid"]]["text"]) for j in active],
                     [(j["pid"], status) for j, status, _text in finished])
        if signature == shown["signature"]:
            return
        shown["signature"] = signature
        running.clear()
        with running:
            if not active and not finished:
                with ui.card().classes("w-full"):
                    ui.label(_("Nothing right now.")).classes("soft-text")
            for job in active:
                _running_card(job, infos[job["pid"]])
            for job, status, _text in finished:
                _finished_card(job, status)

    ui.timer(0.1, load, once=True)
    ui.timer(0.1, draw_running, once=True)
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
