from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MockBrainConfig:
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
