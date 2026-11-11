"""Interactive terminal menu to record, transcribe and identify speakers.

All the logic is in the rest of the package; this only asks and shows. The
web interface uses the same functions.
"""
import math
import os
import time
from pathlib import Path

import questionary
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.table import Table

from . import audio as audio_util
from . import config, i18n, jobs, meetings, record, review, voiceprints
from .i18n import N_, _, _n, number
from .paths import shown_path
from .transcribe import local_available, missing_key

console = Console()
NEW_PROJECT = "\0new"
OTHER_PATH = "\0other"
BACK = "\0back"


def _choice(title, value):
    return questionary.Choice(title, value=value)


def _select(message, choices, **kwargs):
    return questionary.select(message, choices=choices, instruction=_("(Use arrow keys)"), **kwargs)


# ── Common choices ───────────────────────────────────────────────────────────

def choose_project():
    projects = config.list_projects()
    last = config.load_state().get("last_project")
    choice = _select(_("Project:"), choices=projects + [_choice(_("+ new project..."), NEW_PROJECT)],
                                default=last if last in projects else None).ask()
    if choice is None:
        return None
    if choice == NEW_PROJECT:
        choice = questionary.text(_("Name of the new project (e.g. client_x):")).ask()
        if not choice:
            return None
        config.create_project(choice)
    config.update_state(last_project=choice)
    return choice


def _project_dir(project):
    return config.project_dir(project) or str(Path.home())


def choose_audio(project):
    folder = Path(_project_dir(project))
    todo = jobs.untranscribed(folder, limit=10)
    if todo:
        options = []
        for wav, dur in todo:
            title = str(wav.relative_to(folder))
            if dur:
                title += " · " + _("{duration} · ~{local} locally, minutes in the cloud",
                                   duration=jobs.format_minutes(dur),
                                   local=jobs.format_minutes(dur * jobs.PROCESS_FACTOR))
            options.append(_choice(title, str(wav)))
        options.append(_choice(_("Type another path..."), OTHER_PATH))
        choice = _select(_("Audio file (not transcribed yet):"), choices=options).ask()
        if choice is None:
            return None
        if choice != OTHER_PATH:
            # The project folder isn't changed: if the audio was in a subfolder,
            # remembering it would leave the rest of the project out of the next search.
            return Path(choice)

    path = questionary.path(_("Audio file:"), default=str(folder) + os.sep).ask()
    if not path:
        return None
    path = Path(path).expanduser()
    config.set_project_dir(project, path.parent)
    return path


def install_local_mode():
    """Offers to install local mode (faster-whisper + pyannote). True if it's
    installed afterwards."""
    from . import extras, gpu

    console.print(_("Local mode is not installed: it needs ~{size} GB of libraries, and then the whisper model "
                    "the first time it's used.", size=number(extras.SIZE_GB)))
    use_gpu = False
    card = gpu.nvidia()
    if card and card["driver_ok"]:
        use_gpu = questionary.confirm(
            _("Install the version for your NVIDIA card ({name})? Experimental, ~{size} GB; if it fails, the CPU "
              "is used.", name=card["name"], size=number(extras.GPU_SIZE_GB)), default=True).ask()
        if use_gpu is None:
            return False
    elif card:
        console.print(_("Your NVIDIA driver ({driver}) is too old to use the GPU: installing the CPU version.",
                        driver=card["driver"]))
    if not extras.find_uv():
        console.print(_("uv was not found, so it can't be installed from here. Install it by hand:"))
        console.print("  " + escape(extras.manual_command()))
        return False
    free = extras.free_gb()
    needed = extras.GPU_NEEDED_GB if use_gpu else extras.NEEDED_GB
    if free < needed:
        console.print(_("[yellow]Only {free} GB free on the disk: about {needed} GB are needed.[/yellow]",
                        free=number(free), needed=needed))
    if not questionary.confirm(_("Install it now?"), default=False).ask():
        return False
    if extras.install(lambda line: console.print(escape(line), style="dim", highlight=False), gpu=use_gpu):
        console.print(_("[green]Local mode installed.[/green]"))
        return True
    console.print(_("[red]The installation failed.[/red] You can also install it by hand:"))
    console.print("  " + escape(extras.manual_command()))
    return False


def choose_engine_language():
    """Returns (engine, model, language) or None."""
    from . import gpu

    if local_available() and gpu.will_try():
        local_text = _("Locally: free and the audio never leaves the PC; with the GPU ({name}, experimental)",
                       name=gpu.describe())
    else:
        local_text = _("Locally: free and the audio never leaves the PC, but ~1 h 15 min per hour of audio")
    engine = _select(
        _("Where to transcribe?"),
        choices=[
            _choice(_("In the cloud (AssemblyAI): a few minutes, ~$0.23 per hour of audio"), "cloud"),
            _choice(local_text, "local"),
        ],
        default="cloud",
    ).ask()
    if engine is None:
        return None
    if engine == "local" and not local_available() and not install_local_mode():
        return None
    language = _select(
        _("Language spoken:"),
        choices=[
            _choice(_("auto (detect it; a meeting with Galician usually comes out in Spanish)"), "auto"),
            "es",
            _choice(_("gl (keeps the Galician/Spanish mix; in the cloud it may merge speakers)"), "gl"),
            "en",
            _choice(_("other..."), "other"),
        ],
        default="auto",
    ).ask()
    if language == "other":
        language = questionary.text(_("Language code (e.g. fr, de):")).ask()
    if not language:
        return None
    model = "medium"
    if engine == "local":
        model = _select(
            _("Model:"),
            choices=[
                "medium",
                _choice(_("turbo (~25% faster, but sometimes skips sentences; downloaded the first time)"), "turbo"),
                _choice(_("large (downloaded the first time, ~3 GB)"), "large"),
                "small", "base", "tiny",
            ],
            default="medium",
        ).ask()
        if model is None:
            return None
    return engine, model, language


def _key_is_missing(engine):
    if not (key := missing_key(engine)):
        return False
    console.print(_("[red]{key} is missing.[/red] Put it in {path} (a line {key}=...) and try again.",
                    key=key, path=config.secrets_path()))
    return True


# ── Record and transcribe ────────────────────────────────────────────────────

def _bar(level):
    # Voice RMS is usually around 0.01-0.1: log scale so it shows
    full = 0 if level <= 0 else max(0, min(20, int((math.log10(level) + 4) * 5)))
    return "█" * full + "·" * (20 - full)


def do_record():
    project = choose_project()
    if not project:
        return
    folder = questionary.path(_("Where to save the recording?"), default=_project_dir(project) + os.sep,
                              only_directories=True).ask()
    if not folder:
        return
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    config.set_project_dir(project, folder)

    description = questionary.text(_("Meeting description (e.g. weekly_followup):")).ask()
    if description is None:
        return
    audio = folder / f"{record.default_name(description)}.wav"

    try:
        r, warning = record.from_preferences(audio)
    except Exception as e:
        console.print("[red]" + escape(_("Can't record: {error}", error=e)) + "[/red]")
        return
    if warning:
        console.print(f"[yellow]{escape(warning)}[/yellow]")
    console.print("[dim]" + _("Tell the others you are recording the meeting.") + "[/dim]")
    console.print(_("[bold]Recording[/bold] {name}\n  What plays: {output}\n  Microphone: {mic}",
                    name=audio.name, output=r.loop.name, mic=r.mic.name))
    r.start()
    try:
        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while True:
                s = int(r.seconds)
                text = (f"[bold red]●[/bold red] {s // 60}:{s % 60:02d}   "
                        + _("system {system}   mic {mic}", system=_bar(r.levels["system"]), mic=_bar(r.levels["mic"]))
                        + "   [dim]" + _("Ctrl+C to stop") + "[/dim]")
                for w in r.warnings + r.errors:
                    text += f"\n[yellow]{escape(w)}[/yellow]"
                live.update(text)
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    r.stop()
    console.print(_("[green]Recorded:[/green] {path} ({duration})", path=audio,
                    duration=jobs.format_minutes(r.seconds)))

    if not questionary.confirm(_("Transcribe and identify now?"), default=False).ask():
        console.print("[dim]" + _("You can transcribe it later with \"Transcribe + identify\".") + "[/dim]")
        return
    _transcribe(project, audio)


def do_transcribe():
    project = choose_project()
    if not project:
        return
    audio = choose_audio(project)
    if not audio or not audio.exists():
        console.print("[red]" + _("File not found.") + "[/red]")
        return
    _transcribe(project, audio)


def _transcribe(project, audio):
    choice = choose_engine_language()
    if choice is None:
        return
    engine, model, language = choice
    if _key_is_missing(engine):
        return
    background = _select(
        _("How to transcribe?"),
        choices=[
            _choice(_("Foreground (wait here until it's done)"), False),
            _choice(_("Background (same quality; you can record another meeting meanwhile)"), True),
        ],
    ).ask()
    if background is None:
        return
    if background:
        jobs.start(audio, project, engine, model, language)
        console.print("[dim]" + _("Transcribing in the background. Progress shows above the main menu.\n"
                                  "When it's done, review it in \"Review speakers\".") + "[/dim]")
        return

    from . import transcribe
    try:
        transcribe.transcribe(audio, engine=engine, model=model, language=language, diarize=True, project=project)
    except KeyboardInterrupt:
        console.print("[yellow]" + _("Transcription cancelled.") + "[/yellow]")
        return
    except Exception as e:
        console.print("[red]" + escape(_("Error: {error}", error=e)) + "[/red]")
        return
    sidecar = audio.with_suffix(review.SUFFIX)
    if sidecar.exists():
        show_clusters(sidecar)
        if questionary.confirm(_("Review the speakers now?"), default=False).ask():
            review_sidecar(sidecar, project)


def show_jobs():
    """Prints the background transcriptions; returns how many are still running."""
    n = 0
    for job, status, text in jobs.check_jobs():
        name = escape(Path(job["audio"]).stem)
        if status == "running":
            console.print(_("[cyan]Running:[/cyan] {name} · {text}", name=name, text=text))
            n += 1
        elif status == "done":
            console.print(_("[green]Done:[/green] {name} ({text})", name=name, text=text))
        else:
            console.print(_("[red]Failed:[/red] {name} · {text}", name=name, text=escape(text)))
    return n


# ── Meetings ─────────────────────────────────────────────────────────────────

STATUS = {
    "recording": N_("Recording"), "transcribing": N_("Transcribing"), "untranscribed": N_("Not transcribed"),
    "to_review": N_("Speakers to review"), "reviewed": N_("Reviewed"),
}
STATUS_STYLE = {"recording": "red", "transcribing": "cyan", "untranscribed": "dim", "to_review": "yellow",
                "reviewed": "green"}


def _length(seconds):
    if not seconds:
        return "-"
    seconds = round(seconds)
    h, m, s = seconds // 3600, seconds // 60 % 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _meeting_label(m):
    return f"{m['audio'].stem}  ({_(STATUS[m['status']])})"


def _play_meeting(audio, duration):
    start = questionary.text(_("From which minute? (0 = the start; Ctrl+C stops it)"), default="0").ask()
    try:
        start = max(0.0, float((start or "0").replace(",", ".")) * 60)
    except ValueError:
        return
    play_sample({"audio": str(audio), "start": start, "end": duration or start + 3600})


def _delete_meeting(audio):
    files = meetings.files_of(audio)
    console.print(_("These files will be deleted:"))
    for f in files:
        console.print("  · " + escape(f.name))
    if not questionary.confirm(_("Delete {name}?", name=audio.stem), default=False).ask():
        return False
    samples = sum(voiceprints.samples_from_audio(audio).values())
    delete_samples = False
    if samples:
        console.print(_n("{n} voice sample was taken from this meeting.",
                         "{n} voice samples were taken from this meeting.", samples))
        delete_samples = questionary.confirm(_("Delete them too (otherwise they stay, but can't be played)"),
                                             default=False).ask()
    n_files, n_samples = meetings.delete(audio, bool(delete_samples))
    text = _n("{n} file deleted", "{n} files deleted", n_files)
    if n_samples:
        text += " · " + _n("{n} sample deleted (can be undone in People)",
                           "{n} samples deleted (can be undone in People)", n_samples)
    console.print("[green]✓[/green] " + text)
    return True


def _meeting(project, m):
    audio = m["audio"]
    while True:
        status = meetings.status(audio, jobs.running_audio())
        options = [_choice(_("Play"), "play")]
        if audio.with_suffix(".txt").exists():
            options.append(_choice(_("See transcript"), "read"))
        if status == "untranscribed":
            options.append(_choice(_("Transcribe"), "transcribe"))
        if status == "to_review":
            options.append(_choice(_("Review speakers"), "review"))
        if status != "transcribing":
            options.append(_choice(_("Delete..."), "delete"))
        options.append(_choice(_("Back"), BACK))
        action = _select(_meeting_label(dict(m, status=status)) + ":", choices=options).ask()
        if action in (None, BACK):
            return
        if action == "play":
            _play_meeting(audio, m["duration"])
        elif action == "read":
            with console.pager():
                console.print(escape(audio.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")))
        elif action == "transcribe":
            _transcribe(project, audio)
        elif action == "review":
            review_sidecar(audio.with_name(audio.stem + review.SUFFIX), project)
        elif action == "delete" and _delete_meeting(audio):
            return


def meetings_menu():
    project = choose_project()
    if not project:
        return
    folder = _project_dir(project)
    while True:
        found = meetings.list_meetings(folder)
        if not found:
            console.print("[dim]" + escape(_("No meetings in {folder}.", folder=shown_path(folder))) + "[/dim]")
            return
        console.print("[dim]" + escape(shown_path(folder)) + "[/dim]")
        table = Table(title=_("Meetings of {project}", project=project))
        for col in (_("Meeting"), _("Date"), _("Length"), _("State")):
            table.add_column(col)
        for m in found:
            style = STATUS_STYLE[m["status"]]
            table.add_row(escape(m["audio"].stem), m["date"].strftime("%Y-%m-%d %H:%M"),
                          _length(m["duration"]),
                          f"[{style}]{_(STATUS[m['status']])}[/{style}]")
        console.print(table)
        choice = _select(_("Which meeting?"), choices=[_choice(_meeting_label(m), i) for i, m in enumerate(found)]
                         + [_choice(_("Back to the main menu"), BACK)]).ask()
        if choice in (None, BACK):
            return
        _meeting(project, found[choice])
        console.print()


# ── Review speakers ──────────────────────────────────────────────────────────

def show_clusters(sidecar):
    data = review.load(sidecar)
    table = Table(title=_("Speakers: {name}", name=Path(sidecar).name))
    for col in (_("Cluster"), _("Assigned name"), _("Similarity"), _("Speech time")):
        table.add_column(col)
    for spk, info in data["clusters"].items():
        sim = info["similarity"]
        style = "yellow" if info.get("unnamed") else "green"
        table.add_row(spk, f"[{style}]{escape(info['name'])}[/{style}]",
                      f"{sim:.2f}" if sim is not None else "-", f"{info['speech_seconds']:.0f}s")
    console.print(table)


def play_sample(origin):
    if not origin:
        console.print("[yellow]" + _("This sample has no source audio saved.") + "[/yellow]")
        return
    path = Path(origin["audio"])
    if not path.exists():
        console.print("[yellow]" + escape(_("Source audio not found: {path}", path=path)) + "[/yellow]")
        return
    console.print("[dim]" + escape(_("▶ {name} [{start:.1f}s-{end:.1f}s] (Ctrl+C to stop)",
                                     name=path.name, start=origin["start"], end=origin["end"])) + "[/dim]")
    try:
        audio_util.play(path, origin["start"], origin["end"])
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print("[yellow]" + escape(_("Couldn't play it: {error}", error=e)) + "[/yellow]")


def _ask_name(question, known):
    if known:
        return questionary.autocomplete(question, choices=known).ask()
    return questionary.text(question).ask()


def _print_decision(name, r, project):
    if r["added"]:
        console.print("  [green]✓[/green] " + escape(_n("{name}: {n} sample in {project}",
                                                         "{name}: {n} samples in {project}",
                                                         r["samples"], name=name, project=project)))
    else:
        console.print("  [dim]" + escape(_n("{name} already had an almost identical sample: not adding another "
                                            "({n} sample)",
                                            "{name} already had an almost identical sample: not adding another "
                                            "({n} samples)", r["samples"], name=name)) + "[/dim]")


def review_sidecar(sidecar, project):
    """Reviews the speakers one by one; every decision is saved at once, so Esc
    stops without losing anything and next time it resumes where it was."""
    data = review.load(sidecar)
    quotes = review.quotes_by_cluster(sidecar)
    done = sum(1 for c in data["clusters"].values() if c.get("reviewed"))
    if done:
        console.print("[dim]" + _n("Resuming: {n} speaker already reviewed last time.",
                                   "Resuming: {n} speakers already reviewed last time.", done) + "[/dim]")

    changes = 0
    complete = data.get("reviewed", False)
    for spk, info in data["clusters"].items():
        if info.get("reviewed"):
            continue
        current = info["name"]
        console.print("\n" + _("[bold]{speaker}[/bold] ({name}) said, among other things:",
                               speaker=spk, name=escape(current)))
        for quote in quotes.get(spk) or [_("(no long sentences of theirs in the transcript)")]:
            console.print(f"  [dim]«{escape(quote)}»[/dim]")

        new = None
        while new is None:
            choice = _select(
                _("{speaker} ({seconds:.0f}s of speech) → assigned as '{name}'",
                  speaker=spk, seconds=info["speech_seconds"], name=current),
                choices=[
                    _choice(_("Play"), "play"),
                    _choice(_("Confirm (and reinforce the sample)"), "ok"),
                    _choice(_("Correct the name"), "correct"),
                    _choice(_("Skip (I don't know who it is; nothing is saved in the library)"), "skip"),
                ],
            ).ask()
            if choice is None:
                left = review.remaining(sidecar)
                console.print("[yellow]" + _n("Review stopped. {n} speaker left; it's still pending in "
                                              "\"Review speakers\".",
                                              "Review stopped. {n} speakers left; it's still pending in "
                                              "\"Review speakers\".", left) + "[/yellow]")
                return
            if choice == "play":
                play_sample(info.get("origin"))
            elif choice == "skip":
                new = ""
            elif choice == "ok":
                new = current
            else:
                # Esc or empty name: back to this same speaker's menu
                new = _ask_name(_("Right name:"), review.known_names(sidecar, project)) or None

        r = review.decide(sidecar, spk, new, project)
        complete = r["complete"]
        if new:
            changes += 1
            _print_decision(new, r, project)
            if r["renamed"]:
                console.print("  [dim]" + _n("Renamed in the transcript ({n} time)",
                                             "Renamed in the transcript ({n} times)", r["renamed"]) + "[/dim]")

    console.print("[bold green]" + _n("Review complete: {n} speaker confirmed or corrected.",
                                      "Review complete: {n} speakers confirmed or corrected.", changes)
                  + "[/bold green]")
    if complete:
        console.print("\n" + _("Compressing the audio to Opus to archive it (don't close yet)..."))
        try:
            if result := review.archive_if_complete(sidecar):
                console.print("[dim]" + _("Audio archived as {name} ({mb:.0f} MB less).",
                                          name=result[0].name, mb=result[1] / 1e6) + "[/dim]")
        except Exception as e:  # the WAV stays as it is if something fails
            console.print("[yellow]" + escape(_("Couldn't compress it: {error}", error=e)) + "[/yellow]")


def review_speakers(only_project=None):
    todo = review.pending(only_project)
    if not todo:
        console.print("[green]" + _("No transcripts waiting for review.") + "[/green]")
        return
    options = []
    for project, s in todo[:15]:
        title = review.meeting_name(s) + ("" if only_project else f" · {project}")
        options.append(_choice(title, (project, s)))
    choice = _select(_("Which transcript to review?"), choices=options).ask()
    if not choice:
        return
    project, sidecar = choice
    show_clusters(sidecar)
    review_sidecar(sidecar, project)


# ── People (voice library) ───────────────────────────────────────────────────

def _sample_label(sample):
    origin = sample.get("origin")
    if origin:
        return _("{seconds:.0f}s of {name} [{start:.0f}s-{end:.0f}s]", seconds=origin["end"] - origin["start"],
                 name=Path(origin["audio"]).name, start=origin["start"], end=origin["end"])
    return _("no source saved (can't be played)")


def _no_voices(project):
    console.print("[yellow]" + _("Project {project} has no saved voices yet.", project=project) + "[/yellow]")


def _move(project, name, sample_id):
    new = _ask_name(_("{name}: who does it really belong to? (a new name if they're not on the list)", name=name),
                    sorted(voiceprints.load_library(project)))
    if not new or new == name:
        return False
    voiceprints.move_sample(project, name, sample_id, new)
    console.print("[green]✓[/green] " + escape(_("Moved to {name}", name=new)))
    return True


def _manage_sample(project, name, sample_id):
    while True:
        sample = voiceprints.find_sample(project, name, sample_id)
        if sample is None:
            console.print("[dim]" + _("That sample no longer exists (it was deleted or moved).") + "[/dim]")
            return
        action = _select(
            f"{name}: {_sample_label(sample)}",
            choices=[_choice(_("Play"), "play"), _choice(_("Move to another person"), "move"),
                     _choice(_("Delete this sample"), "delete"), _choice(_("Back"), BACK)],
        ).ask()
        if action in (None, BACK):
            return
        if action == "play":
            play_sample(sample.get("origin"))
        elif action == "delete":
            voiceprints.delete_sample(project, name, sample_id)
            console.print("[green]✓[/green] " + _("Sample deleted"))
            return
        elif _move(project, name, sample_id):
            return


def _people_summary(project):
    data = voiceprints.load_samples(project)
    if not data:
        return _no_voices(project)
    table = Table(title=_("Project: {project}", project=project))
    for col in (_("Person"), _("Samples"), _("With playable audio")):
        table.add_column(col)
    for name, samples in sorted(data.items()):
        playable = sum(1 for s in samples if s.get("origin"))
        table.add_row(escape(name), str(len(samples)), f"{playable}/{len(samples)}")
    console.print(table)


def _people_browse(project):
    while True:
        data = voiceprints.load_samples(project)
        if not data:
            return _no_voices(project)
        options = [_choice(_n("{name} ({n} sample)", "{name} ({n} samples)", len(s), name=n), n)
                   for n, s in sorted(data.items())]
        name = _select(_("Person:"), choices=options + [_choice(_("Back"), BACK)]).ask()
        if name in (None, BACK):
            return
        while True:
            samples = voiceprints.load_samples(project).get(name, [])
            if not samples:
                console.print("[dim]" + escape(_("{name} has no samples left.", name=name)) + "[/dim]")
                break
            options = [_choice(_sample_label(s), s["id"]) for s in samples]
            sample_id = _select(_("{name}: pick a sample:", name=name),
                                           choices=options + [_choice(_("Back"), BACK)]).ask()
            if sample_id in (None, BACK):
                break
            _manage_sample(project, name, sample_id)


def _people_rename(project):
    data = voiceprints.load_samples(project)
    if not data:
        _no_voices(project)
        return
    name = _select(_("Rename whom?"), choices=sorted(data) + [_choice(_("Cancel"), BACK)]).ask()
    if name in (None, BACK):
        return
    new = (questionary.text(_("New name for {name}", name=name), default=name).ask() or "").strip()
    if not new or new == name:
        return
    if new in data and not questionary.confirm(
            _("{name} already exists: their samples will be joined (same person).", name=new) + " " + _("Go on?"),
            default=True).ask():
        return
    voiceprints.rename_person(project, name, new)
    text = _("{old} is now {new}", old=name, new=new)
    if questionary.confirm(_("Also change it in this project's transcripts"), default=True).ask():
        n = review.rename_in_transcripts(project, name, new)
        if n:
            text += " · " + _n("changed in {n} meeting", "changed in {n} meetings", n)
    console.print("[green]✓[/green] " + escape(text))


def _people_delete(project):
    data = voiceprints.load_library(project)
    if not data:
        return _no_voices(project)
    name = _select(_("Delete whom?"), choices=sorted(data) + [_choice(_("Cancel"), BACK)]).ask()
    if name in (None, BACK):
        return
    question = _n("Are you sure you want to delete {name} and their {n} sample?",
                  "Are you sure you want to delete {name} and their {n} samples?", len(data[name]), name=name)
    if questionary.confirm(question, default=False).ask():
        voiceprints.delete_person(project, name)
        console.print("[green]✓[/green] " + escape(_("{name} deleted from project {project}",
                                                     name=name, project=project)))


def _people_undo(project):
    if not voiceprints.has_backup(project):
        console.print("[yellow]" + _("Nothing to undo yet (nothing has been deleted or moved).") + "[/yellow]")
        return
    if questionary.confirm(_("This undoes the last delete or move (one step back only). Restore?"),
                           default=False).ask():
        voiceprints.restore_backup(project)
        console.print("[green]✓[/green] " + _("Project {project} restored to before the last change.",
                                              project=project))


def _people_enroll(project):
    audio = choose_audio(project)
    if not audio or not audio.exists():
        console.print("[red]" + _("File not found.") + "[/red]")
        return
    start = questionary.text(_("Start (seconds):")).ask()
    end = questionary.text(_("End (seconds):")).ask()
    name = questionary.text(_("Person's name:")).ask()
    if not (start and end and name):
        return
    n, added = review.enroll(audio, float(start), float(end), name, project)
    _print_decision(name, {"added": added, "samples": n}, project)


def _people_repair():
    from . import repair

    r = repair.repair()
    for old, new, refs in r["fixed"]:
        console.print(f"[green]✓[/green] {escape(Path(old).name)} → {escape(str(Path(new).parent))} ({refs})")
    for old, _candidates in r["ambiguous"]:
        console.print("[yellow]" + escape(_("Several candidates for {path}: left alone", path=old)) + "[/yellow]")
    for old in r["not_found"]:
        console.print("[yellow]" + escape(_("Not found: {path}", path=old)) + "[/yellow]")
    if not any(r.values()):
        console.print("[green]" + _("Every sample points at an audio file that exists.") + "[/green]")


def _people_audit(project):
    """One flat menu per finding: "Next" is the default, so if everything is
    fine, Enter is enough. It recomputes after every action, so a fixed finding
    disappears from the list. "Next" skips it only for this session; "Mark as
    fine" saves it so it's never flagged again."""
    seen = set()

    def key(f):
        return (f["kind"], f["id_a"], f["id_b"])

    while True:
        todo = [f for f in voiceprints.audit_library(project) if key(f) not in seen]
        if not todo:
            if seen:
                console.print("[bold green]" + _n(
                    "No findings left to review ({n} skipped this session; they'll show up again if not fixed).",
                    "No findings left to review ({n} skipped this session; they'll show up again if not fixed).",
                    len(seen)) + "[/bold green]")
            else:
                console.print("[green]" + _("No pending findings in project {project}", project=project) + "[/green]")
            return

        f = voiceprints.most_urgent_first(todo)[0]
        a, b, sim = escape(f["name_a"]), escape(f["name_b"]), f["similarity"]
        console.print("[dim]" + _n("{n} pending finding", "{n} pending findings", len(todo)) + "[/dim]")
        if f["kind"] == "confusion":
            color = "red" if sim >= voiceprints.DEFAULT_THRESHOLD else "yellow"
            console.print(f"[{color}]" + _("Possible confusion") + f"[/{color}]: {a} / {b} "
                          + _("(similarity {similarity:.2f})", similarity=sim))
        elif f["kind"] == "duplicate":
            console.print("[cyan]" + _("Almost duplicate samples") + f"[/cyan]: {a} "
                          + _("(similarity {similarity:.2f}); you can probably delete one", similarity=sim))
        else:
            console.print("[yellow]" + _("Spread-out samples") + f"[/yellow]: {a} "
                          + _("(similarity {similarity:.2f})", similarity=sim))

        sides = {"A": (f["name_a"], f["id_a"]), "B": (f["name_b"], f["id_b"])}
        options = [_choice(_("Next (no changes)"), ("next", None))]
        for verb, label in (("play", _("Play {side} ({name})")), ("delete", _("Delete {side} ({name})")),
                            ("move", _("Move {side} ({name})"))):
            for side, (name, _id) in sides.items():
                options.append(_choice(label.format(side=side, name=name), (verb, side)))
        options += [_choice(_("Mark as fine (don't flag it again)"), ("ok", None)),
                    _choice(_("Leave the audit"), ("quit", None))]
        action = _select(_("What do we do?"), choices=options, default=options[0]).ask()

        if action is None or action[0] == "quit":
            return
        verb, side = action
        if verb == "next":
            seen.add(key(f))
        elif verb == "ok":
            voiceprints.mark_as_ok(project, f["kind"], f["id_a"], f["id_b"])
            console.print("[green]✓[/green] " + _("Marked as fine, it won't show up again."))
        else:
            name, sample_id = sides[side]
            if verb == "play":
                sample = voiceprints.find_sample(project, name, sample_id)
                play_sample(sample.get("origin") if sample else None)
            elif verb == "delete":
                voiceprints.delete_sample(project, name, sample_id)
                console.print("[green]✓[/green] " + escape(_("Sample of {name} deleted.", name=name)))
            else:
                _move(project, name, sample_id)
        console.print()


def people_menu():
    project = choose_project()
    if not project:
        return
    actions = [
        (_("See summary"), lambda: _people_summary(project)),
        (_("Audit and fix"), lambda: _people_audit(project)),
        (_("Correct speakers (recent transcript)"), lambda: review_speakers(only_project=project)),
        (_("Browse by person (play / move / delete)"), lambda: _people_browse(project)),
        (_("Add a sample by hand"), lambda: _people_enroll(project)),
        (_("Rename a person"), lambda: _people_rename(project)),
        (_("Delete a whole person"), lambda: _people_delete(project)),
        (_("Undo the last delete or move"), lambda: _people_undo(project)),
        (_("Repair paths (audio moved to another folder)"), _people_repair),
    ]
    while True:
        n = len(voiceprints.audit_library(project))
        title = _("People, project '{project}'", project=project)
        if n:
            title += " " + _n("({n} pending audit finding)", "({n} pending audit findings)", n)
        choice = _select(title + ":", choices=[_choice(t, i) for i, (t, _f) in enumerate(actions)]
                                    + [_choice(_("Back to the main menu"), BACK)]).ask()
        if choice in (None, BACK):
            return
        actions[choice][1]()
        console.print()


# ── Main menu ────────────────────────────────────────────────────────────────

def choose_language():
    current = config.load_state().get("language") or "auto"
    choice = _select(
        "Language / Idioma:",
        choices=[_choice(_("Same as the system"), "auto")] + [_choice(n, c) for c, n in i18n.LANGUAGES.items()],
        default=current,
    ).ask()
    if choice:
        config.update_state(language=None if choice == "auto" else choice)
        i18n.set_language(choice)


def main():
    console.print(_("[bold cyan]Escriba[/bold cyan]: record, transcribe and identify speakers in meetings") + "\n")
    while True:
        running = show_jobs()
        n = len(review.pending())
        review_title = _("Review speakers") + " " + (
            _n("({n} pending)", "({n} pending)", n) if n else _("(nothing pending)"))
        options = [
            (_("Record a meeting"), do_record),
            (_("Meetings"), meetings_menu),
            (_("Transcribe + identify"), do_transcribe),
            (review_title, review_speakers),
            (_("People"), people_menu),
        ]
        if running:
            options.append((_("Refresh progress"), lambda: None))  # the loop prints the progress again
        options.append(("Language / Idioma", choose_language))
        choice = _select(_("What do you want to do?"),
                                    choices=[_choice(t, i) for i, (t, _f) in enumerate(options)]
                                    + [_choice(_("Quit"), BACK)]).ask()
        if choice in (None, BACK):
            break
        options[choice][1]()
        console.print()
