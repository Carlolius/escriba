"""Local transcription: faster-whisper + diarization with pyannote.

Free, and the audio never leaves the PC, but slow on the CPU (on a Ryzen 5
5625U, ~1 h 15 min per hour of audio with speaker identification). With an
NVIDIA card and torch's CUDA build it uses the GPU (experimental, see gpu.py);
if anything fails there, it goes on with the CPU.
Needs the "local" extra (faster-whisper, pyannote.audio) and, to separate
speakers, an HF_TOKEN with pyannote's conditions accepted.
"""
import warnings

import psutil

from . import config, gpu, speakers as speakers_mod
from .i18n import _
from .progress import Progress, phase

BEAM_SIZE = 5


def threads():
    # Physical cores: at low priority, using all of them doesn't make the rest
    # of the PC sluggish, and the extra logical threads barely speed up whisper.
    return psutil.cpu_count(logical=False) or 4


def _cpu_model(model):
    from faster_whisper import WhisperModel
    return WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads(), num_workers=1)


def _gpu_model(model):
    """Whisper on the GPU, already tried on a bit of silence so that missing
    libraries or too little memory show up now and not halfway through. None
    if it doesn't work."""
    import numpy as np
    from faster_whisper import WhisperModel

    try:
        gpu.prepare_libraries()
        card = gpu.nvidia() or {}
        whisper = WhisperModel(model, device="cuda", compute_type=gpu.whisper_compute_type(card.get("memory_mb", 0)))
        whisper.detect_language(np.zeros(16000 * 2, dtype="float32"))
        return whisper
    except Exception as e:
        print(_("WARNING: the GPU didn't work ({error}): using the CPU", error=e), flush=True)
        return None


def _run_whisper(whisper, audio, kwargs, progress):
    raw_segments, info = whisper.transcribe(str(audio), **kwargs)
    print(_("Detected language: {language} ({probability:.0%}), duration: {seconds:.0f}s",
            language=info.language, probability=info.language_probability, seconds=info.duration), flush=True)
    segments = []
    progress.update("transcribe", 0, info.duration)  # start the clock before the first segment
    for s in raw_segments:
        segments.append((s.start, s.end, s.text.strip()))
        progress.update("transcribe", s.end, info.duration)
    progress.update("transcribe", info.duration, info.duration)
    return segments


def transcribe(audio, out, model="medium", language="auto", prompt="", diarize=False, project="", speakers=()):
    warnings.filterwarnings("ignore", category=UserWarning)  # pyannote/torch noise in the log

    progress = Progress()
    phase("loading_model")
    print(_("Loading model {model}...", model=model), flush=True)
    use_gpu = gpu.cuda_available()
    whisper = _gpu_model(model) if use_gpu else None
    if whisper:
        print(_("Using the GPU: {name} (experimental)", name=gpu.describe()), flush=True)
    else:
        use_gpu = False
        whisper = _cpu_model(model)

    kwargs = dict(beam_size=BEAM_SIZE, vad_filter=True, condition_on_previous_text=False)
    if language and language != "auto":
        kwargs["language"] = language
    if prompt:
        kwargs["initial_prompt"] = prompt

    try:
        segments = _run_whisper(whisper, audio, kwargs, progress)
    except Exception as e:
        if not use_gpu:
            raise
        # Out of memory halfway, a library loaded late...: start again on the CPU
        print(_("WARNING: the GPU failed while transcribing ({error}): starting again on the CPU", error=e),
              flush=True)
        use_gpu = False
        del whisper
        segments = _run_whisper(_cpu_model(model), audio, kwargs, progress)

    turns, names = None, None
    if diarize:
        turns = _diarize(audio, speakers, progress, use_gpu)
        progress.close()  # stop redrawing the bars before printing the matches
        if turns:
            names = speakers_mod.name_speakers(str(audio), str(out), turns, project, list(speakers))

    progress.close()
    speakers_mod.write_transcript(str(out), segments, turns, names)


def _diarize(audio, speakers, progress, use_gpu=False):
    hf_token = config.read_secret("HF_TOKEN")
    if not hf_token:
        print(_("WARNING: HF_TOKEN is missing: speakers won't be separated"))
        return None
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print(_("WARNING: pyannote.audio is not installed: speakers won't be separated (install the 'local' extra)"))
        return None
    phase("diarizing")
    print(_("Running diarization (usually takes longer than the transcription)..."), flush=True)
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=hf_token)
    kwargs = {"num_speakers": len(speakers)} if speakers else {}
    # Audio already loaded in memory: given a path, pyannote 4 would read it
    # with torchcodec, which on Windows needs the FFmpeg DLLs installed separately
    import soundfile as sf
    import torch
    data, sr = sf.read(str(audio), dtype="float32", always_2d=True)
    waveform = {"waveform": torch.from_numpy(data.mean(axis=1, keepdims=True).T.copy()), "sample_rate": sr}
    if use_gpu:
        try:
            pipeline.to(torch.device("cuda"))
            diarization = pipeline(waveform, hook=progress.pyannote_hook(), **kwargs)
        except Exception as e:
            print(_("WARNING: the GPU failed while separating speakers ({error}): starting again on the CPU",
                    error=e), flush=True)
            pipeline.to(torch.device("cpu"))
            diarization = pipeline(waveform, hook=progress.pyannote_hook(), **kwargs)
    else:
        diarization = pipeline(waveform, hook=progress.pyannote_hook(), **kwargs)
    return [(t.start, t.end, s) for t, _unused, s in diarization.speaker_diarization.itertracks(yield_label=True)]
