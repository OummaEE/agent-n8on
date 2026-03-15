"""
test_plan_confirmation.py

Tests for Improvement 2: Plan Confirmation for SLOW tasks
  - SLOW path with require_confirmation=True returns plan, not execution result
  - "да" → execute the plan
  - "нет" → cancel
  - "изменить" → ask what to change, re-plan, show new plan
  - Risk assessment: low / medium / high
  - Plan format contains required sections
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from brain.brain_layer import BrainLayer, _HIGH_RISK_INTENTS, _MEDIUM_RISK_INTENTS
from brain.executor import StepResult
from brain.planner import PlanStep
from brain.verifier import VerificationResult


def _make_ctrl():
    ctrl = MagicMock()
    ctrl.handle_request.return_value = {
        "handled": True, "response": "ok", "tool_name": "x",
        "tool_result": None, "steps": [],
    }
    ctrl._call_tool_json = MagicMock(return_value={"execution_id": "eid"})
    return ctrl


def _make_brain(require_confirmation: bool = True) -> BrainLayer:
    tmpdir = Path(tempfile.mkdtemp())
    brain = BrainLayer(
        _make_ctrl(),
        require_confirmation=require_confirmation,
        rules_file=tmpdir / "rules.md",
        skills_dir=tmpdir,
    )
    # Mock executor + verifier for clean unit tests
    brain.executor = MagicMock()
    brain.executor.execute_plan.return_value = [
        StepResult(step_index=0, intent="N8N_CREATE_WORKFLOW",
                   success=True, response="created"),
    ]
    brain.verifier = MagicMock()
    brain.verifier.verify.return_value = VerificationResult(
        ok=True, summary="SUCCESS: 1/1 steps OK"
    )
    return brain


# Slow message that the router classifies as SLOW
_SLOW_MSG = 'create n8n workflow "X" and then run it'


class RiskAssessmentTests(unittest.TestCase):

    def setUp(self):
        self.brain = _make_brain()

    def test_low_risk_passthrough(self):
        steps = [PlanStep(intent="PASSTHROUGH", description="pass")]
        self.assertEqual(self.brain._assess_risk(steps), "low")

    def test_medium_risk_single_create(self):
        steps = [PlanStep(intent="N8N_CREATE_WORKFLOW", description="create")]
        self.assertEqual(self.brain._assess_risk(steps), "medium")

    def test_medium_risk_two_low_steps(self):
        steps = [
            PlanStep(intent="PASSTHROUGH", description="p1"),
            PlanStep(intent="PASSTHROUGH", description="p2"),
        ]
        self.assertEqual(self.brain._assess_risk(steps), "medium")

    def test_high_risk_debug(self):
        steps = [PlanStep(intent="N8N_DEBUG_WORKFLOW", description="debug")]
        self.assertEqual(self.brain._assess_risk(steps), "high")

    def test_high_risk_purge_trash(self):
        steps = [PlanStep(intent="PURGE_TRASH", description="purge")]
        self.assertEqual(self.brain._assess_risk(steps), "high")

    def test_high_risk_overrides_medium(self):
        steps = [
            PlanStep(intent="N8N_CREATE_WORKFLOW", description="create"),
            PlanStep(intent="N8N_DEBUG_WORKFLOW",  description="debug"),
        ]
        self.assertEqual(self.brain._assess_risk(steps), "high")


class PlanFormatTests(unittest.TestCase):

    def setUp(self):
        self.brain = _make_brain()

    def _make_plan(self):
        return [
            PlanStep(intent="N8N_CREATE_WORKFLOW", description="Create workflow 'X'"),
            PlanStep(intent="N8N_RUN_WORKFLOW",    description="Run workflow 'X'",
                     depends_on=[0]),
        ]

    def test_format_contains_step_numbers(self):
        formatted = self.brain._format_plan_for_user(self._make_plan(), "msg")
        self.assertIn("1.", formatted)
        self.assertIn("2.", formatted)

    def test_format_contains_step_descriptions(self):
        formatted = self.brain._format_plan_for_user(self._make_plan(), "msg")
        self.assertIn("Create workflow", formatted)
        self.assertIn("Run workflow", formatted)

    def test_format_contains_risk(self):
        formatted = self.brain._format_plan_for_user(self._make_plan(), "msg")
        self.assertRegex(formatted, r"(?i)(риск|risk|HIGH|MEDIUM|LOW)")

    def test_format_contains_confirmation_question(self):
        formatted = self.brain._format_plan_for_user(self._make_plan(), "msg")
        self.assertIn("да", formatted.lower())
        self.assertIn("нет", formatted.lower())
        self.assertIn("изменить", formatted.lower())

    def test_format_contains_affected_areas(self):
        formatted = self.brain._format_plan_for_user(self._make_plan(), "msg")
        self.assertIn("N8N_CREATE_WORKFLOW", formatted)


class ConfirmationFlowTests(unittest.TestCase):

    def setUp(self):
        self.brain = _make_brain(require_confirmation=True)

    def test_slow_returns_plan_not_execution(self):
        """First call → plan shown, no execution yet."""
        result = self.brain.handle(_SLOW_MSG)
        self.assertEqual(result["tool_name"], "plan_confirmation")
        self.assertTrue(result.get("awaiting_confirmation"))
        # Executor must NOT have been called yet
        self.brain.executor.execute_plan.assert_not_called()

    def test_slow_result_contains_plan_steps(self):
        result = self.brain.handle(_SLOW_MSG)
        self.assertIn("plan", result["tool_result"])
        self.assertGreater(len(result["tool_result"]["plan"]), 0)

    def test_yes_answer_triggers_execution(self):
        self.brain.handle(_SLOW_MSG)            # show plan
        result = self.brain.handle("да")        # confirm
        self.assertEqual(result["path"], "SLOW")
        self.assertEqual(result["tool_name"], "brain_slow_path")
        self.brain.executor.execute_plan.assert_called_once()

    def test_yes_variants_all_trigger_execution(self):
        for yes_word in ["да", "yes", "ок", "ok", "выполнить", "подтвердить"]:
            brain = _make_brain(require_confirmation=True)
            brain.handle(_SLOW_MSG)
            result = brain.handle(yes_word)
            self.assertEqual(
                result["tool_name"], "brain_slow_path",
                msg=f"'{yes_word}' should trigger execution",
            )

    def test_no_answer_cancels(self):
        self.brain.handle(_SLOW_MSG)
        result = self.brain.handle("нет")
        self.assertEqual(result["tool_name"], "plan_cancelled")
        self.assertIn("отменено", result["response"].lower())
        self.brain.executor.execute_plan.assert_not_called()

    def test_no_clears_pending(self):
        self.brain.handle(_SLOW_MSG)
        self.brain.handle("нет")
        self.assertIsNone(self.brain._pending)

    def test_modify_asks_what_to_change(self):
        self.brain.handle(_SLOW_MSG)
        result = self.brain.handle("изменить")
        self.assertEqual(result["tool_name"], "plan_modification_request")
        self.assertIn("изменить", result["response"].lower())

    def test_modify_then_description_re_plans(self):
        self.brain.handle(_SLOW_MSG)
        self.brain.handle("изменить")
        # User provides modification
        result = self.brain.handle("добавь шаг отладки")
        # Should show a new plan (awaiting confirmation again)
        self.assertTrue(result.get("awaiting_confirmation"))
        self.assertEqual(result["tool_name"], "plan_confirmation")

    def test_modify_then_yes_executes(self):
        self.brain.handle(_SLOW_MSG)
        self.brain.handle("изменить")
        self.brain.handle("добавь шаг")      # describe change → new plan shown
        result = self.brain.handle("да")     # confirm new plan
        self.assertEqual(result["tool_name"], "brain_slow_path")

    def test_unrecognised_answer_reshows_plan(self):
        self.brain.handle(_SLOW_MSG)
        result = self.brain.handle("что?")
        self.assertTrue(result.get("awaiting_confirmation"))
        self.assertIn("да", result["response"].lower())

    def test_pending_cleared_after_execution(self):
        self.brain.handle(_SLOW_MSG)
        self.brain.handle("да")
        self.assertIsNone(self.brain._pending)

    def test_no_confirmation_mode_executes_immediately(self):
        """require_confirmation=False → no plan shown, direct execution."""
        brain = _make_brain(require_confirmation=False)
        result = brain.handle(_SLOW_MSG)
        self.assertEqual(result["tool_name"], "brain_slow_path")
        brain.executor.execute_plan.assert_called_once()

    def test_fast_path_unaffected_by_confirmation_mode(self):
        """FAST requests still go through controller directly."""
        brain = _make_brain(require_confirmation=True)
        # Controller returns handled=True for this message
        brain.controller.handle_request.return_value = {
            "handled": True, "response": "done", "tool_name": "some_tool",
            "tool_result": None, "steps": [],
        }
        result = brain.handle("покажи что-нибудь")
        # FAST path is used (no confirmation)
        self.assertNotEqual(result["tool_name"], "plan_confirmation")


if __name__ == "__main__":
    unittest.main()
