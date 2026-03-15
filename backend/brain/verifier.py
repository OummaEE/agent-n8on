"""Verifier — inspects StepResults and decides if the plan succeeded.

Returns a VerificationResult with:
  - ok:      True if all required steps passed
  - issues:  list of human-readable problem descriptions
  - retries: list of step indices that should be retried
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from brain.executor import StepResult


@dataclass
class VerificationResult:
    ok: bool
    issues: List[str] = field(default_factory=list)
    retries: List[int] = field(default_factory=list)
    summary: str = ""


class Verifier:
    """Analyse a list of StepResults and return a VerificationResult."""

    def verify(self, results: List[StepResult]) -> VerificationResult:
        if not results:
            return VerificationResult(
                ok=False, issues=["No steps were executed"], summary="EMPTY")

        issues: List[str] = []
        retries: List[int] = []

        for r in results:
            if r.skipped:
                issues.append(
                    f"Step {r.step_index} ({r.intent}) was skipped: {r.error}")
                continue
            if not r.success:
                issues.append(
                    f"Step {r.step_index} ({r.intent}) failed: {r.error or r.response[:120]}")
                # Retry only if it's not a dependency skip.
                retries.append(r.step_index)

        # Special check for debug loop: report inner status.
        for r in results:
            if r.intent in {"N8N_DEBUG_WORKFLOW"} and r.success:
                tr = r.tool_result
                if isinstance(tr, dict) and tr.get("status") == "STOPPED":
                    issues.append(
                        f"Debug loop stopped without success: {tr.get('reason', '')}")

        ok = len(issues) == 0
        succeeded = sum(1 for r in results if r.success and not r.skipped)
        total = len(results)
        summary = f"{'SUCCESS' if ok else 'PARTIAL'}: {succeeded}/{total} steps OK"

        return VerificationResult(
            ok=ok,
            issues=issues,
            retries=retries,
            summary=summary,
        )
