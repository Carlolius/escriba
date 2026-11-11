"""GPU in local mode (experimental): detection, and that every failure falls
back to the CPU. No GPU is needed: whisper is replaced by a fake."""
import sys
import types

import pytest

from escriba import extras, gpu, local


def test_parse_nvidia_smi():
    card = gpu.parse_smi("NVIDIA GeForce RTX 3060, 550.120, 12288\n")
    assert card == {"name": "NVIDIA GeForce RTX 3060", "driver": "550.120", "memory_mb": 12288, "driver_ok": True}
    assert not gpu.parse_smi("Quadro K2000, 470.10, 2048")["driver_ok"]
    assert gpu.parse_smi("") is None


def test_setting_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ESCRIBA_GPU", "never")
    assert gpu.setting() == "never"
    assert not gpu.cuda_available()


def test_gpu_install_replaces_the_cpu_torch(tmp_path):
    cmd = extras.command("uv", tmp_path / "c.txt", gpu=True)
    assert cmd[cmd.index("--torch-backend") + 1] == gpu.TORCH_BACKEND == "cu126"  # CUDA 12, never 13
    assert cmd.count("--reinstall-package") == len(extras.TORCH)
    assert not any(p.lower().startswith("torch==") for p in extras._pinned(extras.TORCH))


class FakeWhisper:
    fail_on = set()   # devices whose model fails: "load", "detect" or "transcribe"
    made = []

    def __init__(self, model, device="cpu", **kwargs):
        self.device = device
        FakeWhisper.made.append(device)
        if (device, "load") in self.fail_on:
            raise RuntimeError("CUDA driver version is insufficient")

    def detect_language(self, audio):
        if (self.device, "detect") in self.fail_on:
            raise RuntimeError("Library cublas64_12.dll is not found")

    def transcribe(self, audio, **kwargs):
        info = types.SimpleNamespace(language="es", language_probability=0.9, duration=4.0)

        def segments():
            yield types.SimpleNamespace(start=0.0, end=2.0, text=" hola")
            if (self.device, "transcribe") in self.fail_on:
                raise RuntimeError("CUDA failed with error out of memory")
            yield types.SimpleNamespace(start=2.0, end=4.0, text=" adiós")

        return segments(), info


@pytest.fixture
def fake_whisper(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisper))
    monkeypatch.setattr(gpu, "cuda_available", lambda: True)
    monkeypatch.setattr(gpu, "prepare_libraries", lambda: None)
    monkeypatch.setattr(gpu, "nvidia", lambda: {"name": "Fake RTX", "memory_mb": 8000, "driver_ok": True})
    FakeWhisper.made = []
    return FakeWhisper


@pytest.mark.parametrize("failure, devices", [
    (set(), ["cuda"]),
    ({("cuda", "load")}, ["cuda", "cpu"]),
    ({("cuda", "detect")}, ["cuda", "cpu"]),
    ({("cuda", "transcribe")}, ["cuda", "cpu"]),
])
def test_falls_back_to_the_cpu(fake_whisper, tmp_path, failure, devices):
    fake_whisper.fail_on = failure
    out = tmp_path / "meeting.txt"
    local.transcribe(tmp_path / "meeting.wav", out)
    assert fake_whisper.made == devices
    text = out.read_text(encoding="utf-8")
    assert "hola" in text and "adiós" in text and text.count("hola") == 1
