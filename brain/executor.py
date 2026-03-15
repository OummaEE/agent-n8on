"""Executor — runs PlanSteps one by one via the AgentController.

Each step maps its `intent` to a controller message string, calls
`controller.handle_request()`, and returns a StepResult.

Steps marked with `depends_on` are only executed if all prerequisite
steps succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.planner import PlanStep


@dataclass
class StepResult:
    step_index: int
    intent: str
    success: bool
    response: str = ""
    tool_name: str = ""
    tool_result: Any = None
    error: str = ""
    skipped: bool = False


class Executor:
    """Execute a plan produced by Planner."""

    def __init__(self, controller: Any) -> None:
        self.controller = controller

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_plan(self, steps: List[PlanStep]) -> List[StepResult]:
        """Execute *steps* in order, honouring dependency constraints.

        Returns a list of StepResult, one per step.
        """
        results: List[StepResult] = []

        for idx, step in enumerate(steps):
            # Check that all dependencies succeeded.
            if not self._deps_ok(step, results):
                results.append(StepResult(
                    step_index=idx,
                    intent=step.intent,
                    success=False,
                    skipped=True,
                    error=f"Skipped: dependency step(s) {step.depends_on} failed",
                ))
                continue

            result = self._run_step(idx, step, results)
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deps_ok(self, step: PlanStep, results: List[StepResult]) -> bool:
        for dep_idx in step.depends_on:
            if dep_idx >= len(results):
                return False
            dep = results[dep_idx]
            if dep.skipped or not dep.success:
                return False
        return True

    def _run_step(self, idx: int, step: PlanStep,
                  prev_results: List[StepResult]) -> StepResult:
        """Convert a PlanStep into a controller call and capture the result."""

        if step.intent == "PASSTHROUGH":
            msg = step.params.get("raw_message", "")
            ctrl_result = self.controller.handle_request(msg)
            return self._wrap(idx, step, ctrl_result)

        # N8N_RUN_WORKFLOW calls the tool directly (no controller handler).
        if step.intent == "N8N_RUN_WORKFLOW":
            return self._run_n8n_workflow_step(idx, step, prev_results)

        # N8N_DEBUG_WORKFLOW: enrich params with workflow_id/execution_id from context.
        if step.intent == "N8N_DEBUG_WORKFLOW":
            return self._run_n8n_debug_step(idx, step, prev_results)

        # Build a synthetic controller message from intent + params.
        msg = self._intent_to_message(step, prev_results)
        ctrl_result = self.controller.handle_request(msg)
        return self._wrap(idx, step, ctrl_result)

    def _intent_to_message(self, step: PlanStep,
                           prev_results: List[StepResult]) -> str:
        """Convert a structured PlanStep back into a natural-language string
        that the controller's IntentClassifier will understand."""

        intent = step.intent
        p = step.params

        if intent == "N8N_CREATE_WORKFLOW":
            name = p.get("workflow_name", "My Workflow")
            return f'create n8n workflow named "{name}" with manual trigger'

        if intent == "N8N_DEBUG_WORKFLOW":
            name = p.get("workflow_name", "")
            iters = p.get("max_iterations", 3)
            confirm = "confirm" if p.get("confirm_sensitive_patch") else ""
            return (f'debug my n8n workflow "{name}" until it runs successfully '
                    f'max_iterations={iters} {confirm}').strip()

        if intent == "FIND_DUPLICATES_ONLY":
            path = p.get("path", "")
            return f"find duplicates in {path}"

        if intent == "CLEAN_DUPLICATES_KEEP_NEWEST":
            path = p.get("path", "")
            return f"clean duplicates in {path}"

        # Generic fallback.
        return p.get("raw_message", str(step))

    def _run_n8n_workflow_step(self, idx: int, step: PlanStep,
                               prev_results: List[StepResult]) -> StepResult:
        """Execute N8N_RUN_WORKFLOW directly via tool call (no controller handler)."""
        name = step.params.get("workflow_name", "")
        wf_id = self._find_created_workflow_id(prev_results)
        if not wf_id:
            return StepResult(
                step_index=idx, intent=step.intent,
                success=False, response="",
                error=f'No workflow id found to run "{name}"',
            )
        raw = self.controller._call_tool_json(
            "n8n_run_workflow",
            {"workflow_id": wf_id, "wait": True, "raw": True},
        )
        eid = raw.get("execution_id", "")
        if eid:
            self.controller.state.update_n8n_context(
                execution_id=eid, workflow_id=wf_id)
        err = raw.get("error", "")
        success = not err
        response = f'Workflow "{name}" started, execution_id={eid}' if success else err
        return StepResult(
            step_index=idx, intent=step.intent,
            success=success, response=response,
            tool_name="n8n_run_workflow", tool_result=raw,
            error=err,
        )

    def _run_n8n_debug_step(self, idx: int, step: PlanStep,
                            prev_results: List[StepResult]) -> StepResult:
        """Execute N8N_DEBUG_WORKFLOW with enriched params from previous steps."""
        p = dict(step.params)
        # Inject workflow_id from previous create/run step if not already set.
        if not p.get("workflow_id"):
            wf_id = self._find_created_workflow_id(prev_results)
            if wf_id:
                p["workflow_id"] = wf_id
        # Inject execution_id from controller state if not set.
        if not p.get("execution_id"):
            ctx_eid = getattr(self.controller.state.session, "last_n8n_execution_id", None)
            if ctx_eid:
                p["execution_id"] = ctx_eid
        ctrl_result = self.controller._handle_n8n_debug_workflow(p)
        return self._wrap(idx, step, ctrl_result)

    def _wrap(self, idx: int, step: PlanStep,
              ctrl_result: Dict[str, Any]) -> StepResult:
        """Wrap a controller result into a StepResult."""
        handled = ctrl_result.get("handled", False)
        response = ctrl_result.get("response", "")
        tool_name = ctrl_result.get("tool_name", "")
        tool_result = ctrl_result.get("tool_result")
        error = ""

        # Determine success.
        if not handled:
            # Controller didn't recognise it — not a hard failure for passthrough.
            success = step.intent == "PASSTHROUGH"
            error = "" if success else f"Controller did not handle intent '{step.intent}'"
        else:
            # Check for error in tool_result.
            if isinstance(tool_result, dict) and "error" in tool_result:
                success = False
                error = str(tool_result["error"])
            elif response and any(k in response.lower()
                                  for k in ("error:", "failed", "not found",
                                            "ошибка", "не найд")):
                success = False
                error = response[:200]
            else:
                success = True

        return StepResult(
            step_index=idx,
            intent=step.intent,
            success=success,
            response=response,
            tool_name=tool_name,
            tool_result=tool_result,
            error=error,
        )

    def _find_created_workflow_id(
            self, prev_results: List[StepResult]) -> Optional[str]:
        """Look for a workflow id in previous N8N_CREATE_WORKFLOW results."""
        for r in reversed(prev_results):
            if r.intent == "N8N_CREATE_WORKFLOW" and r.success:
                tr = r.tool_result
                if isinstance(tr, dict):
                    wid = tr.get("id") or tr.get("workflow_id")
                    if wid:
                        return str(wid)
        return None
