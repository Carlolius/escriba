"""Settings: language, keys, local mode, recording devices, appearance,
glossary and data folder."""
from collections import deque

from nicegui import background_tasks, run, ui

from .. import config, extras, gpu, i18n, record, themes
from ..i18n import N_, _, number
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

        with ui.card().classes("w-full gap-3"):
            ui.label(_("Transcribe on this PC")).classes("text-lg font-medium")
            local_mode = ui.column().classes("w-full gap-2")

        with ui.card().classes("w-full gap-3"):
            ui.label(_("Recording")).classes("text-lg font-medium")
            devices = ui.column().classes("w-full")

        with ui.card().classes("w-full gap-3"):
            ui.label(_("Appearance")).classes("text-lg font-medium")
            ui.toggle({"system": _("Same as the system"), "light": _("Light"), "dark": _("Dark")},
                      value=config.load_state().get("theme", "system"),
                      on_change=lambda e: change_theme(e.value))
            ui.label(_("Colors")).classes("text-sm soft-text")
            current = themes.get(config.load_state().get("colors"))
            with ui.row().classes("w-full gap-2"):
                for key, theme in themes.THEMES.items():
                    _theme_button(key, theme, theme is current)

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

    shown = {"key": None, "log": None}

    def draw_local_mode():
        key = (local_available(), gpu.torch_has_cuda(), INSTALL["running"], INSTALL["ok"])
        if key != shown["key"]:  # redrawn only when the state changes, so nothing blinks
            shown["key"] = key
            local_mode.clear()
            with local_mode:
                shown["log"] = _local_mode()
        if shown["log"]:
            shown["log"].set_text(_log_text())

    async def start_local_mode():
        await run.io_bound(gpu.nvidia)  # runs nvidia-smi once, off the event loop
        draw_local_mode()
        ui.timer(1.0, draw_local_mode)

    ui.timer(0.1, load_devices, once=True)
    ui.timer(0.1, start_local_mode, once=True)


# Installing local mode belongs to the server, not to the tab: it goes on if
# the page is closed
INSTALL = {"running": False, "ok": None, "lines": deque(maxlen=300)}


def _whisper_sizes():
    return ", ".join(f"{model} ~{number(gb)} GB" for model, gb in (("small", 0.5), ("medium", 1.5), ("large-v3", 3)))


def _local_mode():
    """Draws the card's content; returns the log label to keep updating, if any."""
    card = gpu.nvidia()
    usable_card = bool(card and card["driver_ok"])
    installed = local_available()
    if INSTALL["running"]:
        with ui.row().classes("items-center gap-3"):
            ui.spinner(size="md")
            ui.label(_("Installing... it may take a few minutes. You can keep using escriba."))
        return _install_log()

    if installed:
        with ui.row().classes("items-center gap-2"):
            ui.icon("check_circle", color="positive")
            ui.label(_("Installed."))
        ui.label(_("Each whisper model is downloaded the first time you use it ({sizes}).", sizes=_whisper_sizes())) \
            .classes("text-sm soft-text")
        if not config.read_secret("HF_TOKEN"):
            ui.label(_("To separate speakers it also needs the Hugging Face token (above).")) \
                .classes("text-sm text-warning")
    else:
        ui.label(_("Free and the audio never leaves the PC, but slower than the cloud. It's optional: it needs "
                   "~{size} GB of libraries, and then the whisper model the first time ({sizes}).",
                   size=number(extras.SIZE_GB), sizes=_whisper_sizes())).classes("text-sm soft-text")

    log = None
    if INSTALL["ok"] is False:
        ui.label(_("The installation failed. You can also install it by hand:")).classes("text-negative")
        ui.code(extras.manual_command(), language=None).classes("w-full")
        log = _install_log()

    with_gpu = None
    if card:
        with ui.column().classes("w-full gap-1 mt-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("memory", color="primary")
                ui.label(_("Graphics card: {name}", name=card["name"])).classes("font-medium")
                ui.badge(_("experimental"), color="warning").props("rounded outline")
            if not card["driver_ok"]:
                ui.label(_("Its driver ({driver}) is too old to use it: update it to use the GPU.",
                           driver=card["driver"])).classes("text-sm text-warning")
            elif installed and gpu.torch_has_cuda():
                ui.toggle({"auto": _("Use the GPU"), "never": _("CPU only")}, value=gpu.setting(),
                          on_change=lambda e: _save_gpu(e.value))
                ui.label(_("If the GPU fails (old driver, too little memory), it goes on with the CPU and says so "
                           "in the log.")).classes("text-sm soft-text")
            elif installed:
                ui.label(_("Local mode is installed for the CPU. The GPU version is much faster, but takes "
                           "~{size} GB.", size=number(extras.GPU_SIZE_GB))).classes("text-sm soft-text")
            else:
                with_gpu = ui.checkbox(_("Install the GPU version (~{size} GB instead of {cpu}). If it fails, the "
                                         "CPU is used.", size=number(extras.GPU_SIZE_GB),
                                         cpu=number(extras.SIZE_GB)), value=True)

    switch = installed and usable_card and not gpu.torch_has_cuda()
    if installed and not switch:
        return log
    if not extras.find_uv():
        ui.label(_("uv was not found, so it can't be installed from here. Install it by hand:")) \
            .classes("text-warning")
        ui.code(extras.manual_command(), language=None).classes("w-full")
        return log
    free = extras.free_gb()
    if free < (extras.GPU_NEEDED_GB if usable_card else extras.NEEDED_GB):
        ui.label(_("Only {free} GB free on the disk: about {needed} GB are needed.", free=number(free),
                   needed=extras.GPU_NEEDED_GB if usable_card else extras.NEEDED_GB)).classes("text-warning")
    if switch:
        ui.button(_("Switch to the GPU version (~{size} GB)", size=number(extras.GPU_SIZE_GB)), icon="download",
                  on_click=lambda: _start_install(True)).props("unelevated").classes("self-start")
    else:
        ui.button(_("Install"), icon="download",
                  on_click=lambda: _start_install(bool(with_gpu and with_gpu.value))) \
            .props("unelevated").classes("self-start")
    return log


def _save_gpu(value):
    config.update_state(gpu=value)
    ui.notify(_("Saved: it will be used for the next transcription"), type="positive")


def _log_text():
    return "\n".join(list(INSTALL["lines"])[-40:]) or "..."


def _install_log():
    with ui.expansion(_("See what it's doing")).classes("w-full"):
        return ui.label(_log_text()).classes("w-full whitespace-pre-wrap font-mono text-xs max-h-72 overflow-auto")


def _start_install(with_gpu=False):
    if INSTALL["running"]:
        return
    if with_gpu and extras.local_job_running():
        ui.notify(_("A local transcription is running: wait until it ends."), type="warning")
        return
    INSTALL.update(running=True, ok=None)
    INSTALL["lines"].clear()

    async def work():
        try:
            INSTALL["ok"] = await run.io_bound(extras.install, INSTALL["lines"].append, with_gpu)
        except Exception as e:
            INSTALL["lines"].append(str(e))
            INSTALL["ok"] = False
        finally:
            INSTALL["running"] = False

    background_tasks.create(work())


def _key_field(key, name, help_text):
    is_set = bool(config.read_secret(key))
    placeholder = _("set (type to change it)")
    with ui.column().classes("w-full gap-1"):
        with ui.row().classes("w-full items-end gap-2"):
            field = ui.input(name, password=True, password_toggle_button=True,
                             placeholder=placeholder if is_set else "").classes("grow")
            badge = ui.badge(_("set") if is_set else _("missing"), color="positive" if is_set else "warning")
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


def _theme_button(key, theme, chosen):
    """A button with the theme's name and colors (dark variant on the
    left half, light on the right)."""
    def dots(colors):
        return "".join(f'<span style="width:12px;height:12px;border-radius:50%;display:inline-block;'
                       f'background:{colors[c]}"></span>' for c in ("primary", "secondary", "accent"))
    dark, light = theme["dark"], theme["light"]
    sample = (f'<div style="display:flex;border-radius:8px;overflow:hidden;border:1px solid var(--escriba-line)">'
              f'<div style="background:{dark["card"]};padding:6px 8px;display:flex;gap:4px">{dots(dark)}</div>'
              f'<div style="background:{light["card"]};padding:6px 8px;display:flex;gap:4px">{dots(light)}</div>'
              f'</div>')
    with ui.button(on_click=lambda: change_colors(key)).props("flat no-caps") \
            .classes("rounded-xl px-2 py-1" + (" ring-2 ring-[var(--q-primary)]" if chosen else "")):
        with ui.column().classes("items-center gap-1"):
            ui.html(sample, sanitize=False)
            ui.label(theme["name"]).classes("text-sm").style("color: var(--escriba-text)")


def change_colors(key):
    config.update_state(colors=key)
    ui.navigate.reload()
