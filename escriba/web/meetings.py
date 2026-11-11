"""Meetings: everything recorded in the current project's folder, its state,
listening to it, reading its transcript and deleting it (for instance a test)."""
from nicegui import run, ui

from .. import jobs, meetings, voiceprints
from ..i18n import N_, _, _n
from .common import file_player, frame, no_project, project_dir, title, transcribe_dialog

STATUS = {  # text, color, icon
    "recording": (N_("Recording"), "negative", "fiber_manual_record"),
    "transcribing": (N_("Transcribing"), "primary", "autorenew"),
    "untranscribed": (N_("Not transcribed"), "grey-7", "hourglass_empty"),
    "to_review": (N_("Speakers to review"), "orange", "record_voice_over"),
    "reviewed": (N_("Reviewed"), "positive", "task_alt"),
}
FILTERS = {"all": N_("All"), "untranscribed": N_("Not transcribed"), "to_review": N_("To review"),
           "reviewed": N_("Reviewed")}


@ui.page("/meetings")
def page():
    from .record import STATE

    with frame("/meetings") as project:
        title(_("Meetings"), _("What's recorded in the project's folder.") if project else None)
        if not project:
            no_project()
            return
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("folder", color="primary")
            ui.label(project_dir(project)).classes("font-mono text-sm break-all")
            ui.space()
            shown = ui.toggle({key: _(text) for key, text in FILTERS.items()}, value="all",
                              on_change=lambda: draw()).props("no-caps rounded unelevated")
        listing = ui.column().classes("w-full gap-2")

    found = []

    async def load():
        listing.clear()
        with listing:
            ui.spinner(size="lg")
        recording = STATE["recording"].target if STATE["recording"] else None
        found[:] = await run.io_bound(meetings.list_meetings, project_dir(project), recording)
        counts = {key: sum(1 for m in found if key == "all" or m["status"] == key) for key in FILTERS}
        shown.set_options({key: f"{_(text)} ({counts[key]})" for key, text in FILTERS.items()}, value=shown.value)
        draw()

    def draw():
        listing.clear()
        chosen = [m for m in found if shown.value == "all" or m["status"] == shown.value]
        with listing:
            if not chosen:
                with ui.card().classes("w-full"):
                    ui.label(_("No meetings here.")).classes("soft-text")
            for m in chosen:
                _row(m)

    def _row(m):
        text, color, icon = STATUS[m["status"]]
        audio = m["audio"]
        with ui.card().classes("w-full gap-2 py-3"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon(icon, color=color, size="sm")
                with ui.column().classes("grow gap-0 min-w-0"):
                    ui.label(audio.stem).classes("font-medium break-all")
                    meta = [m["date"].strftime("%Y-%m-%d %H:%M")]
                    if m["duration"]:
                        meta.append(jobs.format_minutes(m["duration"]))
                    if m["archived"]:
                        meta.append(_("archived (Opus)"))
                    ui.label(" · ".join(meta)).classes("text-sm soft-text")
                ui.badge(_(text), color=color).props("rounded")
                busy = m["status"] in ("recording", "transcribing")
                with ui.button(icon="more_vert").props("flat round dense"):
                    with ui.menu():
                        if m["status"] == "untranscribed":
                            ui.menu_item(_("Transcribe"), on_click=lambda: transcribe(audio))
                        if m["status"] == "to_review":
                            ui.menu_item(_("Review speakers"), on_click=lambda: ui.navigate.to("/review"))
                        if audio.with_suffix(".txt").exists():
                            ui.menu_item(_("See transcript"), on_click=lambda: show_transcript(audio))
                        item = ui.menu_item(_("Delete..."), on_click=lambda: delete(audio))
                        if busy:
                            item.disable()
            if m["status"] != "recording":
                file_player(audio, m["duration"])

    async def transcribe(audio):
        if await transcribe_dialog(audio, project):
            await load()

    def show_transcript(audio):
        text = audio.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
        with ui.dialog() as d, ui.card().classes("w-[48rem] max-w-full"):
            ui.label(audio.stem).classes("text-lg font-medium break-all")
            ui.label(text).classes("whitespace-pre-wrap text-sm max-h-[60vh] overflow-auto")
            ui.button(_("Close"), on_click=d.close).props("flat")
        d.open()

    async def delete(audio):
        files = meetings.files_of(audio)
        samples = await run.io_bound(voiceprints.samples_from_audio, audio)
        n_samples = sum(samples.values())
        with ui.dialog() as d, ui.card().classes("w-[30rem] max-w-full gap-2"):
            ui.label(_("Delete {name}?", name=audio.stem)).classes("text-lg font-medium break-all")
            ui.label(_("These files will be deleted:")).classes("soft-text")
            for f in files:
                ui.label("· " + f.name).classes("font-mono text-sm break-all")
            with_samples = None
            if n_samples:
                ui.label(_n("{n} voice sample was taken from this meeting.",
                            "{n} voice samples were taken from this meeting.", n_samples)).classes("mt-2")
                with_samples = ui.checkbox(_("Delete them too (otherwise they stay, but can't be played)"),
                                           value=False)
            with ui.row().classes("w-full justify-end"):
                ui.button(_("Cancel"), on_click=lambda: d.submit(False)).props("flat")
                ui.button(_("Delete"), icon="delete", color="negative", on_click=lambda: d.submit(True))
        if not await d:
            return
        n_files, n_deleted = await run.io_bound(meetings.delete, audio, bool(with_samples and with_samples.value))
        text = _n("{n} file deleted", "{n} files deleted", n_files)
        if n_deleted:
            text += " · " + _n("{n} sample deleted (can be undone in People)",
                               "{n} samples deleted (can be undone in People)", n_deleted)
        ui.notify(text, type="positive")
        await load()

    ui.timer(0.1, load, once=True)

