"""The parts of transcription that need neither network nor models."""
import os

from escriba import cloud, config, i18n, jobs, speakers, transcribe


def test_write_transcript_with_speakers(tmp_path):
    out = tmp_path / "r.txt"
    segments = [(0.0, 2.0, "Hello."), (2.0, 4.0, "How are you?"), (5.0, 7.0, "Fine.")]
    turns = [(0.0, 4.1, "A"), (4.5, 8.0, "B")]
    speakers.write_transcript(str(out), segments, turns, {"A": "Ana", "B": "Bea"})
    assert out.read_text(encoding="utf-8") == "\n[0s] Ana:\nHello.\n[2s] How are you?\n\n[5s] Bea:\nFine.\n"


def test_unrecognised_speakers_are_named_in_the_interface_language():
    assert speakers._fallback_name(["Ana"], 1) == "Ana"
    assert speakers._fallback_name(["Ana"], 2) == "Speaker 2"
    i18n.set_language("es")
    assert speakers._fallback_name([], 1) == "Hablante 1"


def test_segments_from_assemblyai_words():
    words = [
        {"text": "Hello", "start": 0, "end": 300, "speaker": "A"},
        {"text": "everyone.", "start": 300, "end": 600, "speaker": "A"},
        {"text": "Hi", "start": 900, "end": 1200, "speaker": "B"},
    ]
    assert cloud.segments_from_words(words) == [(0.0, 0.6, "Hello everyone."), (0.9, 1.2, "Hi")]


def test_glossary_for_the_cloud_and_for_whisper():
    config.glossary_path().write_text("Ana, Acme Ltd\na sentence far too long to be a key term at all\n",
                                      encoding="utf-8")
    assert cloud.key_terms() == ["Ana", "Acme Ltd"]
    assert transcribe.glossary_prompt("es") == "Reunión de trabajo. Términos y nombres propios: Ana, Acme Ltd, " \
                                               "a sentence far too long to be a key term at all."
    assert transcribe.glossary_prompt("auto").startswith("Work meeting. Terms and proper names: Ana")


def test_missing_key():
    assert transcribe.missing_key("cloud") == "ASSEMBLYAI_API_KEY"
    config.save_secret("ASSEMBLYAI_API_KEY", "x")
    assert transcribe.missing_key("cloud") is None
    assert transcribe.missing_key("local") == "HF_TOKEN"


def test_progress_from_log(tmp_path):
    log = tmp_path / "t.log"
    cases = [
        ("Loading model medium...\n[phase] loading_model\n", "loading model..."),
        ("[progress] transcribe 50% 1:00 ~1:00\n", "transcribing 50% (step 1/2) · ~5 min left"),
        ("[phase] diarizing\n", "preparing speaker identification (step 2/2)"),
        ("[progress] segment 30% 0:10 ~0:20\n", "identifying speakers 0% (step 2/2)"),
        ("[progress] embed 40% 2:00 ~3:00\n", "identifying speakers 40% (step 2/2) · ~3 min left"),
        ("[progress] upload 35% 0:05 ~0:10\n", "uploading audio 35% (cloud)"),
        ("[phase] cloud_waiting\n[cloud] processing 0:42\n", "processing in the cloud (0:42)"),
        ("[cloud] processing 0:42\n[phase] cloud_done\n", "identifying voices (cloud part done)"),
    ]
    for lines, expected in cases:
        log.write_text(lines, encoding="utf-8")
        assert jobs.progress_from_log(log) == expected
    # The log format doesn't depend on the language; only the text shown does
    i18n.set_language("es")
    assert jobs.progress_from_log(log) == "identificando por voz (nube ya terminada)"


def test_untranscribed(wav):
    a = wav("a.wav")
    b = wav("b.wav", folder=a.parent / "sub")
    a.with_suffix(".txt").write_text("already transcribed", encoding="utf-8")
    todo = jobs.untranscribed(a.parent)
    assert [p for p, _dur in todo] == [b]
    assert abs(todo[0][1] - 5.0) < 0.01


def test_low_priority_doesnt_fail():
    transcribe.low_priority()
    if os.name != "nt":
        assert os.nice(0) > 0
