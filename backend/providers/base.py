"""Base class for LLM providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMResponse:
    """Standardised response from any provider."""
    content: str
    model: str
    provider: str  # "ollama", "openai", "anthropic", etc.
    tokens_used: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


class LLMProvider:
    """Abstract base for a chat-completion provider."""

    name: str = "base"

    def is_available(self) -> bool:
        """Return True if this provider can serve requests right now."""
        raise NotImplementedError

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 180,
    ) -> LLMResponse:
        """Send a chat-completion request and return a standardised response."""
        raise NotImplementedError

    def list_models(self) -> List[str]:
        """Return available model names."""
        return []
