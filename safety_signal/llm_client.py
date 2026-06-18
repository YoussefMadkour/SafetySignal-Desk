"""Configurable LLM client (OpenAI-compatible chat completions).

Works with AI/ML API, OpenAI, or Google Gemini (via its OpenAI-compatible
endpoint) — selected by LLM_PROVIDER (see config.resolve_llm). Used by the
language-heavy agents to phrase findings and draft communications.

Designed to be optional: if no key is configured or a call fails, callers fall
back to deterministic output, so the demo never depends on the network.
"""
from __future__ import annotations

import json
import re

import httpx

from . import config


class LLMClient:
    def __init__(self):
        self.provider, self.api_key, self.base_url, self.model = config.resolve_llm()
        self.base_url = self.base_url.rstrip("/")
        self.enabled = bool(self.api_key)

    def _post(self, payload: dict) -> str | None:
        try:
            with httpx.Client(timeout=40) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict | None:
        """Return a parsed JSON object from the model, or None on any failure.

        Tries JSON mode first; if the provider rejects ``response_format`` (some
        Gemini models do), retries without it and extracts JSON from the text.
        """
        if not self.enabled:
            return None
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        base = {"model": self.model, "temperature": temperature, "messages": messages}

        content = self._post({**base, "response_format": {"type": "json_object"}})
        if content is None:
            content = self._post(base)  # retry without response_format
        if content is None:
            return None
        return _parse_json(content)

    def complete_text(self, system: str, user: str, temperature: float = 0.3) -> str | None:
        if not self.enabled:
            return None
        content = self._post({
            "model": self.model, "temperature": temperature,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        })
        return content.strip() if content else None


def _parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
