from __future__ import annotations

import pytest

from brain.config import MockBrainConfig, MoonshineTinyKoConfig, load_config_from_env


def test_config_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        MockBrainConfig(confidence=1.1)


def test_config_rejects_negative_delay() -> None:
    with pytest.raises(ValueError, match="delay_ms"):
        MockBrainConfig(delay_ms=-1)


def test_config_loads_moonshine_tiny_ko_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN_PIPELINE", "moonshine_tiny_ko")
    monkeypatch.setenv("INTENT_CATALOG_PATH", "/tmp/intent-catalog.json")
    monkeypatch.setenv("MOONSHINE_MAX_AUDIO_MS", "3000")
    monkeypatch.setenv("BRAIN_SLM_ENABLED", "true")
    monkeypatch.setenv("LLAMA_CLI", "/tmp/llama-cli")
    monkeypatch.setenv("QWEN35_MODEL_PATH", "/tmp/qwen.gguf")
    monkeypatch.setenv("BRAIN_SLM_TIMEOUT_MS", "7000")
    config = load_config_from_env()
    assert isinstance(config, MoonshineTinyKoConfig)
    assert config.pipeline == "moonshine_tiny_ko"
    assert config.language == "ko"
    assert config.model_arch == "tiny"
    assert config.intent_catalog_path == "/tmp/intent-catalog.json"
    assert config.max_audio_ms == 3000
    assert config.slm_enabled is True
    assert config.slm_llama_cli == "/tmp/llama-cli"
    assert config.slm_model_path == "/tmp/qwen.gguf"
    assert config.slm_timeout_ms == 7000


def test_config_rejects_unknown_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN_PIPELINE", "base_ko")
    with pytest.raises(ValueError, match="BRAIN_PIPELINE"):
        load_config_from_env()


def test_moonshine_config_rejects_non_tiny_model() -> None:
    with pytest.raises(ValueError, match="model_arch"):
        MoonshineTinyKoConfig(model_arch="base")  # type: ignore[arg-type]


def test_config_rejects_invalid_slm_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN_PIPELINE", "moonshine_tiny_ko")
    monkeypatch.setenv("BRAIN_SLM_ENABLED", "maybe")

    with pytest.raises(ValueError, match="BRAIN_SLM_ENABLED"):
        load_config_from_env()


def test_moonshine_config_rejects_invalid_slm_timeout() -> None:
    with pytest.raises(ValueError, match="slm_timeout_ms"):
        MoonshineTinyKoConfig(slm_timeout_ms=0)
