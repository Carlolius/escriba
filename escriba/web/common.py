"""Pieces shared by every page: the frame (header and navigation), audio clips,
the folder browser and the transcribe dialog."""
import html
import io
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

import soundfile as sf
from fastapi import Request, Response
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from .. import audio as audio_util
from .. import config, jobs
from ..i18n import N_, _, _n
from ..paths import shown_path  # noqa: F401  (the pages import it from here)
from ..transcribe import local_available, missing_key

SECTIONS = [
    ("/", N_("Record"), "mic"),
    ("/meetings", N_("Meetings"), "library_music"),
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

STATIC = Path(__file__).parent / "static"
LOGO = STATIC / "logo.svg"
COLORS = {"primary": "#4f46e5", "secondary": "#f59e0b", "accent": "#0ea5e9",
          "positive": "#16a34a", "negative": "#dc2626", "warning": "#f59e0b", "info": "#0ea5e9"}
CSS = """
:root { --escriba-bg: #f1f2fb; --escriba-card: #ffffff; --escriba-soft: #4b5563; --escriba-line: #e4e6f2; }
body.body--dark { --escriba-bg: #0e0f1d; --escriba-card: #1a1b2f; --escriba-soft: #aab0c6; --escriba-line: #2c2e48; }
body { background: var(--escriba-bg) !important; }
.q-card { background: var(--escriba-card); border-radius: 14px; box-shadow: 0 1px 3px rgb(30 27 75 / 0.08),
          0 6px 20px -8px rgb(30 27 75 / 0.12); }
body.body--dark .q-card { box-shadow: 0 1px 3px rgb(0 0 0 / 0.5); }
.soft-text { color: var(--escriba-soft); }
.q-tab-panels, .q-tab-panel { background: transparent !important; }
.q-tab-panel { padding: 8px 0; }
.line-below { border-bottom: 1px solid var(--escriba-line); }
.escriba-header { background: linear-gradient(100deg, #1e1b4b 0%, #312e81 45%, #4f46e5 100%); }
.escriba-header .q-field__native, .escriba-header .q-field__input { color: white; }
/* In dark mode indigo can't be read on black: lighter primary, dark text on filled buttons */
body.body--dark { --q-primary: #a5b4fc !important; }  /* NiceGUI sets it inline on <body> */
body.body--dark .q-btn.bg-primary { color: #1e1b4b !important; }
.escriba-player { display: inline-flex; align-items: center; gap: 8px; min-width: 12rem; }
.escriba-player button { border: 0; border-radius: 999px; width: 30px; height: 30px; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--q-primary); color: white; flex: none; }
body.body--dark .escriba-player button { color: #1e1b4b; }
.escriba-player .track { flex: 1; height: 6px; border-radius: 3px; background: var(--escriba-line);
  cursor: pointer; overflow: hidden; min-width: 5rem; }
.escriba-player .bar { height: 100%; width: 0; background: var(--q-primary); border-radius: 3px; }
.escriba-player .time { font-variant-numeric: tabular-nums; font-size: 12px; color: var(--escriba-soft);
  white-space: nowrap; }
"""
# The players are plain HTML: they work in the browser alone, without a round
# trip to the server for every tick of playback.
PLAYER_JS = """
<script>
window.escribaFmt = s => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
window.escribaAudio = el => el.closest('.escriba-player').querySelector('audio');
window.escribaPlay = function (button) {
  const box = button.closest('.escriba-player'), audio = escribaAudio(button);
  document.querySelectorAll('.escriba-player audio').forEach(a => { if (a !== audio) a.pause(); });
  if (!audio.dataset.ready) {
    audio.dataset.ready = '1';
    const bar = box.querySelector('.bar'), time = box.querySelector('.time'), icon = button.querySelector('i');
    const total = parseFloat(box.dataset.duration) || 0;
    audio.addEventListener('timeupdate', () => {
      const length = audio.duration && isFinite(audio.duration) ? audio.duration : total;
      if (length) bar.style.width = (100 * audio.currentTime / length) + '%';
      time.textContent = escribaFmt(audio.currentTime) + ' / ' + escribaFmt(length);
    });
    audio.addEventListener('play', () => icon.textContent = 'pause');
    audio.addEventListener('pause', () => icon.textContent = 'play_arrow');
    audio.addEventListener('ended', () => { bar.style.width = '0'; time.textContent = escribaFmt(total); });
  }
  audio.paused ? audio.play() : audio.pause();
};
window.escribaSeek = function (event, track) {
  const box = track.closest('.escriba-player'), audio = escribaAudio(track);
  const length = audio.duration && isFinite(audio.duration) ? audio.duration : parseFloat(box.dataset.duration);
  const r = track.getBoundingClientRect();
  if (audio.paused) escribaPlay(box.querySelector('button'));
  audio.currentTime = length * (event.clientX - r.left) / r.width;
};
</script>
"""
THEMES = {"light": False, "dark": True}  # anything else (system) = None: follow the system


def current_project():
    """The project chosen in the top bar (the last one used), or None if
    there are none yet."""
    projects = config.list_projects()
    last = config.load_state().get("last_project")
    return last if last in projects else (projects[0] if projects else None)


def set_project(name):
    config.create_project(name)  # does nothing if it exists
    config.update_state(last_project=name)


@contextmanager
def frame(current_path):
    """Header with the logo, navigation, project and status (recording,
    running transcriptions); what's inside the with goes to the central
    column. Returns the current project."""
    from . import record as record_page

    ui.page_title("Escriba")
    ui.dark_mode(THEMES.get(config.load_state().get("theme")))
    ui.add_css(CSS)
    ui.add_head_html(PLAYER_JS)
    project = current_project()
    with ui.header().classes("escriba-header items-center flex-nowrap gap-1 px-4 py-2 shadow-md"):
        with ui.link(target="/").classes("flex items-center gap-2 mr-3 no-underline text-white"):
            ui.image("/static/logo.svg").classes("w-8 h-8")
            ui.label("Escriba").classes("text-lg font-semibold tracking-wide max-sm:hidden")
        for path, text, icon in SECTIONS:
            with ui.button(icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props("flat no-caps") \
                    .classes("text-white rounded-lg" + (" bg-white/20" if path == current_path else "")):
                ui.label(_(text)).classes("ml-2 max-lg:hidden")
                ui.tooltip(_(text)).classes("lg:hidden")
        ui.space()
        with ui.link(target="/").classes("no-underline mr-2") as recording:
            with ui.row().classes("items-center gap-1 text-white font-medium no-wrap"):
                ui.icon("fiber_manual_record", color="red-5").classes("animate-pulse")
                recording_text = ui.label()
                recording_tip = ui.tooltip()
        with ui.link(target="/transcribe").classes("no-underline mr-2") as running:
            with ui.row().classes("items-center gap-1 text-white text-sm no-wrap"):
                ui.icon("sync").classes("animate-spin")
                running_text = ui.label()
                running_tip = ui.tooltip()
        projects = config.list_projects()
        select = ui.select(projects, value=project, with_input=True, new_value_mode="add-unique",
                           on_change=lambda e: _change_project(e.value)) \
            .props('dense outlined dark color="white" options-dense hide-bottom-space') \
            .classes("w-44 shrink-0")
        with select.add_slot("prepend"):
            ui.icon("folder_special", color="white", size="xs")
        select.tooltip(_("Project. Pick one, or type a new name and press Enter to create it"))

    def refresh_header():
        r = record_page.STATE["recording"]
        recording.visible = r is not None
        if r:
            s = int(r.seconds)
            recording_text.set_text(f"{s // 60}:{s % 60:02d}")
            recording_tip.set_text(_("Recording"))
        n = len(jobs.running_audio())
        running.visible = n > 0
        running_text.set_text(str(n))
        running_tip.set_text(_n("{n} transcription running", "{n} transcriptions running", n))

    refresh_header()
    ui.timer(1.0, refresh_header)
    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
        yield project


def _change_project(name):
    if name and name != config.load_state().get("last_project"):
        set_project(name)
        ui.navigate.reload()


def title(text, subtitle=None):
    ui.label(text).classes("text-2xl font-semibold")
    if subtitle:
        ui.label(subtitle).classes("soft-text -mt-3")


def no_project():
    """What a page shows when there isn't any project yet."""
    with ui.card().classes("w-full items-start gap-2"):
        ui.label(_("There are no projects yet")).classes("text-lg font-medium")
        ui.label(_("A project groups the meetings and voices of a client or team. Type a name in the project box "
                   "at the top right and press Enter to create one.")).classes("soft-text")


# ── Audio ────────────────────────────────────────────────────────────────────
# The web never gets paths: each audio shown is registered here under a random
# token, and /clip/<token> only serves what's registered.

_CLIPS = {}
_MAX_CLIPS = 5000


def _register(path, start=None, end=None):
    if len(_CLIPS) > _MAX_CLIPS:
        _CLIPS.clear()
    token = secrets.token_urlsafe(16)
    _CLIPS[token] = (str(path), start, end)
    return f"/clip/{token}"


def _player_html(url, seconds):
    seconds = max(0, int(round(seconds or 0)))
    return (f'<div class="escriba-player" data-duration="{seconds}">'
            f'<audio preload="none" src="{url}"></audio>'
            f'<button type="button" onclick="escribaPlay(this)" title="{html.escape(_("Play"))}">'
            f'<i class="q-icon notranslate material-icons" style="font-size:20px">play_arrow</i></button>'
            f'<div class="track" onclick="escribaSeek(event, this)"><div class="bar"></div></div>'
            f'<span class="time">{seconds // 60}:{seconds % 60:02d}</span></div>')


def player(origin):
    """Compact player for a voice sample {"audio", "start", "end"}, with its
    length shown before playing; or a note if it can't be played."""
    if not origin:
        return ui.label(_("No source audio saved")).classes("text-sm soft-text")
    if not Path(origin["audio"]).exists():
        return ui.label(_("{name} not found", name=Path(origin["audio"]).name)).classes("text-sm soft-text")
    start, end = float(origin["start"]), float(origin["end"])
    return ui.html(_player_html(_register(origin["audio"], start, end), end - start), sanitize=False) \
        .classes("w-full max-w-xs")


def file_player(path, seconds):
    """Player for a whole audio file (served as is, so it can be long)."""
    return ui.html(_player_html(_register(path), seconds), sanitize=False).classes("w-full max-w-xs")


def _wav_of(path, start, end):
    data, sr = audio_util.read_clip(path, start, end)
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _ranged(data, media_type, range_header):
    """Answers the Range requests browsers send to seek."""
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    if range_header and range_header.startswith("bytes="):
        first, _sep, last = range_header[6:].split(",")[0].partition("-")
        try:
            start = int(first) if first else len(data) - int(last)
            end = int(last) if first and last else len(data) - 1
        except ValueError:
            start, end = 0, len(data) - 1
        start, end = max(0, start), min(end, len(data) - 1)
        if start <= end:
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
            return Response(data[start:end + 1], status_code=206, media_type=media_type, headers=headers)
    return Response(data, media_type=media_type, headers=headers)


@app.get("/clip/{token}")
async def _serve_clip(token: str, request: Request):
    if token not in _CLIPS:
        return Response(status_code=404)
    path, start, end = _CLIPS[token]
    if start is None:
        if not Path(path).exists():
            return Response(status_code=404)
        media_type = "audio/ogg" if path.lower().endswith(".opus") else "audio/wav"
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})
    data = await run.io_bound(_wav_of, path, start, end)
    return _ranged(data, "audio/wav", request.headers.get("range"))


# ── Project and folders ──────────────────────────────────────────────────────

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
    from .. import gpu

    local = local_available()
    dur = await run.io_bound(audio_util.duration, audio)
    on_gpu = local and await run.io_bound(gpu.will_try)
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
        elif on_gpu:
            text = _("Free and the audio never leaves the PC. It will use the GPU ({name}, experimental): much "
                     "faster than the CPU, and if it fails it goes on with the CPU.", name=gpu.describe())
        elif dur:
            text = _("Free and the audio never leaves the PC, but slow (~{time} for this audio).",
                     time=jobs.format_minutes(dur * jobs.PROCESS_FACTOR))
        else:
            text = _("Free and the audio never leaves the PC, but slow.")
        if not local:
            text += " " + _("The on-this-PC mode is not installed: you can install it in Settings.")
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
