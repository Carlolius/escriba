# escriba

*[Leer en castellano](README.es.md)*

Record, transcribe and identify speakers in your meetings, on Windows and Linux.

- **Record** the call audio and your microphone together, without extra software.
- **Transcribe** in the cloud with AssemblyAI (~$0.23 per hour of audio) or locally with faster-whisper and pyannote.
- **Identify speakers** by voice, against a per-project library that improves each time you review a transcript.
- **Archive** reviewed meetings as Opus, about 15x smaller.

Browser interface and terminal menu, in English and Spanish.

![Recording a meeting](docs/screenshots/en/record.png)

## Before you record

Tell everyone you are recording; in many countries you need their consent. Voiceprints are biometric data (special category under the GDPR): keep the library private and delete a person's samples if they ask. Cloud mode sends the audio to AssemblyAI (USA); use local mode if it must not leave your organization. You are responsible for using escriba lawfully.

## Install

**Windows:** download the repository and run `install.ps1` (right-click > *Run with PowerShell*). It installs everything in your user folder, without admin rights, and creates an *Escriba* shortcut.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1           # cloud
powershell -ExecutionPolicy Bypass -File install.ps1 -Local    # cloud + local
powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
```

To update, close escriba and run the new version's `install.ps1`.

**Linux:** needs [`uv`](https://docs.astral.sh/uv/) and `libpulse`.

```bash
uv tool install --python 3.11 "escriba @ file://$PWD"
escriba install-local    # optional: local mode
```

## Usage

```bash
escriba web      # browser interface (http://127.0.0.1:8765)
escriba          # terminal menu
escriba --help   # commands
```

On first run, paste your AssemblyAI key in *Settings*.

<table>
<tr>
<td><img src="docs/screenshots/en/meetings.png" alt="Meetings"></td>
<td><img src="docs/screenshots/en/transcribe.png" alt="Transcribe"></td>
</tr>
<tr>
<td><img src="docs/screenshots/en/review.png" alt="Review"></td>
<td><img src="docs/screenshots/en/people.png" alt="People"></td>
</tr>
</table>

## Local mode

Optional, about 1.5 GB. Install it from *Settings*, with `escriba install-local` or with `install.ps1 -Local`. It also needs a [Hugging Face token](https://hf.co/settings/tokens) with the conditions of [speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) and [speaker-diarization-community-1](https://hf.co/pyannote/speaker-diarization-community-1) accepted.

On a CPU it takes about 1 h 15 min per hour of audio.

**NVIDIA GPU (experimental):** `escriba install-local --gpu` or `install.ps1 -Gpu` (~5 GB, driver 528+ on Windows, 525+ on Linux). Not yet tested on real hardware; if the GPU fails, escriba falls back to the CPU. Reports are welcome.

## Data

Recordings and transcripts stay in each project's folder. Voice libraries, glossary, keys and settings are in `%LOCALAPPDATA%\escriba` (Windows) or `~/.local/share/escriba` (Linux).

## Development

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]" pytest
.venv/bin/python -m pytest
```

Interface texts are in English inside `_()`, translated in `escriba/locales/<language>.json`.

Voiceprints use [Resemblyzer](https://github.com/resemble-ai/Resemblyzer)'s voice encoder (Apache-2.0), reimplemented in numpy.

## License

Licensed under either of [Apache License 2.0](LICENSE-APACHE) or [MIT license](LICENSE-MIT), at your option.
