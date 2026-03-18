"""Provider abstraction layer.

Supports three modes:
  - local   — use Ollama only (offline, private)
  - api     — use external API (Claude, OpenAI, etc.)
  - auto    — try local first, fall back to API if available
"""
from providers.provider_manager import ProviderManager, ProviderMode
from providers.base import LLMProvider, LLMResponse

__all__ = ["ProviderManager", "ProviderMode", "LLMProvider", "LLMResponse"]
