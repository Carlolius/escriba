"""Review speakers: confirm, correct or skip each voice of a transcript."""
from nicegui import run, ui

from .. import review
from ..i18n import _, _n
from .common import frame, player, title


@ui.page("/review")
def page():
    with frame("/review"):
        content = ui.column().classes("w-full gap-4")

    async def listing():
        content.clear()
        with content:
            title(_("Review speakers"), _("Confirming or correcting each voice teaches escriba to recognise it "
                                          "next time."))
            loading = ui.spinner()
        todo = await run.io_bound(review.pending)
        loading.delete()
        with content:
            if not todo:
                ui.label(_("No transcripts waiting for review.")).classes("soft-text")
            with ui.list().props("bordered separator").classes("w-full"):
                for project, sidecar in todo:
                    with ui.item(on_click=lambda p=project, s=sidecar: meeting(p, s)).props("clickable"):
                        with ui.item_section():
                            ui.item_label(review.meeting_name(sidecar))
                            ui.item_label(project).props("caption")
                        with ui.item_section().props("side"):
                            ui.icon("chevron_right")

    async def meeting(project, sidecar):
        content.clear()
        with content:
            with ui.row().classes("items-center gap-2"):
                ui.button(icon="arrow_back", on_click=listing).props("flat round")
                ui.label(review.meeting_name(sidecar)).classes("text-xl font-semibold break-all")
                ui.badge(project).props("outline")
            transcript = ui.expansion(_("See transcript"), icon="article").classes("w-full")
            speakers = ui.column().classes("w-full gap-3")
        data = await run.io_bound(_load, sidecar, project)

        def draw_transcript():
            transcript.clear()
            txt = review.txt_path(sidecar)
            with transcript:
                text = txt.read_text(encoding="utf-8") if txt.exists() else _("(no transcript)")
                ui.label(text).classes("whitespace-pre-wrap text-sm max-h-96 overflow-auto")

        def draw():
            speakers.clear()
            sidecar_data = review.load(sidecar)
            with speakers:
                for spk, info in sidecar_data["clusters"].items():
                    _card(spk, info, data["quotes"].get(spk, []), data["known"], decide)
                if sidecar_data.get("reviewed"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("task_alt", color="positive", size="md")
                        ui.label(_("Meeting reviewed")).classes("text-lg")
                        ui.button(_("Back to the list"), on_click=listing).props("flat no-caps")

        async def decide(spk, name):
            r = await run.io_bound(review.decide, sidecar, spk, name, project)
            if name:
                if name not in data["known"]:
                    data["known"].append(name)
                text = _n("{name}: {n} sample", "{name}: {n} samples", r["samples"], name=name)
                if r["renamed"]:
                    text += ", " + _n("renamed in {n} place", "renamed in {n} places", r["renamed"])
                ui.notify(text, type="positive")
            draw()
            if r["renamed"]:
                draw_transcript()
            if r["complete"]:
                # The button that triggered this no longer exists (draw() rebuilds
                # the cards): the notification hangs from something still on the page
                with content:
                    await _archive(sidecar)

        draw_transcript()
        draw()

    ui.timer(0.1, listing, once=True)


def _load(sidecar, project):
    return {"quotes": review.quotes_by_cluster(sidecar), "known": review.known_names(sidecar, project)}


async def _archive(sidecar):
    note = ui.notification(_("Compressing the audio to Opus to archive it..."), spinner=True, timeout=None)
    try:
        result = await run.io_bound(review.archive_if_complete, sidecar)
    except Exception as e:  # the WAV stays as it is if something fails
        note.message, note.type = _("Couldn't compress it: {error}", error=e), "warning"
    else:
        note.message = _("Audio archived ({mb:.0f} MB less)", mb=result[1] / 1e6) if result else _("Done")
        note.type = "positive"
    note.spinner = False
    note.timeout = 4


def _card(spk, info, quotes, known, decide):
    reviewed = info.get("reviewed")
    unnamed = info.get("unnamed")
    with ui.card().classes("w-full gap-2" + (" opacity-60" if reviewed else "")):
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(info["name"]).classes("text-lg font-medium")
            if reviewed:
                ui.badge(_("reviewed"), color="positive")
            elif unnamed:
                ui.badge(_("not identified"), color="orange")
            ui.space()
            sim = info.get("similarity")
            detail = _("{seconds:.0f} s of speech", seconds=info["speech_seconds"])
            if sim is not None:
                detail += " · " + _("likeness {similarity:.2f}", similarity=sim)
            ui.label(detail).classes("text-sm soft-text")
        for quote in quotes or [_("(no long sentences of theirs in the transcript)")]:
            ui.label(f"«{quote}»").classes("italic soft-text")
        player(info.get("origin"))
        if reviewed:
            return
        with ui.row().classes("w-full items-end gap-2"):
            name = ui.input(_("Who is it?"), value="" if unnamed else info["name"], autocomplete=known) \
                .classes("grow")
            name.on("keydown.enter", lambda: confirm())
            ui.button(_("Confirm"), icon="check", on_click=lambda: confirm())
            ui.button(_("I don't know"), on_click=lambda: decide(spk, "")).props("flat no-caps") \
                .tooltip(_("Marked as reviewed without saving anything in the voice library"))

    async def confirm():
        value = (name.value or "").strip()
        if not value:
            ui.notify(_("Type who it is, or press «I don't know»"), type="warning")
            return
        await decide(spk, value)
