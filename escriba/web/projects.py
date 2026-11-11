"""Projects: create, rename, change the folder of and delete projects. It's
reached from the pencil next to the project box in the top bar."""
from nicegui import run, ui

from .. import config, projects
from ..i18n import _, _n
from .common import choose_path, frame, set_project, shown_path, title


@ui.page("/projects")
def page():
    with frame("/projects"):
        title(_("Projects"), _("Each project has its own folder and its own voice library."))
        with ui.row().classes("w-full"):
            ui.button(_("New project"), icon="add", on_click=lambda: new_project()).props("unelevated")
        listing = ui.column().classes("w-full gap-3")

    def draw():
        listing.clear()
        current = config.load_state().get("last_project")
        with listing:
            found = projects.summary()
            if not found:
                with ui.card().classes("w-full"):
                    ui.label(_("There are no projects yet")).classes("soft-text")
            for p in found:
                _card(p, p["name"] == current)

    def _card(p, is_current):
        name = p["name"]
        with ui.card().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("folder_special", color="primary", size="sm")
                ui.label(name).classes("text-lg font-medium break-all")
                if is_current:
                    ui.badge(_("current"), color="primary").props("rounded")
                ui.space()
                if not is_current:
                    ui.button(_("Use"), on_click=lambda: use(name)).props("flat no-caps")
                with ui.button(icon="more_vert").props("flat round dense"), ui.menu():
                    ui.menu_item(_("Rename..."), on_click=lambda: rename(name))
                    ui.menu_item(_("Change folder..."), on_click=lambda: change_folder(name))
                    ui.menu_item(_("Delete..."), on_click=lambda: delete(p))
            with ui.row().classes("items-center gap-2 text-sm"):
                ui.icon("folder", color="primary")
                ui.label(shown_path(p["folder"]) if p["folder"] else _("No folder chosen yet")) \
                    .classes("font-mono break-all")
            ui.label(_n("{n} person", "{n} people", p["people"]) + " · "
                     + _n("{n} voice sample", "{n} voice samples", p["samples"])).classes("text-sm soft-text")

    def use(name):
        set_project(name)
        ui.navigate.reload()

    async def new_project():
        name = await _ask_name(_("New project"), "")
        if name:
            try:
                set_project(name)
            except ValueError as e:
                ui.notify(str(e), type="warning")
                return
            ui.navigate.reload()

    async def rename(name):
        new = await _ask_name(_("Rename {name}", name=name), name)
        if not new or new == name:
            return
        try:
            n = await run.io_bound(projects.rename, name, new)
        except (ValueError, RuntimeError) as e:
            ui.notify(str(e), type="warning", multi_line=True)
            return
        text = _("{old} is now {new}", old=name, new=new)
        if n:
            text += " · " + _n("changed in {n} meeting", "changed in {n} meetings", n)
        ui.notify(text, type="positive")
        ui.navigate.reload()   # the project box in the top bar too

    async def change_folder(name):
        if path := await choose_path(config.project_dir(name)):
            config.set_project_dir(name, path)
            draw()

    async def delete(p):
        name = p["name"]
        with ui.dialog() as d, ui.card().classes("w-[30rem] max-w-full gap-2"):
            ui.label(_("Delete {name}?", name=name)).classes("text-lg font-medium break-all")
            ui.label(_n("Its voice library is deleted: {n} person and their samples. This can't be undone.",
                        "Its voice library is deleted: {n} people and their samples. This can't be undone.",
                        p["people"]))
            if p["folder"]:
                ui.label(_("The recordings and transcripts in {folder} are kept.",
                           folder=shown_path(p["folder"]))).classes("soft-text break-all")
            with ui.row().classes("w-full justify-end"):
                ui.button(_("Cancel"), on_click=lambda: d.submit(False)).props("flat")
                ui.button(_("Delete"), icon="delete", color="negative", on_click=lambda: d.submit(True))
        if not await d:
            return
        try:
            await run.io_bound(projects.delete, name)
        except RuntimeError as e:
            ui.notify(str(e), type="warning", multi_line=True)
            return
        ui.notify(_("Project {name} deleted", name=name), type="positive")
        ui.navigate.reload()

    draw()


async def _ask_name(heading, value):
    with ui.dialog() as d, ui.card().classes("w-[26rem] max-w-full gap-3"):
        ui.label(heading).classes("text-lg font-medium break-all")
        field = ui.input(_("Name"), value=value).props("outlined autofocus").classes("w-full") \
            .on("keydown.enter", lambda: d.submit(field.value))
        with ui.row().classes("w-full justify-end"):
            ui.button(_("Cancel"), on_click=lambda: d.submit(None)).props("flat")
            ui.button(_("Save"), on_click=lambda: d.submit(field.value)).props("unelevated")
    result = await d
    return (result or "").strip()
