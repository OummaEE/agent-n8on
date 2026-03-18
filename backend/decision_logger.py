"""Structured decision logger for Agent n8On.

Logs six event types as JSON lines:
  1. routing    — brain routing decision (FAST/SLOW/CLARIFY)
  2. provider   — LLM provider selection and connectivity state
  3. knowledge  — which knowledge sources were checked/used
  4. execution  — workflow execution context
  5. repair     — repair cycle attempts and changes
  6. confirmation — user confirmation state

Log location:
  Windows:  %APPDATA%/Agent n8On/decisions.jsonl
  Other:    backend/memory/decisions.jsonl

Each line is a self-contained JSON object with "event" and "ts" fields.

Security:
  - NEVER log secrets, tokens, passwords, or credential values.
  - Message previews are truncated to 120 chars.
  - Error messages are truncated to 300 chars.

Usage:
    from decision_logger import dlog

    dlog.log_routing("SLOW", user_message="...", reason="multi-step connector detected")
    dlog.log_provider("ollama", mode="local", ...)
    dlog.log_knowledge(sources_checked=[...], sources_used=[...], ...)
    dlog.log_execution(workflow_id="123", ...)
    dlog.log_repair(attempt=2, ...)
    dlog.log_confirmation(state="asked", ...)
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


def _trunc(s: str, n: int = 300) -> str:
    """Truncate string to n chars for log safety."""
    return s[:n] if s else ""


class DecisionLogger:
    """Append-only JSON-lines logger for architecture decisions."""

    def __init__(self, log_file: Optional[Path] = None):
        self._file = log_file or _LOG_FILE
        self._lock = threading.Lock()
        # Ensure parent dir exists
        self._file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def log_path(self) -> Path:
        """Return the path where logs are written."""
        return self._file

    def _write(self, entry: Dict[str, Any]) -> None:
        entry["ts"] = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Logging must never break the application
            pass

    # ------------------------------------------------------------------
    # 1. Brain routing decision
    # ------------------------------------------------------------------
    def log_routing(
        self,
        route: str,
        *,
        user_message: str = "",
        reason: str = "",
    ) -> None:
        """Log a brain routing decision.

        Args:
            route: FAST, SLOW, or CLARIFY
            user_message: the user's message (truncated, no secrets)
            reason: why this route was chosen
                e.g. "multi-step connector detected", "too vague (<=4 words)",
                "2 action verbs found", "default (single action)"
        """
        self._write({
            "event": "routing",
            "route": route,
            "message_preview": _trunc(user_message, 120),
            "reason": reason,
        })

    # ------------------------------------------------------------------
    # 2. Provider decision
    # ------------------------------------------------------------------
    def log_provider(
        self,
        provider: str,
        *,
        mode: str = "",
        fallback: bool = False,
        internet: Optional[bool] = None,
        ollama: Optional[bool] = None,
        reason: str = "",
    ) -> None:
        """Log an LLM provider selection.

        Args:
            provider: which provider handled the request ("ollama", "api", "none")
            mode: configured mode ("local", "api", "auto")
            fallback: True if a fallback provider was used (e.g. auto tried local, fell back to api)
            internet: True/False/None — internet reachable at decision time
            ollama: True/False/None — Ollama reachable at decision time
            reason: why this provider was chosen
                e.g. "local mode, ollama available",
                "auto mode, ollama unavailable, fell back to api",
                "legacy direct call (ProviderManager not initialised)"
        """
        self._write({
            "event": "provider",
            "provider": provider,
            "mode": mode,
            "fallback": fallback,
            "internet": internet,
            "ollama": ollama,
            "reason": reason,
        })

    # ------------------------------------------------------------------
    # 3. Knowledge selection
    # ------------------------------------------------------------------
    def log_knowledge(
        self,
        *,
        sources_checked: Optional[List[str]] = None,
        sources_used: Optional[List[str]] = None,
        augmentation: str = "local_only",
        task: str = "",
        fragments_count: int = 0,
        reason: str = "",
    ) -> None:
        """Log a knowledge retrieval decision.

        Args:
            sources_checked: all sources that were searched
                e.g. ["repair_memory", "instruction_packs", "templates", "skills/instructions"]
            sources_used: sources that actually returned relevant content
                e.g. ["instruction_packs", "skills/instructions"]
            augmentation: "local_only" or "local_plus_online"
                (currently always "local_only" — online augmentation not implemented)
            task: task description (truncated)
            fragments_count: number of knowledge fragments retrieved
            reason: why these sources were selected
                e.g. "keyword 'webhook' matched instruction pack",
                "no matching repair memory entries"
        """
        self._write({
            "event": "knowledge",
            "sources_checked": sources_checked or [],
            "sources_used": sources_used or [],
            "augmentation": augmentation,
            "task_preview": _trunc(task, 120),
            "fragments_count": fragments_count,
            "reason": reason,
        })

    # ------------------------------------------------------------------
    # 4. Workflow execution context
    # ------------------------------------------------------------------
    def log_execution(
        self,
        *,
        workflow_id: str = "",
        workflow_name: str = "",
        execution_id: str = "",
        step_intent: str = "",
        success: bool = False,
        error: str = "",
        failing_node: str = "",
    ) -> None:
        """Log a workflow execution event.

        Args:
            workflow_id: n8n workflow ID (if known)
            workflow_name: human-readable workflow name (if known)
            execution_id: n8n execution ID (if known)
            step_intent: the brain step intent (e.g. N8N_RUN_WORKFLOW)
            success: whether the execution succeeded
            error: error message if failed (truncated, no secrets)
            failing_node: name or ID of the failing node (if known)
        """
        self._write({
            "event": "execution",
            "workflow_id": workflow_id,
            "workflow_name": _trunc(workflow_name, 100),
            "execution_id": execution_id,
            "step_intent": step_intent,
            "success": success,
            "error": _trunc(error),
            "failing_node": failing_node,
        })

    # ------------------------------------------------------------------
    # 5. Repair cycle
    # ------------------------------------------------------------------
    def log_repair(
        self,
        attempt: int,
        *,
        workflow_id: str = "",
        execution_id: str = "",
        error: str = "",
        failing_node: str = "",
        fix_description: str = "",
        what_changed: str = "",
        success: bool = False,
    ) -> None:
        """Log a repair cycle attempt.

        Args:
            attempt: attempt number (1-based)
            workflow_id: n8n workflow ID being repaired
            execution_id: n8n execution ID that failed
            error: the mismatch or failure reason (truncated)
            failing_node: which node failed (name or ID)
            fix_description: what the repair intends to do
            what_changed: concrete diff between this attempt and the previous
                e.g. "changed httpRequest timeout from 10s to 30s",
                "added missing authentication credentials node"
            success: whether this repair attempt resolved the issue
        """
        self._write({
            "event": "repair",
            "attempt": attempt,
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "error": _trunc(error),
            "failing_node": failing_node,
            "fix_description": _trunc(fix_description),
            "what_changed": _trunc(what_changed),
            "success": success,
        })

    # ------------------------------------------------------------------
    # 6. User confirmation state
    # ------------------------------------------------------------------
    def log_confirmation(
        self,
        state: str,
        *,
        workflow_id: str = "",
        execution_id: str = "",
        user_response: str = "",
        problem_description: str = "",
    ) -> None:
        """Log a user confirmation state change.

        Args:
            state: one of:
                "asked"     — system asked user to confirm
                "confirmed" — user confirmed success
                "rejected"  — user reported problem
                "cancelled" — user cancelled the operation
                "modified"  — user requested plan modification
            workflow_id: n8n workflow ID (if applicable)
            execution_id: n8n execution ID (if applicable)
            user_response: what the user said (truncated, no secrets)
            problem_description: if rejected, what the user reported as wrong
        """
        self._write({
            "event": "confirmation",
            "state": state,
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "user_response": _trunc(user_response, 200),
            "problem_description": _trunc(problem_description, 200),
        })


# Module-level singleton
dlog = DecisionLogger()
