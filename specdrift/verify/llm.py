"""One adapter over every model provider, plus an offline stand-in.

``openai`` covers any OpenAI-compatible endpoint, so Ollama, Groq and OpenRouter all
arrive through the same class by setting LLM_BASE_URL. ``anthropic`` is native.
``fake`` needs no network at all.
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol

RETRIES = 3
BACKOFF_S = 1.5


class Completer(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    """The provider failed after every retry."""


class OpenAICompatibleLLM:
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: float = 60.0,
                 max_tokens: int = 600) -> None:
        from openai import OpenAI

        self.model = model
        self.max_tokens = max_tokens
        self._client = OpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url or None,
            timeout=timeout,
        )

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


class AnthropicLLM:
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: float = 60.0,
                 max_tokens: int = 600) -> None:
        from anthropic import Anthropic

        self.model = model
        self.max_tokens = max_tokens
        self._client = Anthropic(api_key=api_key, base_url=base_url or None, timeout=timeout)

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


class FakeLLM:
    """A deterministic offline stand-in, so the whole pipeline runs with no API key.

    It is a weak reader on purpose: it compares the literal numbers and the named
    exceptions a rule mentions against the retrieved code, and knows nothing about
    ordering or about behaviour no rule authorises. Runs made with it are labelled
    `fake` in every result file so they are never mistaken for model results.
    """

    model = "fake"

    _NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
    _EXCEPTION_RE = re.compile(r"`([A-Z][A-Za-z]+)`")
    _RULE_RE = re.compile(r"RULE\s+(R\d+):\s*(.+)")

    def __init__(self, scripted: list[str] | None = None) -> None:
        # Unit tests hand it canned responses; the pipeline lets it reason instead.
        self.scripted = list(scripted or [])
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.scripted:
            return self.scripted.pop(0)
        if user.startswith("RULES:"):
            return json.dumps(self._judge_many(user))
        return json.dumps(self._judge(user))

    @classmethod
    def _values(cls, text: str) -> set[float]:
        return {float(token) for token in cls._NUMBER_RE.findall(text)}

    @staticmethod
    def _format(value: float) -> str:
        return str(int(value)) if value.is_integer() else str(value)

    def _judge_many(self, user: str) -> list[dict]:
        """The whole-file shape: every rule judged against the whole codebase at once."""
        rule_block, _, code = user.partition("CODE (the whole project):")
        rule_block = rule_block.removeprefix("RULES:")

        answers: list[dict] = []
        for line in rule_block.splitlines():
            rule_id, _, text = line.partition(":")
            rule_id, text = rule_id.strip(), text.strip()
            if not re.fullmatch(r"R\d+", rule_id):
                continue
            judged = self._judge(f"RULE {rule_id}: {text}\n\nCODE (only these excerpts are relevant):\n{code}")
            judged["rule_id"] = rule_id
            answers.append(judged)
        return answers

    def _judge(self, user: str) -> dict:
        match = self._RULE_RE.search(user)
        rule_text = match.group(2) if match else ""
        code = user.split("CODE (only these excerpts are relevant):", 1)[-1]
        # Stage 2 excerpts arrive line-numbered ("  41 | code"); the whole-file
        # baseline sends plain source. Strip the gutter only when there is one.
        numbered = [line.split("|", 1)[-1] for line in code.splitlines() if "|" in line]
        code_only = "\n".join(numbered) if numbered else code
        stripped = re.sub(r"#.*", "", code_only)          # comments are claims, not behaviour
        stripped = re.sub(r'"""[\s\S]*?"""', "", stripped)

        # A number the rule states that appears nowhere in the code is the clearest
        # signal available without executing anything - but only where the excerpt is
        # plainly the site that carries values. An excerpt with no literals at all is
        # not evidence of drift, it is an excerpt that does not settle the question.
        # Compare values, not spellings: a rule saying "10 tokens" is satisfied by 10.0.
        rule_numbers = {
            value for value in self._values(rule_text) if value not in (0.0, 1.0, 2.0)
        }
        code_numbers = self._values(stripped)
        missing_number = sorted(rule_numbers - code_numbers) if code_numbers else []

        # The same bar for a named exception: the code must raise something.
        required = self._EXCEPTION_RE.findall(rule_text)
        raises_anything = "raise " in stripped
        missing_raise = (
            [name for name in required if f"raise {name}" not in stripped]
            if raises_anything
            else []
        )

        undecidable = (rule_numbers and not code_numbers) or (required and not raises_anything)

        if missing_number:
            value = self._format(missing_number[0])
            return {
                "verdict": "DRIFT",
                "confidence": 0.72,
                "violated_clause": rule_text[:160],
                "evidence": {"file": "", "start_line": 0, "end_line": 0},
                "counterexample": {
                    "input": f"a case turning on the value {value}",
                    "expected": f"the rule's value {value} is applied",
                    "actual": f"the code never uses {value}",
                },
            }

        if missing_raise:
            name = missing_raise[0]
            return {
                "verdict": "DRIFT",
                "confidence": 0.68,
                "violated_clause": rule_text[:160],
                "evidence": {"file": "", "start_line": 0, "end_line": 0},
                "counterexample": {
                    "input": "the failing condition the rule names",
                    "expected": f"{name} is raised",
                    "actual": f"no `raise {name}` appears in the retrieved code",
                },
            }

        if undecidable:
            return {
                "verdict": "UNCERTAIN",
                "confidence": 0.3,
                "violated_clause": "",
                "evidence": {"file": "", "start_line": 0, "end_line": 0},
                "counterexample": {"input": "", "expected": "", "actual": ""},
            }

        return {
            "verdict": "COMPLIANT",
            "confidence": 0.6,
            "violated_clause": "",
            "evidence": {"file": "", "start_line": 0, "end_line": 0},
            "counterexample": {"input": "", "expected": "", "actual": ""},
        }


def with_retries(llm: Completer, system: str, user: str) -> str:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return llm.complete(system, user)
        except Exception as exc:                      # provider SDKs raise their own types
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_S * (attempt + 1))
    raise LLMError(f"provider failed after {RETRIES} attempts: {last}")


def build_llm(settings) -> Completer:
    provider = settings.llm_provider.lower()
    if provider == "fake":
        return FakeLLM()
    if provider == "openai":
        return OpenAICompatibleLLM(
            settings.llm_model, settings.llm_api_key, settings.llm_base_url,
            settings.llm_timeout_s, settings.llm_max_tokens,
        )
    if provider == "anthropic":
        return AnthropicLLM(
            settings.llm_model, settings.llm_api_key, settings.llm_base_url,
            settings.llm_timeout_s, settings.llm_max_tokens,
        )
    raise ValueError(f"unknown LLM provider {provider!r}")
