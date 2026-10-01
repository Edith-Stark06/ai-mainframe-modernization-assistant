"""
LLM providers for the #120 baseline evaluation.

Reuses the existing :class:`app.ai.providers.LLMProvider` protocol —
nothing is hard-coded to one vendor.

* :class:`ScriptedLLMProvider` — replays recorded responses keyed by a
  prompt fingerprint. Fully offline and deterministic; this is what the
  committed demo baseline report is generated from. Raises if a prompt
  is not in the script (so a report can never silently drift).
* :class:`RecordingLLMProvider` — wraps a real provider and records
  ``prompt_fingerprint -> response`` so a live run can be turned into a
  replayable script.
* :func:`build_provider` — construct a provider from config
  (``eval_provider`` / env): ``scripted``, ``fake`` or ``heuristic-demo``.
  A live provider can be wrapped in :class:`RecordingLLMProvider` by the
  caller to produce a replayable script.

No API key is ever read, stored, or logged by this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMConfigurationError
from app.ai.providers.models import LLMRequest, LLMResponse

__all__ = [
    "prompt_fingerprint",
    "ScriptedLLMProvider",
    "RecordingLLMProvider",
    "build_provider",
]


def prompt_fingerprint(request: LLMRequest) -> str:
    payload = json.dumps(
        {
            "prompt": request.prompt,
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScriptedLLMProvider(LLMProvider):
    """Deterministic offline replay of recorded responses."""

    def __init__(self, script: dict[str, str], model: str = "scripted-demo") -> None:
        self._script = dict(script)
        self._model = model
        self.calls = 0

    @classmethod
    def from_file(
        cls, path: str | Path, model: str = "scripted-demo"
    ) -> "ScriptedLLMProvider":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("responses", data), model=model)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        fp = prompt_fingerprint(request)
        if fp not in self._script:
            raise LLMConfigurationError(
                f"scripted provider has no response for prompt {fp[:12]} — "
                "re-record the script for this benchmark/prompt version"
            )
        return LLMResponse(
            text=self._script[fp],
            model=self._model,
            usage=None,  # a scripted replay has no real token usage
        )


class RecordingLLMProvider(LLMProvider):
    """Wrap a real provider; capture prompt -> response for later replay."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.recorded: dict[str, str] = {}

    def generate(self, request: LLMRequest) -> LLMResponse:
        resp = self._inner.generate(request)
        self.recorded[prompt_fingerprint(request)] = resp.text
        return resp

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"responses": self.recorded}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class HeuristicDemoProvider(LLMProvider):
    """
    A NON-LLM deterministic stand-in used ONLY to demonstrate the #120
    harness end-to-end and produce a committed sample report.

    It is not a language model and its numbers are not a real baseline.
    When it is given the deterministic-analysis context it extracts the
    answer from it (simulating a model that uses the evidence); given
    only the raw source it returns a degraded / partially-guessed answer
    and, for the adversarial traps, sometimes takes the bait — so the
    three-mode comparison exercises the report machinery realistically.
    Use a recorded script (``--provider scripted``) for an actual baseline.
    """

    model = "heuristic-demo"

    def generate(self, request: LLMRequest) -> LLMResponse:
        from app.evaluation.demo_model import answer_from_prompt

        return LLMResponse(
            text=answer_from_prompt(request.prompt),
            model=self.model,
            usage=None,
        )


def build_provider(
    provider: str,
    *,
    model: str = "",
    temperature: float = 0.0,
    timeout_s: int = 60,
    script_path: str | Path | None = None,
) -> LLMProvider:
    """Construct an :class:`LLMProvider` from configuration."""
    if provider == "scripted":
        if not script_path:
            raise LLMConfigurationError("provider 'scripted' requires --script")
        return ScriptedLLMProvider.from_file(
            script_path, model=model or "scripted-demo"
        )
    if provider == "fake":
        from app.ai.providers.fake import FakeLLMProvider

        return FakeLLMProvider(response_text="{}")
    if provider == "heuristic-demo":
        return HeuristicDemoProvider()
    raise LLMConfigurationError(
        f"unknown eval provider '{provider}' " "(use scripted | fake | heuristic-demo)"
    )
