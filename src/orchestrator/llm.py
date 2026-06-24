"""Provider-agnostic LLM layer over OpenAI + Anthropic, with a mock fallback.

The mock provider is deterministic so the full graph, memory, queue, and review
UI run end-to-end without any API keys.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .config import get_settings


@dataclass
class Completion:
    text: str
    provider: str
    model: str


class LLMClient:
    """Thin wrapper that routes to the configured provider."""

    def __init__(self, provider: str | None = None) -> None:
        settings = get_settings()
        self.provider = provider or settings.active_provider
        self.settings = settings

    def complete(self, system: str, prompt: str, *, json_mode: bool = False) -> Completion:
        if self.provider == "openai":
            return self._openai(system, prompt, json_mode)
        if self.provider == "anthropic":
            return self._anthropic(system, prompt, json_mode)
        return self._mock(system, prompt, json_mode)

    # ── providers ────────────────────────────────────────────────
    def _openai(self, system: str, prompt: str, json_mode: bool) -> Completion:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
        )
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            **kwargs,
        )
        return Completion(resp.choices[0].message.content or "", "openai", self.settings.openai_model)

    def _anthropic(self, system: str, prompt: str, json_mode: bool) -> Completion:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
        )
        if json_mode:
            prompt += "\n\nRespond with valid JSON only."
        resp = client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return Completion(text, "anthropic", self.settings.anthropic_model)

    def _mock(self, system: str, prompt: str, json_mode: bool) -> Completion:
        """Deterministic stand-in. Echoes a structured plan/answer."""
        if json_mode:
            payload = {
                "summary": f"[mock] handled: {prompt[:80]}",
                "confidence": 0.72,
                "quality": 0.71,
            }
            return Completion(json.dumps(payload), "mock", "mock-1")
        return Completion(f"[mock:{system[:24]}] {prompt[:200]}", "mock", "mock-1")
