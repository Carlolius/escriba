"""Home page: record a meeting."""
import math
from pathlib import Path

from nicegui import run, ui

from .. import config, jobs, record
from ..i18n import _
from .common import choose_path, frame, project_dir, project_selector, title, transcribe_dialog

# One sound card: the recording belongs to the server, not to the tab. It goes
# on if the browser is closed, and any tab can stop it.
STATE = {"recording": None, "project": None, "last": None}


def _level(rms):
    """Voice RMS is usually around 0.01-0.1: log scale from 0 to 1."""
    return 0.0 if rms <= 0 else max(0.0, min(1.0, (math.log10(rms) + 4) / 4))


@ui.page("/")
def page():
    with frame("/"):
        title(_("Record a meeting"),
              _("Records what plays on the PC (the people on the call) and your microphone, mixed."))

        with ui.card().classes("w-full gap-3") as prepare:
            with ui.row().classes("w-full items-end gap-4"):
                project = project_selector(lambda p: folder.set_text(project_dir(p)))
                description = ui.input(_("Description"), placeholder=_("weekly_followup")).classes("grow")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="grey-7")
                folder = ui.label(project_dir(project.value) if project.value else "").classes(
                    "font-mono text-sm break-all")
                ui.button(_("Change"), on_click=lambda: change_folder()).props("flat dense no-caps")
            ui.label(_("Tell the others you are recording the meeting before you start.")) \
                .classes("text-sm soft-text")
            button = ui.button(_("Start recording"), icon="fiber_manual_record", color="red",
                               on_click=lambda: start()).classes("self-start")

        with ui.card().classes("w-full gap-3") as recording:
            with ui.row().classes("items-center gap-3"):
                ui.icon("fiber_manual_record", color="red").classes("animate-pulse text-2xl")
                clock = ui.label().classes("text-3xl font-mono")
                file_name = ui.label().classes("soft-text break-all")
            ui.label(_("What plays")).classes("text-sm soft-text")
            system_level = ui.linear_progress(value=0, show_value=False).props("instant-feedback rounded size=10px")
            ui.label(_("Microphone")).classes("text-sm soft-text")
            mic_level = ui.linear_progress(value=0, show_value=False, color="teal") \
                .props("instant-feedback rounded size=10px")
            warnings = ui.label().classes("text-orange-9")
            ui.button(_("Stop"), icon="stop", on_click=lambda: stop()).classes("self-start")

        with ui.card().classes("w-full gap-2") as done:
            last = ui.label().classes("font-medium break-all")
            with ui.row():
                ui.button(_("Transcribe"), icon="subtitles", on_click=lambda: transcribe_last())
                ui.button(_("Record another"), on_click=lambda: (STATE.update(last=None), refresh())).props("flat")

    async def change_folder():
        if not project.value:
            ui.notify(_("Pick a project first"), type="warning")
            return
        if path := await choose_path(project_dir(project.value)):
            config.set_project_dir(project.value, path)
            folder.set_text(str(path))

    async def start():
        if not project.value:
            ui.notify(_("Pick or create a project"), type="warning")
            return
        if STATE["recording"]:
            return
        target = Path(folder.text) / f"{record.default_name(description.value or '')}.wav"
        if target.exists():
            ui.notify(_("{name} already exists: change the description", name=target.name), type="warning")
            return
        button.disable()
        try:
            r, warning = await run.io_bound(record.from_preferences, target)
            r.start()
        except Exception as e:
            ui.notify(_("Can't record: {error}", error=e), type="negative", multi_line=True)
            return
        finally:
            button.enable()
        if warning:
            ui.notify(warning, type="warning")
        config.set_project_dir(project.value, folder.text)
        STATE.update(recording=r, project=project.value, last=None)
        refresh()

    async def stop():
        r = STATE["recording"]
        if not r:
            return
        STATE["recording"] = None
        path = await run.io_bound(r.stop)
        STATE["last"] = (path, r.seconds)
        refresh()

    async def transcribe_last():
        path, _seconds = STATE["last"]
        if await transcribe_dialog(path, STATE["project"]):
            STATE["last"] = None
            refresh()

    def refresh():
        r = STATE["recording"]
        prepare.visible = r is None and STATE["last"] is None
        recording.visible = r is not None
        done.visible = r is None and STATE["last"] is not None
        if r:
            s = int(r.seconds)
            clock.set_text(f"{s // 60}:{s % 60:02d}")
            file_name.set_text(r.target.name)
            system_level.set_value(_level(r.levels["system"]))
            mic_level.set_value(_level(r.levels["mic"]))
            warnings.set_text("  ".join(r.warnings + r.errors))
        elif STATE["last"]:
            path, seconds = STATE["last"]
            last.set_text(_("Recorded {name} ({duration})", name=path.name, duration=jobs.format_minutes(seconds)))

    refresh()
    ui.timer(0.2, refresh)
