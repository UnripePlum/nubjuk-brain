from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PipelineKind = Literal["mock", "moonshine_tiny_ko"]
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LLAMA_CLI = str(_ROOT / ".tools" / "llama.cpp" / "bin" / "llama-cli")
DEFAULT_QWEN35_MODEL_PATH = str(_ROOT / "models" / "qwen3.5-0.8b" / "Qwen3.5-0.8B-Q4_K_M.gguf")


@dataclass(frozen=True)
class MockBrainConfig:
    pipeline: PipelineKind = "mock"
    intent: str = "roll_right"
    confidence: float = 0.92
    delay_ms: int = 0
    server_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")

    @classmethod
    def from_env(cls) -> "MockBrainConfig":
        return cls(
            intent=os.getenv("MOCK_BRAIN_INTENT", cls.intent),
            confidence=_float_from_env("MOCK_BRAIN_CONFIDENCE", cls.confidence),
            delay_ms=_int_from_env("MOCK_BRAIN_DELAY_MS", cls.delay_ms),
        )


@dataclass(frozen=True)
class MoonshineTinyKoConfig:
    pipeline: PipelineKind = "moonshine_tiny_ko"
    language: Literal["ko"] = "ko"
    model_arch: Literal["tiny"] = "tiny"
    model_dir: str | None = None
    intent_catalog_path: str | None = None
    max_audio_ms: int = 5000
    max_tokens_per_second: float = 13.0
    unknown_confidence: float = 0.2
    slm_enabled: bool = True
    slm_llama_cli: str = DEFAULT_LLAMA_CLI
    slm_model_path: str = DEFAULT_QWEN35_MODEL_PATH
    slm_timeout_ms: int = 5000
    slm_confidence: float = 0.78
    slm_min_catalog_confidence: float = 0.72
    slm_max_tokens: int = 16
    slm_context_size: int = 2048
    server_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if self.language != "ko":
            raise ValueError("language must be ko")
        if self.model_arch != "tiny":
            raise ValueError("model_arch must be tiny")
        if self.max_audio_ms <= 0:
            raise ValueError("max_audio_ms must be positive")
        if self.max_tokens_per_second <= 0:
            raise ValueError("max_tokens_per_second must be positive")
        if not 0 <= self.unknown_confidence <= 1:
            raise ValueError("unknown_confidence must be between 0 and 1")
        if self.slm_timeout_ms <= 0:
            raise ValueError("slm_timeout_ms must be positive")
        if not 0 <= self.slm_confidence <= 1:
            raise ValueError("slm_confidence must be between 0 and 1")
        if not 0 <= self.slm_min_catalog_confidence <= 1:
            raise ValueError("slm_min_catalog_confidence must be between 0 and 1")
        if self.slm_max_tokens <= 0:
            raise ValueError("slm_max_tokens must be positive")
        if self.slm_context_size <= 0:
            raise ValueError("slm_context_size must be positive")

    @classmethod
    def from_env(cls) -> "MoonshineTinyKoConfig":
        return cls(
            language=os.getenv("MOONSHINE_LANGUAGE", cls.language),
            model_arch=os.getenv("MOONSHINE_MODEL_ARCH", cls.model_arch),
            model_dir=os.getenv("MOONSHINE_MODEL_DIR") or None,
            intent_catalog_path=os.getenv("INTENT_CATALOG_PATH") or None,
            max_audio_ms=_int_from_env("MOONSHINE_MAX_AUDIO_MS", cls.max_audio_ms),
            max_tokens_per_second=_float_from_env(
                "MOONSHINE_MAX_TOKENS_PER_SECOND",
                cls.max_tokens_per_second,
            ),
            unknown_confidence=_float_from_env(
                "MOONSHINE_UNKNOWN_CONFIDENCE",
                cls.unknown_confidence,
            ),
            slm_enabled=_bool_from_env("BRAIN_SLM_ENABLED", cls.slm_enabled),
            slm_llama_cli=os.getenv("LLAMA_CLI", cls.slm_llama_cli),
            slm_model_path=os.getenv("QWEN35_MODEL_PATH", cls.slm_model_path),
            slm_timeout_ms=_int_from_env("BRAIN_SLM_TIMEOUT_MS", cls.slm_timeout_ms),
            slm_confidence=_float_from_env("BRAIN_SLM_CONFIDENCE", cls.slm_confidence),
            slm_min_catalog_confidence=_float_from_env(
                "BRAIN_SLM_MIN_CATALOG_CONFIDENCE",
                cls.slm_min_catalog_confidence,
            ),
            slm_max_tokens=_int_from_env("BRAIN_SLM_MAX_TOKENS", cls.slm_max_tokens),
            slm_context_size=_int_from_env("BRAIN_SLM_CONTEXT_SIZE", cls.slm_context_size),
        )


RuntimeConfig = MockBrainConfig | MoonshineTinyKoConfig


def load_config_from_env() -> RuntimeConfig:
    pipeline = os.getenv("BRAIN_PIPELINE", "mock")
    if pipeline == "mock":
        return MockBrainConfig.from_env()
    if pipeline == "moonshine_tiny_ko":
        return MoonshineTinyKoConfig.from_env()
    raise ValueError("BRAIN_PIPELINE must be one of: mock, moonshine_tiny_ko")


def _float_from_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
