"""Ollama local provider — wraps the existing Ollama integration."""
from __future__ import annotations

import os
import requests
from typing import Dict, List

from providers.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Local Ollama instance. This is the current production path."""

    name = "ollama"

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        timeout: int = 180,
    ):
        self.url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int | None = None,
    ) -> LLMResponse:
        resp = requests.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout or self.timeout,
        )
        resp.encoding = "utf-8"
        data = resp.json()
        content = (
            data.get("message", {}).get("content", "")
            or data.get("response", "")
            or str(data)
        )
        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.name,
            tokens_used=data.get("eval_count", 0),
            raw=data,
        )

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []
