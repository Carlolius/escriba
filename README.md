# escriba

*[Leer en castellano](README.es.md)*

Record, transcribe and identify speakers in your meetings, on Windows and Linux.

- **Record:** mixes what plays on your PC (the other people on the call) with your microphone into a 16 kHz mono WAV. WASAPI on Windows, PipeWire/PulseAudio on Linux. No ffmpeg needed.
- **Transcribe:** in the cloud with AssemblyAI (a few minutes, ~$0.23 per hour of audio) or locally with faster-whisper + pyannote (free, but ~1 h 15 min per hour of audio without an NVIDIA GPU).
- **Identify speakers:** by voice, against a per-project voice library that learns every time you review a transcript. Always done locally, also in cloud mode.
- **Archive:** once a meeting is reviewed, its WAV is compressed to Opus (~15x smaller).

It has a browser interface and a terminal menu, both in **English and Spanish**. It follows your system language; change it in *Settings*, in the terminal menu or with `escriba --lang en|es`.

## Before you record anyone

Recording a meeting and keeping voiceprints of the people in it has legal and ethical implications:

- **Tell everyone** you are recording before you start, and stop if someone objects. In many countries you need their consent.
- **Voiceprints are biometric data.** In the EU, an identifiable voice is personal data under the GDPR and voiceprints used to identify people are a special category. Keep the voice library private, don't share it, and delete a person's samples if they ask.
- **Cloud mode sends the audio out of your PC** to AssemblyAI (USA). escriba deletes the transcript and the uploaded audio from AssemblyAI as soon as it has the result, but if the meeting must not leave your organization, use local mode.

You are responsible for using escriba lawfully where you are.

## Install on Windows

Download this repository (or the .zip, unzipped), then right-click `install.ps1` > **Run with PowerShell**. Or, from PowerShell in that folder:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1           # cloud only
powershell -ExecutionPolicy Bypass -File install.ps1 -Local    # cloud + local
```

What it does, step by step:

1. **Installs [`uv`](https://docs.astral.sh/uv/)** if missing, with its official installer. uv is a Python manager: it downloads the Python version escriba needs without touching any other Python you have.
2. **Installs escriba** with `uv tool install`, in its own environment inside your user folder (no admin rights needed): Python 3.11 and every library, including the audio ones, torch for voiceprints (~200 MB) and the web interface. With `-Local`, also faster-whisper and pyannote (several GB more).
3. **Creates an "Escriba" shortcut** on the desktop and in the Start menu. It opens a black window (keep it open while you use escriba; closing it closes escriba) and your browser with the app. If escriba is already running, it just opens the browser.

Then:
- **First run:** go to *Settings* and paste your AssemblyAI key. It is stored in `%LOCALAPPDATA%\escriba\secrets.env`.
- **If the microphone records nothing:** Windows Settings > Privacy & security > Microphone > "Let desktop apps access your microphone".
- **Update:** run the script again.
- **Uninstall:** `install.ps1 -Uninstall`. Removes the program and the shortcuts; your data (voices, glossary, keys) stays in `%LOCALAPPDATA%\escriba`.

The script doesn't need git: if it's not next to the code, it downloads the repository .zip from GitHub (`-Source` to point to another folder or URL). Its messages are in Spanish if Windows is in Spanish.

Two Windows-specific details it takes care of:
- **`webrtcvad`:** resemblyzer asks for `webrtcvad`, which must be compiled on Windows. `webrtcvad-wheels` is installed instead: the same module, prebuilt.
- **Reading audio locally:** pyannote gets the audio already loaded; reading files itself would need the FFmpeg DLLs.

## Install on Linux

Requires [`uv`](https://docs.astral.sh/uv/) and `libpulse` (comes with PipeWire and PulseAudio).

```bash
uv tool install --python 3.11 "escriba @ file://$PWD"            # cloud only
uv tool install --python 3.11 "escriba[local] @ file://$PWD"     # cloud + local
```

On Linux, torch from PyPI ships NVIDIA support (~2 GB) even if you don't use it. To get the CPU-only build, install into a virtual environment instead:

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]"
```

## Usage

```bash
escriba web        # browser interface
escriba            # terminal menu
escriba --help     # one-off commands: record, transcribe, archive, enroll, repair, data
```

The web interface and the terminal menu do the same things and can be used at the same time. The web only listens on your own PC (`127.0.0.1:8765`), so nobody on your network can reach it. Closing the browser doesn't stop a recording or a transcription; closing the terminal window does stop a recording.

Each command has its own `--help`, e.g. `escriba transcribe --help`.

Background transcriptions keep going if you close the menu or the browser, and their progress (phase, %, time left) shows on top of the main menu and on the *Transcribe* page. Transcripts with speakers to review appear in *Review*, with a few sentences from each speaker so you can tell who it is without listening.

## Your data

Recordings and transcripts stay in the folders you choose for each project. Everything else lives in your data folder (`escriba data` shows it):

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\escriba` |
| Linux | `~/.local/share/escriba` |

Inside:
- `voiceprints/<project>.json`: voiceprints of real people (see above). Don't share them.
- `glossary.txt`: names and terms from your meetings; improves transcription in both modes.
- `secrets.env`: keys, one per line (`ASSEMBLYAI_API_KEY=...`, `HF_TOKEN=...`). An environment variable with the same name takes priority. If you already keep your keys in another `.env`, `secrets.env` can be a link to it: saving a key only changes its own line.
- `state.json`: last projects and folders used, transcriptions in progress, preferred devices, theme and language.

If you move meetings to another folder, their voice samples can no longer be played. *Repair paths* (in *People*, or `escriba repair`) finds them again by file name.

## Cloud mode (AssemblyAI)

Create an account at assemblyai.com (new accounts get $50 of credit) and paste the key in *Settings*.

escriba uploads an Opus copy of the audio, passes your glossary as key terms and, when done, deletes the transcript from AssemblyAI (neither the audio nor the text stays there). Transcription and speaker separation happen there; who is who is decided locally against your library.

Tested on 3 real meetings: more complete and with better proper names than local `medium`. With language "auto", a meeting mixing Galician and Spanish comes out in Spanish; with "gl" it keeps the mix, but in one test it merged two people into one speaker.

## Local mode (faster-whisper + pyannote)

Install with `-Local` (Windows) or the `local` extra (Linux) and, once:

1. Create a token at https://hf.co/settings/tokens
2. Accept the conditions at https://hf.co/pyannote/speaker-diarization-3.1 and https://hf.co/pyannote/speaker-diarization-community-1
3. Paste the token in *Settings* (`HF_TOKEN`)

It always runs at low priority, so your PC stays responsive while it works.

### Performance (Ryzen 5 5625U, CPU only)

Measured on 5 minutes of a real meeting (Oct 2026):

| Step | Time |
|---|---|
| Transcription, `medium` (default) | ~114 s |
| Transcription, `turbo` | ~93 s |
| Speaker diarization (pyannote 3.1) | ~250 s |

`turbo` (large-v3-turbo) gets more individual words right, but in tests it skipped a whole sentence, invented a final "Gracias." and turned a Galician meeting into Spanish. That's why `medium` stays the default.

Diarization is the bottleneck: almost all its time goes into voice embeddings. Spacing out its windows (`segmentation.step`) makes it up to 5x faster, but it ends up merging two people into one, so it's left as is. Running transcription and diarization in parallel only gains 4% and saturates the CPU.

## Voice identification

Each project (client, team...) has its own voice library, created when you create the project. When you review the speakers of a transcript, confirming or correcting a name adds that sample to the person; "I don't know" leaves the library untouched.

In *People* you can play, move or delete samples, delete a person, undo the last change, add a sample by hand, repair paths and audit the library (it flags samples that are too similar between two people, near-duplicates, and samples of the same person that don't match each other).

## Development

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]" pytest
.venv/bin/python -m pytest
```

CI runs the tests on Ubuntu and Windows, and runs `install.ps1` end to end on Windows (install, open the web, uninstall).

| Module | What it does |
|---|---|
| `config.py` | data folder, state, keys, glossary |
| `i18n.py`, `locales/` | interface language and translations |
| `record.py` | recording (soundcard) |
| `transcribe.py` | picks the engine, low priority |
| `cloud.py` / `local.py` | AssemblyAI / faster-whisper + pyannote |
| `speakers.py` | identify voices, write the .txt and .speakers.json |
| `review.py` | review decisions, feed the library |
| `voiceprints.py` | voice library and audit |
| `repair.py` | repair paths of moved meetings |
| `archive.py` / `audio.py` | Opus, duration, playback |
| `jobs.py` / `progress.py` | background transcriptions and their progress |
| `menu.py` / `cli.py` | terminal menu and commands |
| `web/` | web interface (NiceGUI), one page per section |

No logic module asks the user anything: the terminal menu and the web call the same functions.

### Translations

Every text the user sees is written in English inside `_()` (or `_n()` for plurals) and translated in `escriba/locales/<language>.json`, keyed by the English text. `tests/test_i18n.py` fails if a text has no Spanish translation or a translation is left over, so the two languages can't drift apart. To add a language, copy `es.json`, translate the values and add it to `LANGUAGES` in `i18n.py`.

## License

Licensed under either of [Apache License 2.0](LICENSE-APACHE) or [MIT license](LICENSE-MIT), at your option.

Unless you explicitly state otherwise, any contribution you submit for inclusion in escriba, as defined in the Apache-2.0 license, shall be dual licensed as above, without any additional terms or conditions.
