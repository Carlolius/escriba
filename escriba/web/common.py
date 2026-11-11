"""Pieces shared by every page: the frame (header and navigation), audio clips,
the folder browser and the transcribe dialog."""
import io
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

import soundfile as sf
from fastapi import Response
from nicegui import app, run, ui

from .. import audio as audio_util
from .. import config, jobs
from ..i18n import N_, _, _n
from ..transcribe import local_available, missing_key

SECTIONS = [
    ("/", N_("Record"), "mic"),
    ("/transcribe", N_("Transcribe"), "subtitles"),
    ("/review", N_("Review"), "record_voice_over"),
    ("/people", N_("People"), "groups"),
    ("/settings", N_("Settings"), "settings"),
]

LANGUAGES = {
    "auto": N_("Detect it"),
    "es": N_("Spanish"),
    "gl": N_("Galician (keeps the mix with Spanish)"),
    "en": N_("English"),
    "ca": N_("Catalan"),
    "pt": N_("Portuguese"),
    "fr": N_("French"),
    "de": N_("German"),
}
MODELS = {
    "medium": N_("medium (recommended)"),
    "turbo": N_("turbo: ~25% faster, sometimes skips sentences"),
    "large": N_("large: the most accurate and slowest (~3 GB)"),
    "small": "small",
    "base": "base",
    "tiny": "tiny",
}


def translated(options):
    return {k: _(v) for k, v in options.items()}


# ── Page frame ───────────────────────────────────────────────────────────────

HEADER_COLOR = "#2f4858"
# In dark mode the ink blue can't be read on black: the primary color (flat
# buttons, tabs, bars) gets lighter and filled buttons get dark text.
CSS = """
.soft-text { color: #5b6770; }
body.body--dark .soft-text { color: #a9b5bd; }
body.body--dark { --q-primary: #8db7d1 !important; }  /* NiceGUI sets it inline on <body> */
body.body--dark .q-btn.bg-primary { color: #10212b !important; }
"""
THEMES = {"light": False, "dark": True}  # anything else (system) = None: follow the system


@contextmanager
def frame(current_path):
    """Header with navigation and status (recording, running transcriptions);
    what's inside the with goes to the central column."""
    from . import record as record_page

    ui.page_title("Escriba")
    ui.dark_mode(THEMES.get(config.load_state().get("theme")))
    ui.add_css(CSS)
    with ui.header().classes("items-center gap-1 px-4 py-2").style(f"background-color: {HEADER_COLOR}"):
        ui.label("Escriba").classes("text-lg font-semibold mr-4")
        for path, title, icon in SECTIONS:
            b = ui.button(_(title), icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props("flat no-caps")
            b.classes("text-white" + (" bg-white/20" if path == current_path else ""))
        ui.space()
        recording = ui.label().classes("text-white font-medium")
        running = ui.label().classes("text-white/90 text-sm")

    def refresh_header():
        r = record_page.STATE["recording"]
        recording.visible = r is not None
        if r:
            s = int(r.seconds)
            recording.set_text(_("● Recording {time}", time=f"{s // 60}:{s % 60:02d}"))
        n = len(jobs.running_audio())
        running.visible = n > 0
        running.set_text(_n("{n} transcription running", "{n} transcriptions running", n))

    ui.timer(1.0, refresh_header)
    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
        yield


def title(text, subtitle=None):
    ui.label(text).classes("text-2xl font-semibold")
    if subtitle:
        ui.label(subtitle).classes("soft-text -mt-3")


# ── Audio clips ──────────────────────────────────────────────────────────────
# The web never gets paths: each clip shown is registered here under a random
# token, and /clip/<token> only serves what's registered.

_CLIPS = {}
_MAX_CLIPS = 5000


def player(origin):
    """ui.audio for {"audio", "start", "end"}, or a note if it can't be played."""
    if not origin:
        return ui.label(_("No source audio saved")).classes("text-sm soft-text")
    if not Path(origin["audio"]).exists():
        return ui.label(_("{name} not found", name=Path(origin["audio"]).name)).classes("text-sm soft-text")
    if len(_CLIPS) > _MAX_CLIPS:
        _CLIPS.clear()
    token = secrets.token_urlsafe(16)
    _CLIPS[token] = (origin["audio"], float(origin["start"]), float(origin["end"]))
    return ui.audio(f"/clip/{token}").props("preload=none").classes("w-full max-w-sm h-10")


def _wav_of(path, start, end):
    data, sr = audio_util.read_clip(path, start, end)
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@app.get("/clip/{token}")
async def _serve_clip(token: str):
    if token not in _CLIPS:
        return Response(status_code=404)
    data = await run.io_bound(_wav_of, *_CLIPS[token])
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# ── Project and folders ──────────────────────────────────────────────────────

def project_selector(on_change):
    """Project select that can also create a new one. Calls on_change(name)."""
    projects = config.list_projects()
    last = config.load_state().get("last_project")
    value = last if last in projects else (projects[0] if projects else None)

    def change(e):
        if e.value:
            config.create_project(e.value)  # does nothing if it exists
            config.update_state(last_project=e.value)
            on_change(e.value)

    select = ui.select(projects, label=_("Project"), value=value, with_input=True, new_value_mode="add-unique",
                       on_change=change).classes("min-w-48")
    select.tooltip(_("Pick one, or type a new name and press Enter to create it"))
    return select


def project_dir(project):
    return config.project_dir(project) or str(Path.home())


def _roots():
    if os.name == "nt":
        import psutil
        return [p.mountpoint for p in psutil.disk_partitions()]
    return ["/"]


async def choose_path(initial, folders=True, extensions=(".wav", ".opus", ".flac", ".ogg")):
    """Browser of the PC's folders (the browser can't pick them itself).
    With folders=False it also shows audio files. Returns the path or None."""
    current = {"path": Path(initial).expanduser() if initial else Path.home()}
    if not current["path"].is_dir():
        current["path"] = Path.home()

    with ui.dialog() as dialog, ui.card().classes("w-[36rem] max-w-full"):
        path_label = ui.label().classes("font-mono text-sm break-all")
        listing = ui.list().props("dense separator").classes("w-full h-80 overflow-auto")
        with ui.row().classes("w-full justify-end"):
            ui.button(_("Cancel"), on_click=lambda: dialog.submit(None)).props("flat")
            if folders:
                ui.button(_("Choose this folder"), on_click=lambda: dialog.submit(current["path"]))

    def draw():
        path = current["path"]
        path_label.set_text(str(path))
        listing.clear()
        try:
            children = sorted((p for p in path.iterdir() if not p.name.startswith(".")), key=lambda p: p.name.lower())
        except OSError:
            children = []
        with listing:
            if path.parent != path:
                _item("..", "arrow_upward", lambda: go(path.parent))
            elif os.name == "nt":
                for root in _roots():
                    _item(root, "storage", lambda r=root: go(Path(r)))
            for p in children:
                if p.is_dir():
                    _item(p.name, "folder", lambda p=p: go(p))
                elif not folders and p.suffix.lower() in extensions:
                    _item(p.name, "audio_file", lambda p=p: dialog.submit(p))

    def go(path):
        current["path"] = path
        draw()

    draw()
    return await dialog


def _item(text, icon, action):
    with ui.item(on_click=action).props("clickable"):
        with ui.item_section().props("avatar"):
            ui.icon(icon, color="grey-7")
        ui.item_section(text)


async def confirm(question):
    with ui.dialog() as d, ui.card():
        ui.label(question)
        with ui.row().classes("w-full justify-end"):
            ui.button(_("Cancel"), on_click=lambda: d.submit(False)).props("flat")
            ui.button(_("Yes"), color="negative", on_click=lambda: d.submit(True))
    return await d


# ── Transcribe ───────────────────────────────────────────────────────────────

async def transcribe_dialog(audio, project):
    """Asks engine/language/model and starts the transcription in the
    background. Returns True if it started."""
    local = local_available()
    dur = await run.io_bound(audio_util.duration, audio)
    with ui.dialog() as dialog, ui.card().classes("w-[30rem] max-w-full gap-3"):
        ui.label(Path(audio).name).classes("text-lg font-medium break-all")
        if dur:
            ui.label(_("{duration} of audio · project {project}", duration=jobs.format_minutes(dur),
                       project=project)).classes("soft-text")
        engine = ui.toggle({"cloud": _("In the cloud"), "local": _("On this PC")}, value="cloud")
        if not local:
            engine.props("disable")
        explanation = ui.label().classes("text-sm soft-text")
        language = ui.select(translated(LANGUAGES), label=_("Language spoken"), value="auto").classes("w-full")
        model = ui.select(translated(MODELS), label=_("Model"), value="medium").classes("w-full")
        with ui.row().classes("w-full justify-end"):
            ui.button(_("Cancel"), on_click=lambda: dialog.submit(None)).props("flat")
            ui.button(_("Transcribe"), icon="play_arrow", on_click=lambda: dialog.submit(True))

    def explain():
        model.visible = engine.value == "local"
        if engine.value == "cloud":
            text = _("AssemblyAI: a few minutes, ~$0.23 per hour of audio. The audio leaves the PC and is deleted "
                     "there when done.")
        elif dur:
            text = _("Free and the audio never leaves the PC, but slow (~{time} for this audio).",
                     time=jobs.format_minutes(dur * jobs.PROCESS_FACTOR))
        else:
            text = _("Free and the audio never leaves the PC, but slow.")
        if not local:
            text += " " + _("The on-this-PC mode is not installed.")
        explanation.set_text(text)

    engine.on_value_change(explain)
    explain()
    if not await dialog:
        return False
    if key := missing_key(engine.value):
        ui.notify(_("The {key} key is missing: set it in Settings", key=key), type="negative")
        return False
    await run.io_bound(jobs.start, audio, project, engine.value, model.value, language.value)
    ui.notify(_("Transcribing {name} in the background", name=Path(audio).name), type="positive")
    return True
