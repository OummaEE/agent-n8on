"""External API provider — stub for future Claude/OpenAI integration.

STATUS: SCAFFOLDED — not yet functional.
This file defines the interface. Actual API calls are not implemented.
To enable, set provider_mode=api and configure api_key + api_provider in config.
"""
from __future__ import annotations

import os
from typing import Dict, List

from providers.base import LLMProvider, LLMResponse


class APIProvider(LLMProvider):
    """Remote API provider (Claude, OpenAI, etc.). Not yet implemented."""

    name = "api"

    def __init__(
        self,
        api_key: str | None = None,
        api_provider: str = "anthropic",
        model: str | None = None,
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.api_provider = api_provider
        self.model = model or "claude-sonnet-4-20250514"
        self.timeout = timeout

    def is_available(self) -> bool:
        # API provider requires a key and internet.
        # Actual connectivity check is deferred to first call.
        return bool(self.api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int | None = None,
    ) -> LLMResponse:
        # TODO: Implement actual API calls for Claude / OpenAI.
        raise NotImplementedError(
            f"APIProvider ({self.api_provider}) is scaffolded but not yet implemented. "
            "Use provider_mode=local for now."
        )

    def list_models(self) -> List[str]:
        return []
