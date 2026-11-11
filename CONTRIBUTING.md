# Contributing to escriba

Thanks for your interest. escriba is a hobby project maintained in spare time, so replies may take a while. Issues and pull requests are welcome, in English.

## Where help is most needed

- **NVIDIA GPU.** GPU support is experimental and has never run on real hardware. If you have an NVIDIA card, install with `escriba install-local --gpu` (or `install.ps1 -Gpu`), transcribe a meeting in local mode and [open an issue](https://github.com/Carlolius/escriba/issues) with your OS, the output of `nvidia-smi`, and the transcription log, whether the GPU worked or not.
- **Recording on Windows.** CI has no sound card, so recording on Windows has only been tested by hand on a few machines. Reports of what works and what doesn't (Windows version, audio devices, headphones or speakers) are very useful.
- **macOS.** Not supported yet. It needs a way to capture system audio and an install path. Please open an issue to discuss the approach before starting.

## Reporting a bug

Include your OS, escriba version, transcription mode (cloud or local), what you did, what happened, and any error from the terminal window.

> [!CAUTION]
> Never attach meeting recordings, transcripts or voice library files to an issue. They contain other people's voices and personal data. If a bug needs audio to reproduce, record a short clip of yourself.

## Pull requests

For anything beyond a small fix, open an issue first so we can agree on the approach.

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]" pytest
.venv/bin/python -m pytest
uvx ruff check
```

- Tests and `ruff check` must pass. CI runs the tests on Linux and Windows.
- Add tests for new behavior when practical.
- Code, comments and commit messages are in English.
- Every text shown to the user goes inside `_()` (or `_n()` for plurals) and needs its Spanish translation in `escriba/locales/es.json`. `tests/test_i18n.py` fails otherwise.
- Logic modules never prompt the user: the web interface and the terminal menu call the same functions.
- Keep the base install small. New heavy dependencies belong in the optional `local` extra.

By contributing, you agree that your contributions are dual licensed under [MIT](LICENSE-MIT) and [Apache 2.0](LICENSE-APACHE), like the rest of the project.
