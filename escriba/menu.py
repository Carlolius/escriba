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
from . import config, i18n, jobs, record, review, voiceprints
from .i18n import _, _n
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


def choose_engine_language():
    """Returns (engine, model, language) or None."""
    engine = _select(
        _("Where to transcribe?"),
        choices=[
            _choice(_("In the cloud (AssemblyAI): a few minutes, ~$0.23 per hour of audio"), "cloud"),
            _choice(_("Locally: free and the audio never leaves the PC, but ~1 h 15 min per hour of audio"),
                    "local"),
        ],
        default="cloud",
    ).ask()
    if engine is None:
        return None
    if engine == "local" and not local_available():
        console.print(_("[red]Local mode is not installed[/red] (the 'local' extra is missing: faster-whisper "
                        "and pyannote)."))
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
