from __future__ import annotations

import pytest

from brain.config import MockBrainConfig


def test_config_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        MockBrainConfig(confidence=1.1)


def test_config_rejects_negative_delay() -> None:
    with pytest.raises(ValueError, match="delay_ms"):
        MockBrainConfig(delay_ms=-1)

