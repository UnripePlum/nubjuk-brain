from __future__ import annotations

from pathlib import Path

from brain.intent.catalog import IntentCatalog


def test_nubjuk_motion_recipe_is_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "recipes" / "nubjuk_motion_catalog.json"

    catalog = IntentCatalog.from_path(path)
    roll_right = catalog.match("오른쪽으로 굴러", unknown_confidence=0.2)
    roll_right_asr_variant = catalog.match("울어 굴러.", unknown_confidence=0.2)
    roll_left = catalog.match("좌로 글로", unknown_confidence=0.2)
    roll_left_observed_noise = catalog.match("잘 어울려.", unknown_confidence=0.2)
    roll_left_observed_noise_variant = catalog.match("잘 어글러", unknown_confidence=0.2)
    sit = catalog.match("앉아.", unknown_confidence=0.2)
    sit_asr_variant = catalog.match("안 자.", unknown_confidence=0.2)
    sit_observed_noise = catalog.match("환자", unknown_confidence=0.2)
    stand = catalog.match("너 저기 일어서", unknown_confidence=0.2)
    idle = catalog.match("가만히 있어", unknown_confidence=0.2)
    give_hand = catalog.match("손 줘", unknown_confidence=0.2)
    surprise = catalog.match("어흥", unknown_confidence=0.2)
    surprise_variant = catalog.match("왁", unknown_confidence=0.2)
    role_right = catalog.match("role right", unknown_confidence=0.2)
    role_left = catalog.match("role left", unknown_confidence=0.2)

    assert catalog.version == "nubjuk-motion-2026-05-06.4"
    assert catalog.intent_count == 7
    assert catalog.intent_ids == (
        "idle",
        "sit",
        "stand",
        "roll_left",
        "roll_right",
        "give_hand",
        "surprise",
    )
    assert roll_right.intent == "roll_right"
    assert roll_right_asr_variant.intent == "roll_right"
    assert roll_right_asr_variant.confidence == 0.94
    assert roll_left.intent == "roll_left"
    assert roll_left.confidence == 0.72
    assert roll_left_observed_noise.intent == "roll_left"
    assert roll_left_observed_noise_variant.intent == "roll_left"
    assert sit.intent == "sit"
    assert sit_asr_variant.intent == "sit"
    assert sit_observed_noise.intent == "sit"
    assert stand.intent == "stand"
    assert stand.confidence == 0.86
    assert idle.intent == "idle"
    assert give_hand.intent == "give_hand"
    assert surprise.intent == "surprise"
    assert surprise_variant.intent == "surprise"
    assert role_right.intent == "roll_right"
    assert role_left.intent == "roll_left"
