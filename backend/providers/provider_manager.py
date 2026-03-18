"""ProviderManager — selects and manages the active LLM provider.

Modes:
  local  — Ollama only (default, offline-safe)
  api    — external API only (requires key + internet)
  auto   — try local first, fall back to API if local unavailable
"""
from __future__ import annotations

import enum
from typing import Dict, List, Optional

from providers.base import LLMProvider, LLMResponse
from providers.local_ollama import OllamaProvider
from providers.api_provider import APIProvider


class ProviderMode(str, enum.Enum):
    LOCAL = "local"
    API = "api"
    AUTO = "auto"


class ProviderManager:
    """Central point for LLM access. Wraps provider selection logic."""

    def __init__(
        self,
        mode: ProviderMode = ProviderMode.LOCAL,
        ollama_url: str | None = None,
        ollama_model: str | None = None,
        api_key: str | None = None,
        api_provider: str = "anthropic",
        api_model: str | None = None,
    ):
        self.mode = mode
        self._local = OllamaProvider(url=ollama_url, model=ollama_model)
        self._api = APIProvider(
            api_key=api_key, api_provider=api_provider, model=api_model
        )
        self._last_provider: str | None = None
        self._last_fallback: bool = False

    # -- public interface ---------------------------------------------------

    @property
    def active_provider_name(self) -> str:
        """Name of the provider that handled the last request."""
        return self._last_provider or self.mode.value

    @property
    def used_fallback(self) -> bool:
        return self._last_fallback

    def is_local_available(self) -> bool:
        return self._local.is_available()

    def is_api_available(self) -> bool:
        return self._api.is_available()

    def list_models(self) -> List[str]:
        if self.mode == ProviderMode.LOCAL:
            return self._local.list_models()
        if self.mode == ProviderMode.API:
            return self._api.list_models()
        # auto: merge both
        return self._local.list_models() + self._api.list_models()

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 180,
    ) -> LLMResponse:
        """Route a chat request through the configured provider mode."""
        self._last_fallback = False

        if self.mode == ProviderMode.LOCAL:
            self._last_provider = "ollama"
            return self._local.chat(
                messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout
            )

        if self.mode == ProviderMode.API:
            self._last_provider = "api"
            return self._api.chat(
                messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout
            )

        # AUTO: try local, fall back to api
        if self._local.is_available():
            self._last_provider = "ollama"
            return self._local.chat(
                messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout
            )

        if self._api.is_available():
            self._last_provider = "api"
            self._last_fallback = True
            return self._api.chat(
                messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout
            )

        raise ConnectionError(
            "No LLM provider available. "
            "Ollama is not running and no API key is configured."
        )

    # convenience: expose current model name for status display
    @property
    def current_model(self) -> str:
        if self.mode == ProviderMode.API:
            return self._api.model
        return self._local.model
