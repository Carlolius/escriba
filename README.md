# escriba

*[Leer en castellano](README.es.md)*

Record, transcribe and identify speakers in your meetings, on Windows and Linux.

- **Record:** mixes what plays on your PC (the other people on the call) with your microphone into a 16 kHz mono WAV. WASAPI on Windows, PipeWire/PulseAudio on Linux. No ffmpeg needed.
- **Transcribe:** in the cloud with AssemblyAI (a few minutes, ~$0.23 per hour of audio) or locally with faster-whisper + pyannote (free, but ~1 h 15 min per hour of audio without an NVIDIA GPU).
- **Identify speakers:** by voice, against a per-project voice library that learns every time you review a transcript. Always done locally, also in cloud mode.
- **Archive:** once a meeting is reviewed, its WAV is compressed to Opus (~15x smaller).

![Recording a meeting: level meters for what plays and for the microphone](docs/screenshots/en/record.png)

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
powershell -ExecutionPolicy Bypass -File install.ps1 -Gpu      # cloud + local on an NVIDIA card (experimental)
```

What it does, step by step:

1. **Installs [`uv`](https://docs.astral.sh/uv/)** if missing, with its official installer. uv is a Python manager: it downloads the Python version escriba needs without touching any other Python you have.
2. **Installs escriba** with `uv tool install`, in its own environment inside your user folder (no admin rights needed): Python 3.11 and every library, including the audio ones and the web interface: ~150 MB in all. With `-Local`, also faster-whisper and pyannote (~1.5 GB more); you can also add them later from *Settings*.
3. **Creates an "Escriba" shortcut** on the desktop and in the Start menu. It opens a black window (keep it open while you use escriba; closing it closes escriba) and your browser with the app. If escriba is already running, it just opens the browser.

Then:
- **First run:** go to *Settings* and paste your AssemblyAI key. It is stored in `%LOCALAPPDATA%\escriba\secrets.env`.
- **If the microphone records nothing:** Windows Settings > Privacy & security > Microphone > "Let desktop apps access your microphone".
- **Update:** run the script again. If local mode is installed, it is kept.
- **Uninstall:** `install.ps1 -Uninstall`. Removes the program and the shortcuts; your data (voices, glossary, keys) stays in `%LOCALAPPDATA%\escriba`.

The script doesn't need git: if it's not next to the code, it downloads the repository .zip from GitHub (`-Source` to point to another folder or URL). Its messages are in Spanish if Windows is in Spanish.

One Windows-specific detail it takes care of: in local mode, pyannote gets the audio already loaded, because reading files itself would need the FFmpeg DLLs.

## Install on Linux

Requires [`uv`](https://docs.astral.sh/uv/) and `libpulse` (comes with PipeWire and PulseAudio).

```bash
uv tool install --python 3.11 "escriba @ file://$PWD"     # cloud only, ~150 MB
escriba install-local                                       # optional: add local mode
```

`escriba install-local` (or *Settings* > *Transcribe on this PC*) adds faster-whisper and pyannote with the CPU-only torch, ~1.5 GB. Installing the `local` extra directly with `uv tool install` also works, but on Linux torch from PyPI brings NVIDIA support (~2 GB more) that escriba doesn't use.

## Usage

```bash
escriba web        # browser interface
escriba            # terminal menu
escriba --help     # one-off commands: record, transcribe, archive, enroll, repair, install-local, data
```

The web interface and the terminal menu do the same things and can be used at the same time. The web only listens on your own PC (`127.0.0.1:8765`), so nobody on your network can reach it. Closing the browser doesn't stop a recording or a transcription; closing the terminal window does stop a recording.

Each command has its own `--help`, e.g. `escriba transcribe --help`.

In the web, the project you work on is chosen in the top bar (type a new name to create one); every page shows that project. *Meetings* lists what's recorded in its folder, with its state, a player and the transcript, and lets you delete a meeting (for instance a test) with its files and, if you want, the voice samples taken from it. *Transcribe* shows the running transcriptions of every project, step by step. The terminal menu has the same *Meetings* list.

Background transcriptions keep going if you close the menu or the browser, and their progress (phase, %, time left) shows on top of the main menu and on the *Transcribe* page. Transcripts with speakers to review appear in *Review*, with a few sentences from each speaker so you can tell who it is without listening.

### Screenshots

Made with invented demo data.

<table>
<tr>
<td><img src="docs/screenshots/en/meetings.png" alt="Meetings of a project and their state"></td>
<td><img src="docs/screenshots/en/transcribe.png" alt="Transcriptions running, step by step"></td>
</tr>
<tr>
<td><img src="docs/screenshots/en/review.png" alt="Reviewing who each voice is"></td>
<td><img src="docs/screenshots/en/people.png" alt="Auditing the voice library"></td>
</tr>
</table>

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

It's optional. Install it from *Settings* > *Transcribe on this PC*, with `escriba install-local`, or with `install.ps1 -Local`: ~1.5 GB of libraries, added to escriba's environment without touching what's installed, so it works while escriba is running. Each whisper model is downloaded the first time it's used (`medium`, the default, ~1.5 GB).

Then, once:

1. Create a token at https://hf.co/settings/tokens
2. Accept the conditions at https://hf.co/pyannote/speaker-diarization-3.1 and https://hf.co/pyannote/speaker-diarization-community-1
3. Paste the token in *Settings* (`HF_TOKEN`)

It always runs at low priority, so your PC stays responsive while it works.

### NVIDIA GPU (experimental)

With an NVIDIA card, local mode can use it: transcription and diarization go from more than an hour per hour of audio to a few minutes. When installing local mode, escriba offers the GPU version if it finds a card (`nvidia-smi`); if local mode is already installed for the CPU, *Settings* has a button to switch. From the command line: `escriba install-local --gpu`, or `install.ps1 -Gpu` on Windows.

- **It's experimental:** the authors have no NVIDIA card and CI has no GPU, so it hasn't run on real hardware yet. If you try it, please report how it went.
- **It never makes things worse:** if the GPU fails (driver too old, too little memory, a missing library), escriba says so in the log and goes on with the CPU. *Settings* > *CPU only*, or `escriba transcribe --local --cpu`, turns it off.
- **Requirements:** NVIDIA driver 528 or newer on Windows, 525 or newer on Linux. AMD and Intel cards aren't supported (faster-whisper only runs on CUDA).
- **Size:** ~5 GB instead of ~1.5 GB. torch is installed for CUDA 12.6, not 13: faster-whisper's engine (CTranslate2 4.x) needs cuBLAS 12 and cuDNN 9, which come with that torch.

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

Voiceprints are computed on your PC in both modes, with [Resemblyzer](https://github.com/resemble-ai/Resemblyzer)'s pretrained voice encoder (Apache-2.0) rewritten in numpy (`encoder.py`): it gives the same embeddings as the original (checked on 158 real clips, difference below 1e-6) without torch, which keeps the base install at ~150 MB instead of ~1.2 GB.

In *People* you can play, move or delete samples, rename a person (also in the project's transcripts; if the new name exists, both join), delete a person, undo the last change, add a sample by hand, repair paths and audit the library (it flags samples that are too similar between two people, near-duplicates, and samples of the same person that don't match each other).

## Development

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]" pytest
.venv/bin/python -m pytest
```

`tools/export_voice_encoder.py` regenerates `escriba/models/voice_encoder.npz` from Resemblyzer's weights; `tests/test_encoder.py` checks the numpy encoder still matches it.

CI runs the tests on Ubuntu and Windows, and runs `install.ps1` end to end on Windows (install, open the web, uninstall).

| Module | What it does |
|---|---|
| `config.py` | data folder, state, keys, glossary |
| `i18n.py`, `locales/` | interface language and translations |
| `record.py` | recording (soundcard) |
| `transcribe.py` | picks the engine, low priority |
| `extras.py` / `gpu.py` | installs local mode afterwards / NVIDIA GPU, with CPU fallback |
| `cloud.py` / `local.py` | AssemblyAI / faster-whisper + pyannote |
| `speakers.py` | identify voices, write the .txt and .speakers.json |
| `review.py` | review decisions, feed the library |
| `encoder.py`, `models/` | voiceprints with numpy (Resemblyzer's model) |
| `voiceprints.py` | voice library and audit |
| `meetings.py` | a folder's meetings, their state, deleting one |
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
