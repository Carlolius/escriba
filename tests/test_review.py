import json
import shutil

from escriba import audio, config, repair, review, voiceprints


def test_quotes():
    text = ("\n[0s] Ana:\nHello, this is quite a long sentence.\n[2s] short\n"
            "\n[5s] Bea:\nAnother sentence of five words.\n")
    assert review.quotes(text, "Ana") == ["Hello, this is quite a long sentence."]
    assert review.quotes(text, "Bea") == ["Another sentence of five words."]


def test_pending_looks_in_the_project_folder(meeting):
    wav, sidecar, _txt = meeting
    assert review.pending() == []
    config.set_project_dir("test", wav.parent)
    assert review.pending() == [("test", sidecar.resolve())]


def test_known_names_leave_out_unnamed_voices(meeting):
    _wav, sidecar, _txt = meeting
    assert review.known_names(sidecar, "test") == ["Ana"]


def test_correct_skip_and_archive(meeting):
    wav, sidecar, txt = meeting
    r = review.decide(sidecar, "SPEAKER_A", "Carol")
    assert r["added"] and r["renamed"] == 1 and not r["complete"]
    assert "[0s] Carol:" in txt.read_text(encoding="utf-8")
    assert review.remaining(sidecar) == 1
    r = review.decide(sidecar, "SPEAKER_B", "")  # don't know: leaves the library alone
    assert r["complete"]
    assert set(voiceprints.load_library("test")) == {"Carol"}

    dur = audio.duration(wav)
    opus, saved = review.archive_if_complete(sidecar)
    assert not wav.exists() and opus.suffix == ".opus" and saved > 0
    assert abs(audio.duration(opus) - dur) < 0.5
    # References move to the .opus, in the library and in the sidecar
    assert voiceprints.load_samples("test")["Carol"][0]["origin"]["audio"] == str(opus)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["clusters"]["SPEAKER_A"]["origin"]["audio"] == str(opus)


def test_not_archived_until_fully_reviewed(meeting):
    wav, sidecar, _txt = meeting
    review.decide(sidecar, "SPEAKER_A", "Carol")
    assert review.archive_if_complete(sidecar) is None
    assert wav.exists()


def test_repair_paths_of_a_moved_audio(meeting):
    wav, sidecar, _txt = meeting
    review.decide(sidecar, "SPEAKER_A", "Carol")
    config.set_project_dir("test", wav.parent)
    moved = wav.parent / "archive" / wav.name
    moved.parent.mkdir()
    for f in (wav, sidecar):
        shutil.move(f, moved.parent / f.name)
    assert str(wav) in repair.broken_paths()

    r = repair.repair()
    assert [(old, new) for old, new, _refs in r["fixed"]] == [(str(wav), str(moved.resolve()))]
    assert repair.broken_paths() == {}
    assert voiceprints.load_samples("test")["Carol"][0]["origin"]["audio"] == str(moved.resolve())
