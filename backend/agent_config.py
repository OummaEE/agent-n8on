"""Unified configuration for Agent n8On.

Loads config from multiple sources with clear precedence:
  1. Hardcoded defaults (lowest priority)
  2. %APPDATA%/Agent n8On/config.json (installer-written)
  3. Environment variables (highest priority)

This module is the single source of truth for runtime configuration.
All other modules should import from here instead of reading env vars directly.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


# -- Defaults ---------------------------------------------------------------

_DEFAULTS = {
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:14b",
    "n8n_url": "http://localhost:5678",
    "web_port": 5000,
    "provider_mode": "local",  # local | api | auto
    "api_provider": "anthropic",  # anthropic | openai
    "api_key": "",
    "api_model": "",
    "knowledge_mode": "local_first",  # local_first | local_only
    "version": "5.0",
    "installed_by_agent": {
        "ollama": False,
        "nodejs": False,
        "n8n": False,
    },
}


def _appdata_config_path() -> Optional[Path]:
    """Return the installer-written config path on Windows, or None."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        p = Path(appdata) / "Agent n8On" / "config.json"
        if p.exists():
            return p
    return None


def _load_installer_config() -> Dict[str, Any]:
    """Load config.json written by the Tauri installer (if present)."""
    p = _appdata_config_path()
    if p is None:
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _env_override(key: str, env_var: str, current: Any) -> Any:
    """Override a config value from an environment variable if set."""
    val = os.environ.get(env_var)
    if val is None:
        return current
    # Coerce to int if the default is int
    if isinstance(current, int):
        try:
            return int(val)
        except ValueError:
            return current
    return val


@dataclass
class AgentConfig:
    """Runtime configuration. Immutable after load()."""

    ollama_url: str = _DEFAULTS["ollama_url"]
    ollama_model: str = _DEFAULTS["ollama_model"]
    n8n_url: str = _DEFAULTS["n8n_url"]
    web_port: int = _DEFAULTS["web_port"]
    provider_mode: str = _DEFAULTS["provider_mode"]
    api_provider: str = _DEFAULTS["api_provider"]
    api_key: str = _DEFAULTS["api_key"]
    api_model: str = _DEFAULTS["api_model"]
    knowledge_mode: str = _DEFAULTS["knowledge_mode"]
    version: str = _DEFAULTS["version"]
    installed_by_agent: Dict[str, bool] = field(
        default_factory=lambda: dict(_DEFAULTS["installed_by_agent"])
    )

    # -- source tracking (not persisted) ---
    _source: str = "defaults"

    @classmethod
    def load(cls) -> "AgentConfig":
        """Load configuration with precedence: defaults < installer < env vars."""
        cfg = cls()

        # Layer 2: installer config
        installer = _load_installer_config()
        if installer:
            cfg._source = "installer"
            if installer.get("model"):
                cfg.ollama_model = installer["model"]
            if installer.get("provider_mode"):
                cfg.provider_mode = installer["provider_mode"]
            if installer.get("api_key"):
                cfg.api_key = installer["api_key"]
            if installer.get("api_provider"):
                cfg.api_provider = installer["api_provider"]
            if installer.get("api_model"):
                cfg.api_model = installer["api_model"]
            if installer.get("knowledge_mode"):
                cfg.knowledge_mode = installer["knowledge_mode"]
            if isinstance(installer.get("installed_by_agent"), dict):
                cfg.installed_by_agent.update(installer["installed_by_agent"])

        # Layer 3: environment variable overrides (highest priority)
        cfg.ollama_url = _env_override("ollama_url", "OLLAMA_URL", cfg.ollama_url)
        cfg.ollama_model = _env_override("ollama_model", "OLLAMA_MODEL", cfg.ollama_model)
        cfg.n8n_url = _env_override("n8n_url", "N8N_URL", cfg.n8n_url)
        cfg.provider_mode = _env_override("provider_mode", "PROVIDER_MODE", cfg.provider_mode)
        cfg.api_key = _env_override("api_key", "LLM_API_KEY", cfg.api_key)
        if os.environ.get("OLLAMA_URL") or os.environ.get("OLLAMA_MODEL"):
            cfg._source = "env"

        return cfg

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for status endpoint / logging. Redacts api_key."""
        return {
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "n8n_url": self.n8n_url,
            "web_port": self.web_port,
            "provider_mode": self.provider_mode,
            "api_provider": self.api_provider,
            "api_key_set": bool(self.api_key),
            "api_model": self.api_model,
            "knowledge_mode": self.knowledge_mode,
            "version": self.version,
            "installed_by_agent": self.installed_by_agent,
            "config_source": self._source,
        }
