from __future__ import annotations

from brain.intent.catalog import IntentCatalog
from brain.pipeline.qwen_slm import (
    build_intent_prompt,
    compact_slm_output,
    extract_slm_completion,
    parse_intent_from_slm_output,
)


def test_parse_intent_from_slm_output_uses_last_valid_intent() -> None:
    output = "Valid ids: roll_right, roll_left, sit, unknown\n\nIntent id:\nroll_left\n"

    intent = parse_intent_from_slm_output(output, ("roll_right", "roll_left", "sit"))

    assert intent == "roll_left"


def test_parse_intent_from_slm_output_returns_unknown_for_invalid_output() -> None:
    output = "I cannot decide."

    intent = parse_intent_from_slm_output(output, ("roll_right", "roll_left", "sit"))

    assert intent == "unknown"


def test_build_intent_prompt_mentions_pronunciation() -> None:
    catalog = IntentCatalog.from_dict(
        {
            "catalog_version": "prompt",
            "intents": [
                {"id": "roll_left", "aliases": ["좌로 굴러"], "description": "Roll left."},
            ],
        }
    )

    prompt = build_intent_prompt("좌로 글로", catalog)

    assert "pronunciation" in prompt
    assert "좌로 글로" in prompt
    assert "Current pronunciation candidates:" in prompt
    assert "- roll_left: alias=좌로 굴러" in prompt
    assert "roll_left" in prompt
    assert "좌로 굴러" in prompt


def test_build_intent_prompt_includes_observed_asr_noise_examples() -> None:
    catalog = IntentCatalog.from_dict(
        {
            "catalog_version": "prompt",
            "intents": [
                {"id": "roll_right", "aliases": ["오른쪽으로 굴러"]},
                {"id": "roll_left", "aliases": ["좌로 굴러"]},
                {"id": "idle", "aliases": ["가만히 있어"]},
                {"id": "sit", "aliases": ["앉아"]},
                {"id": "stand", "aliases": ["일어서"]},
                {"id": "give_hand", "aliases": ["손 줘"]},
            ],
        }
    )

    prompt = build_intent_prompt("우러글라?", catalog)

    assert "ASR text: 우러글라 -> roll_right" in prompt
    assert "ASR text: 울어 굴러 -> roll_right" in prompt
    assert "ASR text: 좌로 글로 -> roll_left" in prompt
    assert "ASR text: 잘 어울려 -> roll_left" in prompt
    assert "ASR text: 잘 어글러 -> roll_left" in prompt
    assert "ASR text: 안 자 -> sit" in prompt
    assert "ASR text: 너 저기 일어서 -> stand" in prompt
    assert "ASR text: 손 줘 -> give_hand" in prompt
    assert "ASR text: 가만히 있어 -> idle" in prompt
    assert 'Current ASR text: "우러글라?"' in prompt


def test_extract_slm_completion_removes_llama_cli_noise() -> None:
    output = "metal logs\n> prompt text\nIntent id:\nroll_right\n[ Prompt: 100 t/s ]\nExiting...\n"

    completion = extract_slm_completion(output)

    assert completion == "roll_right"


def test_compact_slm_output_collapses_and_truncates() -> None:
    output = "  roll_left\n\n" + ("x" * 500)

    compact = compact_slm_output(output, limit=20)

    assert compact == "roll_left xxxxxxxxxx..."
