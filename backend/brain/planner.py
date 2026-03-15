"""Planner — breaks a complex user request into ordered PlanSteps.

Each PlanStep carries:
  - intent:       string key understood by the controller / executor
  - description:  human-readable label
  - params:       dict of arguments for that step
  - depends_on:   list of step indices that must succeed before this one runs
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlanStep:
    intent: str
    description: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)


class Planner:
    """Convert a complex natural-language request into a list of PlanSteps."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(self, message: str) -> List[PlanStep]:
        """Return an ordered list of PlanSteps for *message*."""
        msg = message.strip()
        steps: List[PlanStep] = []

        # --- n8n end-to-end: create + run + debug ---
        if self._wants_n8n_create_and_run(msg):
            wf_name = self._extract_workflow_name(msg) or "My Workflow"
            steps.append(PlanStep(
                intent="N8N_CREATE_WORKFLOW",
                description=f"Create n8n workflow '{wf_name}'",
                params={"workflow_name": wf_name},
            ))
            steps.append(PlanStep(
                intent="N8N_RUN_WORKFLOW",
                description=f"Run workflow '{wf_name}'",
                params={"workflow_name": wf_name},
                depends_on=[0],
            ))
            if self._wants_debug(msg):
                steps.append(PlanStep(
                    intent="N8N_DEBUG_WORKFLOW",
                    description=f"Debug workflow '{wf_name}' until successful",
                    params={"workflow_name": wf_name, "max_iterations": 3},
                    depends_on=[1],
                ))
            return steps

        # --- n8n create only ---
        if self._wants_n8n_create(msg):
            wf_name = self._extract_workflow_name(msg) or "My Workflow"
            steps.append(PlanStep(
                intent="N8N_CREATE_WORKFLOW",
                description=f"Create n8n workflow '{wf_name}'",
                params={"workflow_name": wf_name},
            ))
            return steps

        # --- n8n debug only ---
        if self._wants_n8n_debug(msg):
            wf_name = self._extract_workflow_name(msg) or ""
            steps.append(PlanStep(
                intent="N8N_DEBUG_WORKFLOW",
                description=f"Debug n8n workflow '{wf_name}'",
                params={
                    "workflow_name": wf_name,
                    "max_iterations": self._extract_max_iterations(msg),
                },
            ))
            return steps

        # --- file scan + clean ---
        if self._wants_scan_and_clean(msg):
            path = self._extract_path(msg) or ""
            steps.append(PlanStep(
                intent="FIND_DUPLICATES_ONLY",
                description=f"Scan '{path}' for duplicates",
                params={"path": path},
            ))
            steps.append(PlanStep(
                intent="CLEAN_DUPLICATES_KEEP_NEWEST",
                description=f"Remove duplicates in '{path}'",
                params={"path": path},
                depends_on=[0],
            ))
            return steps

        # Fallback: single generic step → router will route back to controller.
        steps.append(PlanStep(
            intent="PASSTHROUGH",
            description="Pass request through to controller",
            params={"raw_message": message},
        ))
        return steps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wants_n8n_create_and_run(self, msg: str) -> bool:
        has_create = bool(re.search(
            r"\b(create|build|make|создай|создать|собери)\b", msg, re.I))
        has_run = bool(re.search(
            r"\b(run|запусти|запустить|execute|trigger)\b", msg, re.I))
        has_n8n = "n8n" in msg.lower()
        return has_n8n and has_create and has_run

    def _wants_n8n_create(self, msg: str) -> bool:
        has_create = bool(re.search(
            r"\b(create|build|make|создай|создать|собери)\b", msg, re.I))
        has_n8n = "n8n" in msg.lower()
        has_workflow = bool(re.search(r"\b(workflow|воркфлоу)\b", msg, re.I))
        return has_n8n and has_create and has_workflow

    def _wants_n8n_debug(self, msg: str) -> bool:
        has_debug = bool(re.search(
            r"\b(debug|fix|исправь|исправить|отладь|починить)\b", msg, re.I))
        has_n8n = "n8n" in msg.lower()
        return has_n8n and has_debug

    def _wants_debug(self, msg: str) -> bool:
        return bool(re.search(
            r"\b(debug|fix|until|пока|исправь|автоматически)\b", msg, re.I))

    def _wants_scan_and_clean(self, msg: str) -> bool:
        has_dup = bool(re.search(
            r"\bduplicates?\b|\bдублик|\bодинаков|\bкопи", msg, re.I))
        has_clean = bool(re.search(
            r"\b(clean|delete|remove|удали|очисти)\b", msg, re.I))
        return has_dup and has_clean

    def _extract_workflow_name(self, msg: str) -> Optional[str]:
        # Quoted name has priority.
        m = re.search(r'["\']([^"\']{2,80})["\']', msg)
        if m:
            return m.group(1).strip()
        # "named X" / "called X" / "под названием X"
        m = re.search(
            r'(?:named?|called|под\s+названием)\s+([A-Za-zА-ЯЁа-яё0-9 _\-]{2,60})',
            msg, re.I)
        if m:
            return m.group(1).strip()
        # English: "workflow X"
        m = re.search(r'workflow\s+([A-Za-z0-9 _\-]{2,60})', msg, re.I)
        if m:
            name = m.group(1)
            for stopper in [" in n8n", " and", " then", " run", " debug"]:
                idx = name.lower().find(stopper)
                if idx > 0:
                    name = name[:idx]
            return name.strip()
        return None

    def _extract_max_iterations(self, msg: str) -> int:
        m = re.search(
            r'(?:max[_ ]?iterations?|итерац[ий]{1,2})\s*[:=]?\s*(\d+)',
            msg, re.I)
        if m:
            return max(1, min(int(m.group(1)), 10))
        return 3

    def _extract_path(self, msg: str) -> Optional[str]:
        m = re.search(r'([A-Za-z]:[/\\][^\s,\'"<>]+)', msg)
        if m:
            return m.group(1).replace("\\", "/")
        return None
