from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from brain.config import MoonshineTinyKoConfig
from brain.intent.catalog import IntentCatalog
from brain.pipeline.base import StiError


@dataclass(frozen=True)
class SlmIntentDecision:
    intent: str
    raw_output: str
    slm_ms: int


class QwenSlmIntentResolver:
    def __init__(self, config: MoonshineTinyKoConfig) -> None:
        self._config = config
        self._llama_cli = _resolve_executable(config.slm_llama_cli)
        self._model_path = _resolve_model_path(config.slm_model_path)
        self._process: asyncio.subprocess.Process | None = None

    async def resolve(self, raw_text: str, catalog: IntentCatalog) -> SlmIntentDecision:
        prompt = build_intent_prompt(raw_text, catalog)
        started = time.monotonic()
        command = [
            self._llama_cli,
            "-m",
            self._model_path,
            "-p",
            prompt,
            "-n",
            str(self._config.slm_max_tokens),
            "--temp",
            "0",
            "--ctx-size",
            str(self._config.slm_context_size),
            "--single-turn",
            "--reasoning",
            "off",
            "--no-display-prompt",
            "--no-warmup",
            "--log-disable",
            "--no-perf",
            "--simple-io",
            "--color",
            "off",
        ]

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._process = process
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self._config.slm_timeout_ms / 1000,
            )
        except TimeoutError as exc:
            await self.cancel()
            raise StiError("timeout", "SLM intent resolution timed out") from exc
        except OSError as exc:
            raise StiError("slm_failed", f"cannot execute llama-cli: {exc}") from exc
        except asyncio.CancelledError:
            await self.cancel()
            raise
        finally:
            if process is not None and process.returncode is not None:
                self._process = None

        if process is None:
            raise StiError("slm_failed", "llama-cli did not start")
        returncode = process.returncode
        self._process = None
        output = stdout.decode("utf-8", errors="replace")
        completion = extract_slm_completion(output)
        slm_ms = int((time.monotonic() - started) * 1000)
        if returncode != 0:
            raise StiError("slm_failed", f"llama-cli exited with code {returncode}")

        return SlmIntentDecision(
            intent=parse_intent_from_slm_output(completion, catalog.intent_ids),
            raw_output=completion,
            slm_ms=slm_ms,
        )

    async def cancel(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            self._process = None
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.kill()
            await process.wait()
        finally:
            self._process = None


def build_intent_prompt(raw_text: str, catalog: IntentCatalog) -> str:
    lines = [
        "You map Korean robot voice ASR text to exactly one intent id.",
        "ASR text may contain severe spacing errors, homophones, missing syllables, or pronunciation mistakes.",
        "Compare the ASR text against aliases by robot command meaning and Korean pronunciation.",
        "Use the pronunciation candidates as strong hints. They are computed from Hangul sound similarity.",
        "Do not choose idle unless the ASR text means stay, stop, wait, or hold still.",
        "Return only one id from the valid ids, or unknown if none fit.",
        "",
        "Valid intents:",
    ]
    for candidate in catalog.candidates:
        aliases = ", ".join(candidate.aliases[:10])
        description = f" ({candidate.description})" if candidate.description else ""
        lines.append(f"- {candidate.intent}{description}: {aliases}")
    examples = _prompt_examples(catalog)
    if examples:
        lines.extend(["", "Examples:"])
        for text, intent in examples:
            lines.append(f"ASR text: {text} -> {intent}")
    lines.extend(["", f'Current ASR text: "{raw_text}"'])
    pronunciation_candidates = catalog.pronunciation_candidates(raw_text)
    if pronunciation_candidates:
        lines.extend(["", "Current pronunciation candidates:"])
        for candidate in pronunciation_candidates:
            lines.append(
                f"- {candidate.intent}: alias={candidate.alias}, sound_score={candidate.score:.3f}"
            )
    lines.extend(["", "Intent id:"])
    return "\n".join(lines)


def parse_intent_from_slm_output(output: str, valid_intents: tuple[str, ...]) -> str:
    valid = (*valid_intents, "unknown")
    matches: list[tuple[int, str]] = []
    for intent in valid:
        start = 0
        while True:
            index = output.find(intent, start)
            if index < 0:
                break
            matches.append((index, intent))
            start = index + len(intent)
    if not matches:
        return "unknown"
    return max(matches, key=lambda item: item[0])[1]


def extract_slm_completion(output: str) -> str:
    text = re.split(r"\[\s*Prompt:|Exiting\.\.\.", output, maxsplit=1)[0]
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    if "Intent id:" in text:
        text = text.rsplit("Intent id:", maxsplit=1)[-1]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return text.strip()


def compact_slm_output(output: str, *, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", output).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _prompt_examples(catalog: IntentCatalog) -> list[tuple[str, str]]:
    intent_ids = set(catalog.intent_ids)
    examples: list[tuple[str, str]] = []
    if "roll_left" in intent_ids:
        examples.extend(
            [
                ("좌로 글로", "roll_left"),
                ("잘 어울려", "roll_left"),
                ("잘 어글러", "roll_left"),
            ]
        )
    if "roll_right" in intent_ids:
        examples.extend(
            [
                ("우러글라", "roll_right"),
                ("울어 굴러", "roll_right"),
                ("오른쪽으로 글러", "roll_right"),
            ]
        )
    if "sit" in intent_ids:
        examples.append(("안 자", "sit"))
    if "stand" in intent_ids:
        examples.append(("너 저기 일어서", "stand"))
    if "give_hand" in intent_ids:
        examples.append(("손 줘", "give_hand"))
    if "idle" in intent_ids:
        examples.append(("가만히 있어", "idle"))
    else:
        examples.append(("가만히 있어", "unknown"))
    return examples


def _resolve_executable(path: str) -> str:
    if "/" in path:
        executable = Path(path)
        if executable.is_file() and executable.stat().st_mode & 0o111:
            return str(executable)
        raise RuntimeError(f"llama-cli is not executable: {path}")
    resolved = shutil.which(path)
    if resolved is None:
        raise RuntimeError(f"llama-cli not found: {path}")
    return resolved


def _resolve_model_path(path: str) -> str:
    model = Path(path)
    if not model.is_file():
        raise RuntimeError(f"SLM model not found: {path}")
    return str(model)
