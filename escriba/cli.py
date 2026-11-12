"""escriba's command line. Without arguments it opens the terminal menu."""
import argparse
import os
import sys
import time
import warnings
from pathlib import Path

from . import config, i18n
from .i18n import N_, _, number

USAGE = N_("""\
  escriba                       terminal menu
  escriba web                   browser interface
  escriba record [NAME]         record a meeting (Ctrl+C to stop)
  escriba transcribe AUDIO      transcribe (and identify speakers)
  escriba archive [DIR ...]     compress what's already reviewed to Opus
  escriba enroll AUDIO START END NAME PROJECT
  escriba repair [DIR ...]      fix samples of audio moved to another folder
  escriba install-local         install local mode (transcribe on this PC)
  escriba data                  where your data and keys are

Each command has its own help: escriba <command> --help
Interface language: --lang en|es (or ESCRIBA_LANG); it's remembered.""")


def _utf8():
    # On Windows, with the output redirected to a file, Python would use cp1252
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_record(a):
    from . import record

    if a.list:
        devices = record.list_devices()
        print(_("Outputs (what plays; use with --output):"))
        for name, default in devices["outputs"]:
            print(f"  {name}" + (_(" (default)") if default else ""))
        print("\n" + _("Microphones (use with --mic):"))
        for name, default in devices["mics"]:
            print(f"  {name}" + (_(" (default)") if default else ""))
        return
    stem = config.clean_name(a.name) if a.name else record.default_name()
    if not stem:
        sys.exit(_("Invalid name: {name}", name=a.name))
    target = record.free_target(Path(a.dir).expanduser(), stem)
    r = record.Recording(target, output=a.output, mic=a.mic)
    try:
        r.start()
    except Exception as e:
        sys.exit(_("Can't record: {error}", error=e))
    print(_("Recording to: {path}\n  What plays: {output}\n  Microphone: {mic}\nCtrl+C to stop.",
            path=target, output=r.loop.name, mic=r.mic.name))
    try:
        while True:
            time.sleep(1)
            s = int(r.seconds)
            print(f"\r{s // 60}:{s % 60:02d}  " + "  ".join(r.warnings), end="", flush=True)
    except KeyboardInterrupt:
        pass
    r.stop()
    print("\n" + _("Saved: {path}", path=target))
    if a.transcribe:
        from . import transcribe
        transcribe.transcribe(target, engine="local" if a.local else "cloud", diarize=bool(a.project),
                              project=a.project or "")


def cmd_transcribe(a):
    from . import transcribe

    if a.cpu:
        os.environ["ESCRIBA_GPU"] = "never"
    speakers = [s.strip() for s in a.speakers.split(",") if s.strip()]
    diarize = a.diarize or bool(a.project) or bool(speakers)
    try:
        transcribe.transcribe(a.audio, engine="local" if a.local else "cloud", model=a.model, language=a.language,
                              diarize=diarize, project=a.project, speakers=speakers, prompt=a.prompt)
    except Exception as e:
        sys.exit(_("Error: {error}", error=e))


def cmd_archive(a):
    from . import archive

    dirs = [Path(d).expanduser() for d in a.dirs] or archive.project_dirs()
    archive.archive_dirs(dirs, dry_run=a.dry_run)


def cmd_enroll(a):
    from . import review

    n, added = review.enroll(a.audio, a.start, a.end, a.name, a.project)
    if added:
        print(_("Added a sample of {name} to project {project} ({n} samples in total)",
                name=a.name, project=a.project, n=n))
    else:
        print(_("There was already an almost identical sample of {name}: not adding another ({n} samples in total)",
                name=a.name, n=n))


def cmd_web(a):
    import socket
    import webbrowser

    url = f"http://127.0.0.1:{a.port}"
    with socket.socket() as s:
        already_open = s.connect_ex(("127.0.0.1", a.port)) == 0
    if already_open:
        # Second click on the shortcut: escriba is already running
        print(_("Escriba is already open at {url}", url=url))
        if not a.no_browser:
            webbrowser.open(url)
        return

    from . import web

    print(_("Escriba at {url}\nKeep this window open while you use it; closing it closes Escriba "
            "(and stops any recording).", url=url))
    web.run(port=a.port, open_browser=not a.no_browser)


def cmd_repair(a):
    from . import repair

    r = repair.repair(extra=a.dirs, dry_run=a.dry_run)
    for old, new, refs in r["fixed"]:
        text = _("  would fix: {old}\n        -> {new} ({refs} references)") if a.dry_run else \
            _("  fixed: {old}\n        -> {new} ({refs} references)")
        print(text.format(old=old, new=new, refs=refs))
    for old, candidates in r["ambiguous"]:
        print(_("  several candidates for {old}: {candidates}", old=old, candidates=", ".join(candidates)))
    for old in r["not_found"]:
        print(_("  not found: {old}", old=old))
    if not any(r.values()):
        print(_("Every sample points at an audio file that exists."))


def cmd_install_local(a):
    from . import extras, gpu
    from .transcribe import local_available

    card = gpu.nvidia()
    use_gpu = a.gpu or (not a.cpu and bool(card and card["driver_ok"]))
    if a.gpu and not card:
        sys.exit(_("No NVIDIA card found (nvidia-smi doesn't answer)."))
    if local_available() and (not use_gpu or gpu.torch_has_cuda()):
        print(_("Local mode is already installed."))
        return
    if not extras.find_uv():
        sys.exit(_("uv was not found, so it can't be installed from here. Install it by hand:") + "\n  "
                 + extras.manual_command())
    if use_gpu and extras.local_job_running():
        sys.exit(_("A local transcription is running: wait until it ends."))
    if use_gpu:
        print(_("Installing local mode for the GPU {name} (experimental, ~{size} GB)...",
                name=card["name"] if card else "CUDA", size=number(extras.GPU_SIZE_GB)), flush=True)
    else:
        print(_("Installing local mode (~{size} GB)...", size=number(extras.SIZE_GB)), flush=True)
    if not extras.install(lambda line: print(line, flush=True), gpu=use_gpu):
        sys.exit(_("The installation failed. You can also install it by hand:") + "\n  " + extras.manual_command())
    print(_("Local mode installed."))


def cmd_data(a):
    print(_("Data folder: {path}", path=config.data_dir()))
    print(_("  Voices:   {path}", path=config.voiceprints_dir()))
    print(_("  Glossary: {path}", path=config.glossary_path()))
    for key in ("ASSEMBLYAI_API_KEY", "HF_TOKEN"):
        print(f"  {key}: " + (_("set") if config.read_secret(key) else _("missing")))


class _Formatter(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, _("usage: ") if prefix is None else prefix)


def _translated(p):
    """argparse's own texts, in the interface language."""
    p._positionals.title = _("positional arguments")
    p._optionals.title = _("options")
    p.add_argument("-h", "--help", action="help", help=_("show this help and exit"))
    return p


def parser():
    p = _translated(argparse.ArgumentParser(
        prog="escriba", description=_("Record, transcribe and identify speakers in meetings."),
        formatter_class=_Formatter, add_help=False, epilog=_(USAGE)))
    p.add_argument("--lang", choices=sorted(i18n.LANGUAGES), help=_("interface language (it's remembered)"))
    subparsers = p.add_subparsers(dest="command", metavar=_("command"))


    def command(name, **kwargs):
        sub = _translated(subparsers.add_parser(name, formatter_class=_Formatter, add_help=False, **kwargs))
        # Also accepted after the command (it's read before parsing, see _early_lang)
        sub.add_argument("--lang", choices=sorted(i18n.LANGUAGES), default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sub

    r = command("record", help=_("record a meeting"),
                       description=_("Records what plays on the PC + your microphone, mixed, to a 16 kHz mono WAV."))
    r.add_argument("name", nargs="?", help=_("file name, without .wav (default: date_meeting_HHMM)"))
    r.add_argument("--dir", default=".", help=_("folder to save to (default: the current one)"))
    r.add_argument("--list", action="store_true", help=_("list outputs and microphones and exit"))
    r.add_argument("--output", help=_("output whose sound to record (default: the system one)"))
    r.add_argument("--mic", help=_("microphone (default: the system one)"))
    r.add_argument("--transcribe", action="store_true", help=_("transcribe when finished"))
    r.add_argument("--local", action="store_true", help=_("with --transcribe: locally instead of in the cloud"))
    r.add_argument("--project", help=_("with --transcribe: identify speakers by voice with this project"))
    r.set_defaults(func=cmd_record)

    t = command("transcribe", help=_("transcribe an audio file"),
                       description=_("Transcribes an audio file and leaves the .txt (and the .speakers.json if "
                                     "speakers are identified) next to it."))
    t.add_argument("audio")
    engine = t.add_mutually_exclusive_group()
    engine.add_argument("--cloud", action="store_true",
                        help=_("AssemblyAI (default): a few minutes, ~$0.23/hour; needs ASSEMBLYAI_API_KEY"))
    engine.add_argument("--local", action="store_true",
                        help=_("faster-whisper + pyannote on this PC: free but slow; needs local mode "
                               "(escriba install-local)"))
    t.add_argument("--model", default="medium", help=_("local only: tiny/base/small/medium/large/turbo (medium)"))
    t.add_argument("--language", default="auto", help=_("language spoken: es, gl, en... (default auto)"))
    t.add_argument("--diarize", action="store_true", help=_("separate speakers (implied by --project)"))
    t.add_argument("--project", default="", help=_("identify speakers by voice with this project's library"))
    t.add_argument("--speakers", default="", help=_('"A,B": names in order of appearance for unrecognised voices'))
    t.add_argument("--prompt", default=None, help=_("local only: initial prompt (default: the glossary)"))
    t.add_argument("--cpu", action="store_true", help=_("local only: don't use the GPU even if there is one"))
    t.set_defaults(func=cmd_transcribe)

    ar = command("archive", help=_("compress what's already reviewed to Opus"),
                        description=_("Converts to Opus the WAVs already transcribed and reviewed, and updates "
                                      "the references."))
    ar.add_argument("dirs", nargs="*", help=_("folders (default: the last one of each project)"))
    ar.add_argument("--dry-run", action="store_true", help=_("only list what it would do"))
    ar.set_defaults(func=cmd_archive)

    e = command("enroll", help=_("add a voice sample by hand"),
                       description=_("Adds the START-END clip (seconds) of an audio file as a voice sample."))
    e.add_argument("audio")
    e.add_argument("start", type=float)
    e.add_argument("end", type=float)
    e.add_argument("name")
    e.add_argument("project")
    e.set_defaults(func=cmd_enroll)

    w = command("web", help=_("browser interface"),
                       description=_("Opens escriba in the browser. Only reachable from this PC."))
    w.add_argument("--port", type=int, default=8765, help=_("local port (default 8765)"))
    w.add_argument("--no-browser", action="store_true", help=_("don't open the browser"))
    w.set_defaults(func=cmd_web)

    rp = command("repair", help=_("fix samples of audio moved to another folder"),
                        description=_("Looks up by name the audio files that were moved (in the projects' folders "
                                      "and the ones you give) and updates the samples' paths."))
    rp.add_argument("dirs", nargs="*", help=_("folders to search besides the projects' ones"))
    rp.add_argument("--dry-run", action="store_true", help=_("only say what it would do"))
    rp.set_defaults(func=cmd_repair)

    il = command("install-local", help=_("install local mode (transcribe on this PC)"),
                 description=_("Adds faster-whisper and pyannote (~1.5 GB) to escriba's environment. Whisper's "
                               "models are downloaded the first time each one is used."))
    device = il.add_mutually_exclusive_group()
    device.add_argument("--gpu", action="store_true",
                        help=_("version for NVIDIA cards (experimental, ~5 GB); also switches an installed CPU one"))
    device.add_argument("--cpu", action="store_true", help=_("CPU version even with an NVIDIA card"))
    il.set_defaults(func=cmd_install_local)

    d = command("data", help=_("where your data is and which keys are set"))
    d.set_defaults(func=cmd_data)
    return p


def _early_lang(argv):
    """--lang has to be known before building the parser, whose help is translated."""
    for i, arg in enumerate(argv):
        value = arg.split("=", 1)[1] if arg.startswith("--lang=") else (
            argv[i + 1] if arg == "--lang" and i + 1 < len(argv) else None)
        if value in i18n.LANGUAGES:
            return value
    return None


def main(argv=None):
    _utf8()
    # pyannote/torch noise (deprecation notices, etc.) that clutters the logs
    warnings.filterwarnings("ignore", category=UserWarning)
    argv = sys.argv[1:] if argv is None else argv
    if lang := _early_lang(argv):
        i18n.set_language(lang)
        config.update_state(language=lang)
    args = parser().parse_args(argv)
    try:
        if not args.command:
            from . import menu
            return menu.main()
        return args.func(args)
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to close it: whatever was running already
        # stopped cleanly (a recording keeps its WAV), no traceback to show
        print("\n" + _("Escriba closed."))
        return 130
