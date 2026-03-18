"""Network status detection — offline-first policy enforcement.

Provides a simple, cached check for internet availability.
Used by ProviderManager and KnowledgeSelector to decide what's reachable.
"""
from __future__ import annotations

import socket
import time
from typing import Optional


# Cache duration in seconds — avoid hammering the network on every request
_CACHE_TTL = 30
_last_check: float = 0.0
_last_result: bool = False


def is_internet_available(timeout: float = 2.0) -> bool:
    """Check if the machine can reach the internet.

    Uses DNS resolution of a well-known host as a lightweight probe.
    Result is cached for _CACHE_TTL seconds.
    """
    global _last_check, _last_result

    now = time.time()
    if now - _last_check < _CACHE_TTL:
        return _last_result

    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo("dns.google", 443)
        _last_result = True
    except (socket.gaierror, socket.timeout, OSError):
        _last_result = False

    _last_check = now
    return _last_result


def is_ollama_available(url: str = "http://localhost:11434", timeout: float = 2.0) -> bool:
    """Check if local Ollama is reachable."""
    import requests
    try:
        r = requests.get(f"{url}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


class NetworkStatus:
    """Snapshot of current network/provider availability."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self._internet: Optional[bool] = None
        self._ollama: Optional[bool] = None

    def refresh(self) -> "NetworkStatus":
        self._internet = is_internet_available()
        self._ollama = is_ollama_available(self.ollama_url)
        return self

    @property
    def internet(self) -> bool:
        if self._internet is None:
            self.refresh()
        return self._internet  # type: ignore

    @property
    def ollama(self) -> bool:
        if self._ollama is None:
            self.refresh()
        return self._ollama  # type: ignore

    @property
    def effective_mode(self) -> str:
        """Human-readable description of what's available right now."""
        if self.ollama and self.internet:
            return "local + online"
        if self.ollama:
            return "local only"
        if self.internet:
            return "online only (no local model)"
        return "offline (nothing available)"

    def to_dict(self) -> dict:
        return {
            "internet": self.internet,
            "ollama": self.ollama,
            "effective_mode": self.effective_mode,
        }
