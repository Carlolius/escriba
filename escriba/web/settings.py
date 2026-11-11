"""Settings: language, keys, recording devices, appearance, glossary and data folder."""
from nicegui import run, ui

from .. import config, i18n, record
from ..i18n import N_, _
from ..transcribe import local_available
from .common import THEMES, frame, title

KEYS = [
    ("ASSEMBLYAI_API_KEY", N_("AssemblyAI key"),
     N_("To transcribe in the cloud. Create it at assemblyai.com (new accounts get $50 of credit).")),
    ("HF_TOKEN", N_("Hugging Face token"),
     N_("To separate speakers on this PC. Create it at hf.co/settings/tokens and accept the conditions of "
        "pyannote/speaker-diarization-3.1 and pyannote/speaker-diarization-community-1.")),
]


@ui.page("/settings")
def page():
    with frame("/settings"):
        title(_("Settings"))

        with ui.card().classes("w-full gap-2"):
            ui.label(_("Language")).classes("text-lg font-medium")
            ui.toggle({"auto": _("Same as the system")} | i18n.LANGUAGES,
                      value=config.load_state().get("language") or "auto",
                      on_change=lambda e: change_language(e.value))

        with ui.card().classes("w-full gap-3"):
            ui.label(_("Keys")).classes("text-lg font-medium")
            for key, name, help_text in KEYS:
                _key_field(key, _(name), _(help_text))
            secrets = config.secrets_path()
            if secrets.is_symlink():
                ui.label(_("They're saved in {path} (secrets.env is a link).", path=secrets.resolve())) \
                    .classes("text-sm soft-text")
            if not local_available():
                ui.label(_("The on-this-PC mode is not installed: you can only transcribe in the cloud.")) \
                    .classes("text-sm soft-text")

        with ui.card().classes("w-full gap-3"):
            ui.label(_("Recording")).classes("text-lg font-medium")
            devices = ui.column().classes("w-full")

        with ui.card().classes("w-full gap-2"):
            ui.label(_("Appearance")).classes("text-lg font-medium")
            ui.toggle({"system": _("Same as the system"), "light": _("Light"), "dark": _("Dark")},
                      value=config.load_state().get("theme", "system"),
                      on_change=lambda e: change_theme(e.value))

        with ui.card().classes("w-full gap-2"):
            ui.label(_("Glossary")).classes("text-lg font-medium")
            ui.label(_("Names of people, companies and terms that come up in your meetings, separated by commas or "
                       "one per line. It helps both modes spell them right.")).classes("text-sm soft-text")
            glossary = ui.textarea(value=config.glossary_path().read_text(encoding="utf-8")) \
                .props("outlined autogrow").classes("w-full font-mono text-sm")
            ui.button(_("Save glossary"), icon="save", on_click=lambda: save_glossary()).classes("self-start")

        with ui.card().classes("w-full gap-1"):
            ui.label(_("Your data")).classes("text-lg font-medium")
            ui.label(_("Voices, glossary, keys and state: {path}", path=config.data_dir())) \
                .classes("font-mono text-sm break-all")
            ui.label(_("Voices are other people's biometric data: don't share them.")).classes("text-sm soft-text")

    def change_language(value):
        config.update_state(language=None if value == "auto" else value)
        i18n.set_language(value)
        ui.navigate.reload()

    def change_theme(value):
        config.update_state(theme=value)
        ui.dark_mode(THEMES.get(value))

    def save_glossary():
        config.glossary_path().write_text(glossary.value, encoding="utf-8")
        ui.notify(_("Glossary saved"), type="positive")

    async def load_devices():
        try:
            found = await run.io_bound(record.list_devices)
        except Exception as e:
            with devices:
                ui.label(_("Can't list the audio devices: {error}", error=e)).classes("text-negative")
            return
        state = config.load_state()
        with devices:
            for key, label, options in (("output_device", _("What plays (output)"), found["outputs"]),
                                        ("mic", _("Microphone"), found["mics"])):
                default = next((n for n, is_default in options if is_default), "")
                # "" = the system one (a None key doesn't survive the trip to the browser)
                choices = {"": _("(the system one): {name}", name=default)} | {n: n for n, _d in options}
                current = state.get(key) if state.get(key) in choices else ""
                ui.select(choices, label=label, value=current,
                          on_change=lambda e, k=key: save_device(k, e.value)).classes("w-full")

    def save_device(key, value):
        config.update_state(**{key: value or None})
        ui.notify(_("Saved: it will be used for the next recording"), type="positive")

    ui.timer(0.1, load_devices, once=True)


def _key_field(key, name, help_text):
    is_set = bool(config.read_secret(key))
    placeholder = _("set (type to change it)")
    with ui.column().classes("w-full gap-1"):
        with ui.row().classes("w-full items-end gap-2"):
            field = ui.input(name, password=True, password_toggle_button=True,
                             placeholder=placeholder if is_set else "").classes("grow")
            badge = ui.badge(_("set") if is_set else _("missing"), color="positive" if is_set else "orange")
            ui.button(_("Save"), on_click=lambda: save()).props("flat")
        ui.label(help_text).classes("text-sm soft-text")

    def save():
        value = (field.value or "").strip()
        if not value:
            ui.notify(_("Type the key before saving"), type="warning")
            return
        config.save_secret(key, value)
        field.set_value("")
        field.props(f'placeholder="{placeholder}"')
        badge.set_text(_("set"))
        badge.props("color=positive")
        ui.notify(_("{name} saved", name=name), type="positive")
