from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.intent.catalog import IntentCatalog, load_intent_catalog


def test_default_catalog_matches_roll_right_alias() -> None:
    catalog = load_intent_catalog()

    exact = catalog.match("오른쪽으로 굴러", unknown_confidence=0.2)
    partial = catalog.match("지금 오른쪽으로 굴러", unknown_confidence=0.2)

    assert catalog.version == "2026-05-06.4"
    assert exact.intent == "roll_right"
    assert exact.confidence == 0.94
    assert partial.intent == "roll_right"
    assert partial.confidence == 0.86


def test_default_catalog_matches_sit_alias_with_punctuation() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("앉아.", unknown_confidence=0.2)

    assert match.intent == "sit"
    assert match.confidence == 0.94


def test_default_catalog_matches_sit_asr_variant() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("안 자.", unknown_confidence=0.2)

    assert match.intent == "sit"
    assert match.confidence == 0.94


def test_default_catalog_matches_short_sit_phonetic_asr_variant() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("은자", unknown_confidence=0.2)
    candidates = catalog.pronunciation_candidates("은자")

    assert match.intent == "sit"
    assert match.confidence == 0.72
    assert candidates[0].intent == "sit"


@pytest.mark.parametrize("text", ["인자", "환자", "아니다"])
def test_default_catalog_matches_observed_sit_asr_noise(text: str) -> None:
    catalog = load_intent_catalog()

    match = catalog.match(text, unknown_confidence=0.2)

    assert match.intent == "sit"
    assert match.confidence == 0.86


def test_default_catalog_matches_roll_left_phonetic_asr_variant() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("좌로 글로", unknown_confidence=0.2)

    assert match.intent == "roll_left"
    assert match.confidence == 0.72


def test_default_catalog_matches_observed_roll_left_asr_noise() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("잘 어울려.", unknown_confidence=0.2)
    variant = catalog.match("잘 어글러", unknown_confidence=0.2)

    assert match.intent == "roll_left"
    assert match.confidence == 0.86
    assert variant.intent == "roll_left"
    assert variant.confidence == 0.86


def test_default_catalog_matches_roll_right_asr_variant() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("울어 굴러.", unknown_confidence=0.2)

    assert match.intent == "roll_right"
    assert match.confidence == 0.94


def test_default_catalog_matches_stand_phrase() -> None:
    catalog = load_intent_catalog()

    match = catalog.match("너 저기 일어서", unknown_confidence=0.2)

    assert match.intent == "stand"
    assert match.confidence == 0.86


def test_default_catalog_matches_idle_give_hand_and_surprise() -> None:
    catalog = load_intent_catalog()

    idle = catalog.match("가만히 있어", unknown_confidence=0.2)
    give_hand = catalog.match("손 줘", unknown_confidence=0.2)
    surprise = catalog.match("어흥", unknown_confidence=0.2)
    surprise_variant = catalog.match("왁", unknown_confidence=0.2)
    old_surprise_command = catalog.match("놀라", unknown_confidence=0.2)

    assert idle.intent == "idle"
    assert give_hand.intent == "give_hand"
    assert surprise.intent == "surprise"
    assert surprise_variant.intent == "surprise"
    assert old_surprise_command.intent == "unknown"


def test_catalog_can_be_loaded_from_local_json(tmp_path: Path) -> None:
    path = tmp_path / "intent_catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_version": "local-test",
                "intents": [
                    {
                        "id": "wave_hand",
                        "aliases": ["손 흔들어", "인사해"],
                        "description": "Wave hand.",
                        "confidence": 0.81,
                        "exact_confidence": 0.93,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_intent_catalog(str(path))
    exact = catalog.match("손 흔들어", unknown_confidence=0.2)
    partial = catalog.match("지금 인사해", unknown_confidence=0.2)

    assert catalog.version == "local-test"
    assert exact.intent == "wave_hand"
    assert exact.confidence == 0.93
    assert partial.intent == "wave_hand"
    assert partial.confidence == 0.81


def test_catalog_uses_phonetic_fallback_for_korean_aliases() -> None:
    catalog = IntentCatalog.from_dict(
        {
            "catalog_version": "phonetic",
            "intents": [
                {
                    "id": "roll_left",
                    "aliases": ["좌로 굴러"],
                    "phonetic_confidence": 0.71,
                }
            ],
        }
    )

    match = catalog.match("좌로 글로", unknown_confidence=0.2)

    assert match.intent == "roll_left"
    assert match.confidence == 0.71


def test_catalog_exposes_pronunciation_candidates_for_slm_prompt() -> None:
    catalog = load_intent_catalog()

    candidates = catalog.pronunciation_candidates("좌로 글로")

    assert candidates[0].intent == "roll_left"
    assert candidates[0].alias == "좌로 굴러"
    assert candidates[0].score >= 0.76


def test_catalog_rejects_duplicate_aliases() -> None:
    with pytest.raises(ValueError, match="duplicate alias"):
        IntentCatalog.from_dict(
            {
                "catalog_version": "bad",
                "intents": [
                    {"id": "roll_right", "aliases": ["오른쪽"]},
                    {"id": "turn_right", "aliases": ["오른쪽"]},
                ],
            }
        )


def test_catalog_partial_match_prefers_longer_alias() -> None:
    catalog = IntentCatalog.from_dict(
        {
            "catalog_version": "longest-match",
            "intents": [
                {"id": "roll_right", "aliases": ["오른쪽"]},
                {"id": "wave_right_hand", "aliases": ["오른쪽 손 흔들어"]},
            ],
        }
    )

    match = catalog.match("지금 오른쪽 손 흔들어 줘", unknown_confidence=0.2)

    assert match.intent == "wave_right_hand"
