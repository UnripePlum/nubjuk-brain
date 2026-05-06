from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_CATALOG_RESOURCE = "default_catalog.json"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntentRecipe(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    aliases: list[str] = Field(min_length=1)
    asr_noise: list[str] = Field(default_factory=list)
    description: str = ""
    slots: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.86, ge=0, le=1)
    exact_confidence: float = Field(default=0.94, ge=0, le=1)
    phonetic_confidence: float = Field(default=0.72, ge=0, le=1)


class IntentCatalogData(StrictModel):
    catalog_version: str = Field(min_length=1)
    intents: list[IntentRecipe] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_intents_and_aliases(self) -> "IntentCatalogData":
        seen_ids: set[str] = set()
        seen_aliases: dict[str, str] = {}
        for intent in self.intents:
            if intent.id in seen_ids:
                raise ValueError(f"duplicate intent id: {intent.id}")
            seen_ids.add(intent.id)
            for alias in [*intent.aliases, *intent.asr_noise]:
                normalized = normalize_text(alias).replace(" ", "")
                if not normalized:
                    raise ValueError(f"empty alias for intent: {intent.id}")
                existing = seen_aliases.get(normalized)
                if existing is not None:
                    raise ValueError(f"duplicate alias across intents: {alias} ({existing}, {intent.id})")
                seen_aliases[normalized] = intent.id
        return self


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    confidence: float
    slots: dict[str, Any]


@dataclass(frozen=True)
class IntentCandidate:
    intent: str
    aliases: tuple[str, ...]
    description: str
    slots: dict[str, Any]


@dataclass(frozen=True)
class PronunciationCandidate:
    intent: str
    alias: str
    score: float


class IntentCatalog:
    def __init__(self, data: IntentCatalogData) -> None:
        self._data = data
        self._recipes = list(data.intents)
        self._recipes_by_id = {recipe.id: recipe for recipe in self._recipes}
        self._exact_aliases: dict[str, IntentRecipe] = {}
        self._exact_asr_noise: dict[str, IntentRecipe] = {}
        self._partial_aliases: list[tuple[str, IntentRecipe]] = []
        self._phonetic_aliases: list[tuple[str, str, IntentRecipe]] = []
        for recipe in self._recipes:
            for alias in recipe.aliases:
                alias_compact = normalize_text(alias).replace(" ", "")
                self._exact_aliases[alias_compact] = recipe
                self._partial_aliases.append((alias_compact, recipe))
                if _hangul_syllable_count(alias_compact) >= 2:
                    self._phonetic_aliases.append((alias_compact, alias, recipe))
            for noise in recipe.asr_noise:
                noise_compact = normalize_text(noise).replace(" ", "")
                self._exact_asr_noise[noise_compact] = recipe
        self._partial_aliases.sort(key=lambda item: len(item[0]), reverse=True)
        self._phonetic_aliases.sort(key=lambda item: _hangul_syllable_count(item[0]), reverse=True)

    @property
    def version(self) -> str:
        return self._data.catalog_version

    @property
    def intent_count(self) -> int:
        return len(self._recipes)

    @property
    def intent_ids(self) -> tuple[str, ...]:
        return tuple(recipe.id for recipe in self._recipes)

    @property
    def candidates(self) -> tuple[IntentCandidate, ...]:
        return tuple(
            IntentCandidate(
                intent=recipe.id,
                aliases=tuple(recipe.aliases),
                description=recipe.description,
                slots=dict(recipe.slots),
            )
            for recipe in self._recipes
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntentCatalog":
        try:
            parsed = IntentCatalogData.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"invalid intent catalog: {exc}") from exc
        return cls(parsed)

    @classmethod
    def from_path(cls, path: str | Path) -> "IntentCatalog":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"cannot read intent catalog: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid intent catalog JSON: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError("intent catalog must be a JSON object")
        return cls.from_dict(data)

    def match(self, text: str, *, unknown_confidence: float) -> IntentMatch:
        normalized = normalize_text(text)
        compact = normalized.replace(" ", "")
        if not compact:
            return IntentMatch("unknown", unknown_confidence, {})

        exact = self._exact_aliases.get(compact)
        if exact is not None:
            return IntentMatch(exact.id, exact.exact_confidence, dict(exact.slots))

        noise = self._exact_asr_noise.get(compact)
        if noise is not None:
            return IntentMatch(noise.id, noise.confidence, dict(noise.slots))

        for alias_compact, recipe in self._partial_aliases:
            if alias_compact in compact:
                return IntentMatch(recipe.id, recipe.confidence, dict(recipe.slots))

        phonetic = self._match_phonetic(compact)
        if phonetic is not None:
            return phonetic

        return IntentMatch("unknown", unknown_confidence, {})

    def match_intent_id(self, intent: str, *, confidence: float) -> IntentMatch | None:
        recipe = self._recipes_by_id.get(intent)
        if recipe is None:
            return None
        return IntentMatch(recipe.id, confidence, dict(recipe.slots))

    def pronunciation_candidates(
        self,
        text: str,
        *,
        min_score: float = 0.55,
        limit: int = 5,
    ) -> tuple[PronunciationCandidate, ...]:
        compact = normalize_text(text).replace(" ", "")
        if not compact:
            return ()

        by_intent: dict[str, PronunciationCandidate] = {}
        for alias_compact, alias, recipe in self._phonetic_aliases:
            score = phonetic_similarity(alias_compact, compact)
            if score < min_score:
                continue
            existing = by_intent.get(recipe.id)
            candidate = PronunciationCandidate(
                intent=recipe.id,
                alias=alias,
                score=round(score, 3),
            )
            if existing is None or (candidate.score, len(candidate.alias)) > (
                existing.score,
                len(existing.alias),
            ):
                by_intent[recipe.id] = candidate

        candidates = sorted(
            by_intent.values(),
            key=lambda candidate: (candidate.score, len(candidate.alias)),
            reverse=True,
        )
        return tuple(candidates[:limit])

    def _match_phonetic(self, compact: str) -> IntentMatch | None:
        best: tuple[float, int, IntentRecipe] | None = None
        for alias_compact, _alias, recipe in self._phonetic_aliases:
            score = phonetic_similarity(alias_compact, compact)
            if score < 0.76:
                continue
            candidate = (score, _hangul_syllable_count(alias_compact), recipe)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
        if best is None:
            return None
        return IntentMatch(best[2].id, best[2].phonetic_confidence, dict(best[2].slots))


def load_intent_catalog(path: str | None = None) -> IntentCatalog:
    if path:
        return IntentCatalog.from_path(path)
    raw = resources.files("brain.intent").joinpath(DEFAULT_CATALOG_RESOURCE).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("default intent catalog must be a JSON object")
    return IntentCatalog.from_dict(data)


def normalize_text(text: str) -> str:
    lowered = text.casefold()
    without_punctuation = re.sub(r"[^\w\s가-힣]", " ", lowered)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def phonetic_similarity(alias: str, text: str) -> float:
    alias_syllables = _hangul_syllables(alias)
    text_syllables = _hangul_syllables(text)
    if len(alias_syllables) < 2 or len(text_syllables) < 2:
        return 0.0

    alias_key = _hangul_pronunciation_key("".join(alias_syllables))
    best = 0.0
    window_sizes = {len(alias_syllables)}
    if len(alias_syllables) > 4:
        window_sizes.add(len(alias_syllables) - 1)
    window_sizes.add(len(alias_syllables) + 1)

    for window_size in sorted(window_sizes):
        if window_size <= 0 or window_size > len(text_syllables):
            continue
        for start in range(0, len(text_syllables) - window_size + 1):
            window = "".join(text_syllables[start : start + window_size])
            window_key = _hangul_pronunciation_key(window)
            distance = _levenshtein_distance(alias_key, window_key)
            denominator = max(len(alias_key), len(window_key), 1)
            best = max(best, 1.0 - distance / denominator)
    return best


def _hangul_syllables(text: str) -> list[str]:
    return [char for char in text if _is_hangul_syllable(char)]


def _hangul_syllable_count(text: str) -> int:
    return len(_hangul_syllables(text))


def _is_hangul_syllable(char: str) -> bool:
    return 0xAC00 <= ord(char) <= 0xD7A3


_CHOSUNG = [
    "ㄱ",
    "ㄲ",
    "ㄴ",
    "ㄷ",
    "ㄸ",
    "ㄹ",
    "ㅁ",
    "ㅂ",
    "ㅃ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅉ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]
_JUNGSUNG = [
    "ㅏ",
    "ㅐ",
    "ㅑ",
    "ㅒ",
    "ㅓ",
    "ㅔ",
    "ㅕ",
    "ㅖ",
    "ㅗ",
    "ㅘ",
    "ㅙ",
    "ㅚ",
    "ㅛ",
    "ㅜ",
    "ㅝ",
    "ㅞ",
    "ㅟ",
    "ㅠ",
    "ㅡ",
    "ㅢ",
    "ㅣ",
]
_JONGSUNG = [
    "",
    "ㄱ",
    "ㄲ",
    "ㄳ",
    "ㄴ",
    "ㄵ",
    "ㄶ",
    "ㄷ",
    "ㄹ",
    "ㄺ",
    "ㄻ",
    "ㄼ",
    "ㄽ",
    "ㄾ",
    "ㄿ",
    "ㅀ",
    "ㅁ",
    "ㅂ",
    "ㅄ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]


def _hangul_pronunciation_key(text: str) -> str:
    parts: list[str] = []
    for char in text:
        code = ord(char)
        if not 0xAC00 <= code <= 0xD7A3:
            continue
        offset = code - 0xAC00
        initial = offset // 588
        vowel = (offset % 588) // 28
        final = offset % 28
        parts.append(_CHOSUNG[initial])
        parts.append(_JUNGSUNG[vowel])
        if final:
            parts.append(_JONGSUNG[final])
    return "".join(parts)


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]
