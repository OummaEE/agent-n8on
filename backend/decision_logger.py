"""Structured decision logger for Agent n8On.

Logs routing, provider, knowledge, and repair decisions as JSON lines.
Each entry is a single JSON object on one line in the log file.

Usage:
    from decision_logger import dlog
    dlog.log_routing("SLOW", user_message="create a webhook workflow")
    dlog.log_provider("ollama", fallback=False)
    dlog.log_knowledge(["repair_memory", "instruction_packs"])
    dlog.log_repair(attempt=2, error="timeout", fix="increased timeout to 30s")
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_LOG_DIR = Path(os.environ.get("APPDATA", "")) / "Agent n8On"
if not _LOG_DIR.exists():
    # Fallback for non-Windows or missing APPDATA
    _LOG_DIR = Path(__file__).parent / "memory"

_LOG_FILE = _LOG_DIR / "decisions.jsonl"


class DecisionLogger:
    """Append-only JSON-lines logger for architecture decisions."""

    def __init__(self, log_file: Optional[Path] = None):
        self._file = log_file or _LOG_FILE
        self._lock = threading.Lock()
        # Ensure parent dir exists
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: Dict[str, Any]) -> None:
        entry["ts"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_routing(
        self,
        route: str,
        *,
        user_message: str = "",
        reason: str = "",
    ) -> None:
        self._write({
            "event": "routing",
            "route": route,
            "message_preview": user_message[:120],
            "reason": reason,
        })

    def log_provider(
        self,
        provider: str,
        *,
        fallback: bool = False,
        internet: Optional[bool] = None,
        ollama: Optional[bool] = None,
    ) -> None:
        self._write({
            "event": "provider",
            "provider": provider,
            "fallback": fallback,
            "internet": internet,
            "ollama": ollama,
        })

    def log_knowledge(
        self,
        sources_used: List[str],
        *,
        task: str = "",
        fragments_count: int = 0,
    ) -> None:
        self._write({
            "event": "knowledge",
            "sources": sources_used,
            "task_preview": task[:120],
            "fragments": fragments_count,
        })

    def log_repair(
        self,
        attempt: int,
        *,
        error: str = "",
        node_id: str = "",
        fix: str = "",
        success: bool = False,
    ) -> None:
        self._write({
            "event": "repair",
            "attempt": attempt,
            "error": error[:200],
            "node_id": node_id,
            "fix": fix[:200],
            "success": success,
        })

    def log_confirmation(
        self,
        confirmed: bool,
        *,
        workflow_id: str = "",
        execution_id: str = "",
        user_feedback: str = "",
    ) -> None:
        self._write({
            "event": "confirmation",
            "confirmed": confirmed,
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "feedback": user_feedback[:200],
        })


# Module-level singleton
dlog = DecisionLogger()
