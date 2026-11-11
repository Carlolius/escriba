"""Home page: record a meeting."""
import html
import math
from collections import deque

from nicegui import run, ui

from .. import config, jobs, record
from ..i18n import _
from .common import choose_path, frame, no_project, project_dir, shown_path, title, transcribe_dialog

# One sound card: the recording belongs to the server, not to the tab. It goes
# on if the browser is closed, and any tab can stop it.
STATE = {"recording": None, "project": None, "last": None}

HISTORY = 64          # bars in each meter: 64 x 0.2 s = the last ~13 seconds
CHANNELS = (("system", "headphones", "#818cf8"), ("mic", "mic", "#fbbf24"))
METER_CSS = """
.escriba-rec { background: radial-gradient(120% 140% at 0% 0%, #2a2a5a 0%, #14152c 55%, #0d0e1f 100%) !important;
  color: white; }
.escriba-rec .soft { color: #a5a9cf; }
.meter-row { display: flex; align-items: center; gap: 12px; }
.meter-name { width: 9.5rem; display: flex; align-items: center; gap: 6px; font-size: 13px; color: #c7cbef; }
.meter-row svg { flex: 1; height: 52px; min-width: 0; }
.meter-db { width: 4.2rem; text-align: right; font: 600 13px ui-monospace, monospace; }
@media (max-width: 640px) { .meter-name span { display: none; } .meter-name { width: auto; } }
"""


def _level(rms):
    """Voice RMS is usually around 0.01-0.1: log scale from 0 to 1."""
    return 0.0 if rms <= 0 else max(0.0, min(1.0, (math.log10(rms) + 4) / 4))


def _db(rms):
    return "-∞ dB" if rms <= 1e-5 else f"{max(-99, round(20 * math.log10(rms)))} dB"


def meters_html(history, rms, names):
    """Two scrolling level meters (what plays, microphone): one bar every
    0.2 s, the newest on the right and brighter. Grey below -60 dB (silence,
    background hum)."""
    rows = []
    for key, icon, color in CHANNELS:
        levels = list(history[key])
        levels = [0.0] * (HISTORY - len(levels)) + levels
        bars = []
        for i, level in enumerate(levels):
            h = max(2.0, level * 48)
            opacity = 0.25 + 0.75 * (i + 1) / HISTORY
            fill = color if level > 0.25 else "#4b4f7a"
            bars.append(f'<rect x="{i * 5}" y="{26 - h / 2:.1f}" width="3" height="{h:.1f}" rx="1.5" '
                        f'fill="{fill}" fill-opacity="{opacity:.2f}"/>')
        current = levels[-1]
        db_color = color if current > 0.25 else "#6b6f99"
        rows.append(
            f'<div class="meter-row"><div class="meter-name">'
            f'<i class="q-icon notranslate material-icons" style="font-size:20px;color:{color}">{icon}</i>'
            f'<span>{html.escape(names[key])}</span></div>'
            f'<svg viewBox="0 0 {HISTORY * 5} 52" preserveAspectRatio="none">{"".join(bars)}</svg>'
            f'<div class="meter-db" style="color:{db_color}">{_db(rms[key])}</div></div>')
    return '<div class="flex flex-col gap-2">' + "".join(rows) + "</div>"


@ui.page("/")
def page():
    with frame("/") as project:
        folder = {"path": project_dir(project) if project else ""}
        ui.add_css(METER_CSS)
        title(_("Record a meeting"),
              _("Records what plays on the PC (the people on the call) and your microphone, mixed."))
        if not project:
            no_project()

        with ui.card().classes("w-full gap-4") as prepare:
            with ui.row().classes("w-full items-end gap-4"):
                description = ui.input(_("Description"), placeholder=_("weekly_followup")).classes("grow")
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder", color="primary")
                folder_label = ui.label(shown_path(folder["path"]) if project else "") \
                    .classes("font-mono text-sm break-all")
                ui.button(_("Change"), on_click=lambda: change_folder()).props("flat dense no-caps")
            with ui.row().classes("items-center gap-2 text-sm soft-text"):
                ui.icon("campaign", color="warning")
                ui.label(_("Tell the others you are recording the meeting before you start."))
            button = ui.button(_("Start recording"), icon="fiber_manual_record", color="negative",
                               on_click=lambda: start()).props("size=lg rounded unelevated").classes("self-start")

        with ui.card().classes("escriba-rec w-full gap-4 p-6") as recording:
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("fiber_manual_record", color="red").classes("animate-pulse text-3xl")
                clock = ui.label().classes("text-4xl font-mono font-semibold tracking-wider")
                with ui.column().classes("gap-0 grow min-w-0"):
                    file_name = ui.label().classes("break-all font-medium")
                    recording_project = ui.label().classes("soft text-sm")
                ui.button(_("Stop"), icon="stop", color="white", on_click=lambda: stop()) \
                    .props("rounded unelevated text-color=negative size=lg")
            meters = ui.html("", sanitize=False).classes("w-full")
            warnings = ui.label().classes("text-amber-300")

        with ui.card().classes("w-full gap-3") as done:
            with ui.row().classes("items-center gap-2"):
                ui.icon("check_circle", color="positive", size="md")
                last = ui.label().classes("font-medium break-all")
            with ui.row():
                ui.button(_("Transcribe"), icon="subtitles", on_click=lambda: transcribe_last()).props("unelevated")
                ui.button(_("Record another"), on_click=lambda: (STATE.update(last=None), refresh())).props("flat")

    history = {key: deque(maxlen=HISTORY) for key, _icon, _color in CHANNELS}
    names = {"system": _("What plays"), "mic": _("Microphone")}

    async def change_folder():
        if not project:
            return
        if path := await choose_path(project_dir(project)):
            config.set_project_dir(project, path)
            folder["path"] = str(path)
            folder_label.set_text(shown_path(path))

    async def start():
        if not project:
            ui.notify(_("Create a project first, in the box at the top right"), type="warning")
            return
        if STATE["recording"]:
            return
        target = record.free_target(folder["path"], record.default_name(description.value or ""))
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
        config.set_project_dir(project, folder["path"])
        STATE.update(recording=r, project=project, last=None)
        for h in history.values():
            h.clear()
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
        prepare.visible = r is None and STATE["last"] is None and project is not None
        recording.visible = r is not None
        done.visible = r is None and STATE["last"] is not None
        if r:
            s = int(r.seconds)
            clock.set_text(f"{s // 60:02d}:{s % 60:02d}")
            file_name.set_text(r.target.name)
            recording_project.set_text(_("Project {project}", project=STATE["project"]))
            for key in history:
                history[key].append(_level(r.levels[key]))
            meters.set_content(meters_html(history, r.levels, names))
            warnings.set_text("  ".join(r.warnings + r.errors))
        elif STATE["last"]:
            path, seconds = STATE["last"]
            last.set_text(_("Recorded {name} ({duration})", name=path.name, duration=jobs.format_minutes(seconds)))

    refresh()
    ui.timer(0.2, refresh)
