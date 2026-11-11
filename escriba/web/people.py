"""People: each project's voice library, its audit and samples added by hand."""
from pathlib import Path

from nicegui import run, ui

from .. import repair, review, voiceprints
from ..i18n import N_, _, _n
from .common import choose_path, confirm, frame, no_project, player, project_dir

EXPLANATION = {
    "confusion": N_("Two people with very similar samples: risk of mixing them up. Listen to both: if a sample "
                    "is under the wrong person, click its name and change it; if it's bad (noise, two voices), "
                    "delete it."),
    "duplicate": N_("Two almost identical samples of the same person: you can delete one."),
    "spread": N_("Two samples of the same person that don't look alike: one may be someone else. Listen to both "
                 "and, if so, click its name and change it."),
}
KIND = {"confusion": N_("Possible confusion"), "duplicate": N_("Almost duplicate samples"),
        "spread": N_("Spread-out samples")}


def _label(sample):
    origin = sample.get("origin")
    if not origin:
        return _("no source audio")
    return f"{Path(origin['audio']).name} · {origin['start']:.0f}-{origin['end']:.0f} s"


@ui.page("/people")
def page():
    with frame("/people") as current:
        ui.label(_("People")).classes("text-2xl font-semibold")
        if not current:
            no_project()
            return
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(_("Voices of {project}", project=current)).classes("soft-text")
            ui.space()
            ui.button(_("Add a sample by hand"), icon="add", on_click=lambda: add()).props("flat no-caps")
            ui.button(_("Undo the last change"), icon="undo", on_click=lambda: undo()).props("flat no-caps")
            ui.button(_("Repair paths"), icon="build", on_click=lambda: repair_paths()).props("flat no-caps") \
                .tooltip(_("If you moved meetings to another folder, finds their audio so it can be played again"))
        with ui.tabs().classes("w-full") as tabs:
            ui.tab("people", label=_("People"), icon="groups")
            audit_tab = ui.tab("audit", label=_("Audit"), icon="fact_check")
        with ui.tab_panels(tabs, value="people").classes("w-full"):
            with ui.tab_panel("people"):
                people = ui.column().classes("w-full gap-2")
            with ui.tab_panel("audit"):
                audit = ui.column().classes("w-full gap-3")


    skipped = set()  # findings dismissed during this visit

    async def reload():
        p = current
        data, findings = await run.io_bound(lambda: (voiceprints.load_samples(p), voiceprints.audit_library(p)))
        draw_people(p, data)
        draw_audit(p, findings, data)

    def draw_people(p, data):
        people.clear()
        with people:
            if not data:
                ui.label(_("This project has no voices yet. They're added when reviewing speakers.")) \
                    .classes("soft-text")
            for name, samples in sorted(data.items(), key=lambda x: x[0].lower()):
                with ui.expansion(_n("{name} ({n} sample)", "{name} ({n} samples)", len(samples), name=name),
                                  icon="person").classes("w-full"):
                    for s in samples:
                        with ui.row().classes("w-full items-center gap-2 py-1 line-below"):
                            ui.label(_label(s)).classes("text-sm grow break-all")
                            player(s.get("origin"))
                            _sample_actions(p, name, s["id"], data)
                    with ui.row().classes("gap-1 pt-1"):
                        ui.button(_("Rename"), icon="edit",
                                  on_click=lambda n=name: rename(p, n, data)).props("flat no-caps")
                        ui.button(_("Delete the whole of {name}", name=name), icon="delete", color="negative",
                                  on_click=lambda n=name: delete_person(p, n)).props("flat no-caps")

    def draw_audit(p, findings, data):
        todo = voiceprints.most_urgent_first(
            [f for f in findings if (f["kind"], f["id_a"], f["id_b"]) not in skipped])
        audit_tab.props(f'label="{_("Audit")} ({len(todo)})"' if todo else f'label="{_("Audit")}"')
        audit.clear()
        with audit:
            if not todo:
                ui.label(_("No pending findings.")).classes("soft-text")
            for f in todo[:20]:
                _finding_card(p, f, data)
            if len(todo) > 20:
                ui.label(_("And {n} more: they show up as you resolve these.", n=len(todo) - 20)).classes("soft-text")

    def _finding_card(p, f, data):
        color = "negative" if f["kind"] == "confusion" and f["similarity"] >= voiceprints.DEFAULT_THRESHOLD \
            else "orange"
        with ui.card().classes("w-full gap-3"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.badge(_(KIND[f["kind"]]), color=color)
                ui.label(_("likeness {similarity:.2f}", similarity=f["similarity"])).classes("soft-text")
            ui.label(_(EXPLANATION[f["kind"]])).classes("text-sm soft-text")
            for side, other in (("a", "b"), ("b", "a")):
                name, sample_id = f[f"name_{side}"], f[f"id_{side}"]
                sample = next((s for s in data.get(name, []) if s["id"] == sample_id), None)
                # In a confusion the likely fix is giving the sample the other name: it's suggested
                suggestion = f[f"name_{other}"] if f["kind"] == "confusion" else ""
                with ui.row().classes("w-full items-center gap-3 py-1 line-below no-wrap"):
                    ui.button(name, icon="edit",
                              on_click=lambda n=name, i=sample_id, sg=suggestion: move(p, n, i, data, sg)) \
                        .props("outline no-caps dense").classes("px-2 shrink-0") \
                        .tooltip(_("Whose voice is this? Change the name of this sample"))
                    if sample:
                        player(sample.get("origin"))
                        ui.space()
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda n=name, i=sample_id: delete_sample(p, n, i)) \
                            .props("flat round dense").tooltip(_("Delete this sample"))
            with ui.row().classes("gap-2"):
                ui.button(_("It's fine like this"), icon="done", on_click=lambda: mark_ok(p, f)) \
                    .props("unelevated no-caps").tooltip(_("Don't flag this case again"))
                ui.button(_("Dismiss for now"), icon="close", on_click=lambda: skip(f)).props("flat no-caps") \
                    .tooltip(_("It shows up again next time"))

    def _sample_actions(p, name, sample_id, data):
        with ui.button(icon="more_vert").props("flat round dense"):
            with ui.menu():
                ui.menu_item(_("It's someone else's..."), on_click=lambda: move(p, name, sample_id, data))
                ui.menu_item(_("Delete this sample"), on_click=lambda: delete_sample(p, name, sample_id))

    async def move(p, name, sample_id, data, suggestion=""):
        with ui.dialog() as d, ui.card().classes("w-96 max-w-full"):
            ui.label(_("This sample is under {name}. Whose is it?", name=name))
            new = ui.input(_("Person"), value=suggestion, autocomplete=sorted(data)).classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button(_("Cancel"), on_click=lambda: d.submit(None)).props("flat")
                ui.button(_("Move"), on_click=lambda: d.submit((new.value or "").strip()))
        await move_to(p, name, sample_id, await d)

    async def move_to(p, name, sample_id, target):
        if target and target != name:
            await run.io_bound(voiceprints.move_sample, p, name, sample_id, target)
            ui.notify(_("Moved to {name}", name=target), type="positive")
            await reload()

    async def rename(p, name, data):
        with ui.dialog() as d, ui.card().classes("w-96 max-w-full"):
            ui.label(_("New name for {name}", name=name)).classes("font-medium")
            new = ui.input(_("Name"), value=name, autocomplete=sorted(data)).classes("w-full")
            merge = ui.label().classes("text-sm text-orange-9")
            everywhere = ui.checkbox(_("Also change it in this project's transcripts"), value=True)
            new.on_value_change(lambda e: merge.set_text(
                _("{name} already exists: their samples will be joined (same person).", name=e.value.strip())
                if e.value and e.value.strip() != name and e.value.strip() in data else ""))
            with ui.row().classes("w-full justify-end"):
                ui.button(_("Cancel"), on_click=lambda: d.submit(None)).props("flat")
                ui.button(_("Rename"), on_click=lambda: d.submit((new.value or "").strip()))
        target = await d
        if not target or target == name:
            return
        await run.io_bound(voiceprints.rename_person, p, name, target)
        text = _("{old} is now {new}", old=name, new=target)
        if everywhere.value:
            n = await run.io_bound(review.rename_in_transcripts, p, name, target)
            if n:
                text += " · " + _n("changed in {n} meeting", "changed in {n} meetings", n)
        ui.notify(text, type="positive")
        await reload()

    async def delete_sample(p, name, sample_id):
        await run.io_bound(voiceprints.delete_sample, p, name, sample_id)
        ui.notify(_("Sample deleted (can be undone)"), type="positive")
        await reload()

    async def delete_person(p, name):
        if await confirm(_("Delete {name} and all their samples?", name=name)):
            await run.io_bound(voiceprints.delete_person, p, name)
            ui.notify(_("{name} deleted (can be undone)", name=name), type="positive")
            await reload()

    async def skip(f):
        skipped.add((f["kind"], f["id_a"], f["id_b"]))
        await reload()

    async def mark_ok(p, f):
        await run.io_bound(voiceprints.mark_as_ok, p, f["kind"], f["id_a"], f["id_b"])
        await reload()

    async def undo():
        if not current:
            return
        if not voiceprints.has_backup(current):
            ui.notify(_("Nothing to undo yet"), type="info")
            return
        if await confirm(_("This undoes the last delete or change of person (one step back only). Go on?")):
            await run.io_bound(voiceprints.restore_backup, current)
            ui.notify(_("Undone"), type="positive")
            await reload()

    async def repair_paths():
        r = await run.io_bound(repair.repair)
        refs = sum(n for _old, _new, n in r["fixed"])
        if not any(r.values()):
            ui.notify(_("Every sample points at an audio file that exists"), type="positive")
        else:
            parts = [_n("{n} audio file found", "{n} audio files found", len(r["fixed"]))
                     + " " + _n("({n} reference fixed)", "({n} references fixed)", refs)]
            if r["not_found"]:
                parts.append(_n("{n} not found", "{n} not found", len(r["not_found"])))
            if r["ambiguous"]:
                parts.append(_n("{n} with several candidates (left alone)", "{n} with several candidates (left alone)",
                                len(r["ambiguous"])))
            ui.notify(", ".join(parts), type="positive" if r["fixed"] else "warning", multi_line=True)
        await reload()

    async def add():
        if not current:
            return
        path = await choose_path(project_dir(current), folders=False)
        if not path:
            return
        with ui.dialog() as d, ui.card().classes("w-96 max-w-full"):
            ui.label(path.name).classes("font-medium break-all")
            with ui.row().classes("w-full"):
                start = ui.number(_("From (s)"), min=0, value=0).classes("w-24")
                end = ui.number(_("To (s)"), min=0, value=10).classes("w-24")
            name = ui.input(_("Person"), autocomplete=sorted(voiceprints.load_library(current))) \
                .classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button(_("Cancel"), on_click=lambda: d.submit(False)).props("flat")
                ui.button(_("Add"), on_click=lambda: d.submit(True))
        if not await d or not (name.value or "").strip():
            return
        begin, finish = float(start.value or 0), float(end.value or 0)
        if finish <= begin:
            ui.notify(_("The end must come after the start"), type="warning")
            return
        try:
            n, added = await run.io_bound(review.enroll, path, begin, finish, name.value.strip(), current)
        except Exception as e:
            ui.notify(_("Can't add it: {error}", error=e), type="negative", multi_line=True)
            return
        text = _n("{name}: {n} sample", "{name}: {n} samples", n, name=name.value)
        if not added:
            text += " " + _("(there was already an almost identical one)")
        ui.notify(text, type="positive")
        await reload()

    ui.timer(0.1, reload, once=True)
