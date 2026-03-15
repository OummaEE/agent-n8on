"""Tests for BrainLayer orchestration: Router, Planner, Executor, Verifier, BrainLayer.

Covers:
  FAST PATH  — controller handles the request directly → brain wraps it.
  SLOW PATH  — multi-step request → plan → execute → verify.
  CLARIFY    — too-vague message → brain asks for clarification.
  Router     — FAST/SLOW/CLARIFY classification.
  Planner    — step generation for different request types.
  Verifier   — success / partial / failure analysis.
  E2E chains — User → Brain → Plan → Execute → Verify → Done.
"""

import json
import os
import shutil
import tempfile
import unittest

from controller import create_controller
from brain.brain_layer import BrainLayer
from brain.router import Router
from brain.planner import Planner
from brain.executor import Executor, StepResult
from brain.verifier import Verifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_brain(memory_dir: str, tools: dict) -> BrainLayer:
    ctrl = create_controller(memory_dir, tools)
    return BrainLayer(ctrl)


def _noop_tools():
    """Minimal tools that succeed silently."""
    return {
        "n8n_list_workflows": lambda a: json.dumps({"data": []}),
        "n8n_create_workflow": lambda a: json.dumps({"id": "wf-1", "name": a.get("name", "X")}),
        "n8n_get_workflow": lambda a: json.dumps({"id": "wf-1", "name": "X", "nodes": [], "connections": {}}),
        "n8n_run_workflow": lambda a: json.dumps({"execution_id": "exec-1"}),
        "n8n_get_execution": lambda a: json.dumps({"id": "exec-1", "status": "success", "data": {"resultData": {}}}),
        "n8n_get_executions": lambda a: json.dumps({"data": [{"id": "exec-1", "status": "success", "startedAt": "2026-03-01T10:00:00Z"}]}),
    }


# ---------------------------------------------------------------------------
# 1. Router tests
# ---------------------------------------------------------------------------

class RouterTests(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    # FAST: controller handled it
    def test_fast_when_controller_handled(self):
        self.assertEqual(self.router.route("anything", controller_handled=True), "FAST")

    # FAST: simple single-action message
    def test_fast_simple_create(self):
        path = self.router.route('create n8n workflow "Test"', controller_handled=False)
        self.assertEqual(path, "FAST")

    # SLOW: explicit "and then" connector
    def test_slow_and_then_connector(self):
        path = self.router.route(
            'create n8n workflow "X" and then run it', controller_handled=False)
        self.assertEqual(path, "SLOW")

    # SLOW: Russian connector
    def test_slow_ru_zathem(self):
        path = self.router.route(
            'создай workflow в n8n, а затем запусти его', controller_handled=False)
        self.assertEqual(path, "SLOW")

    # SLOW: "until it works"
    def test_slow_until_it_works(self):
        path = self.router.route(
            'debug n8n workflow "X" until it works', controller_handled=False)
        self.assertEqual(path, "SLOW")

    # SLOW: multiple action verbs
    def test_slow_multiple_actions(self):
        path = self.router.route(
            'scan and delete duplicates in Downloads', controller_handled=False)
        self.assertEqual(path, "SLOW")

    # CLARIFY: too vague
    def test_clarify_vague_fix(self):
        path = self.router.route('fix', controller_handled=False)
        self.assertEqual(path, "CLARIFY")

    def test_clarify_vague_debug(self):
        path = self.router.route('debug', controller_handled=False)
        self.assertEqual(path, "CLARIFY")


# ---------------------------------------------------------------------------
# 2. Planner tests
# ---------------------------------------------------------------------------

class PlannerTests(unittest.TestCase):

    def setUp(self):
        self.planner = Planner()

    def test_plan_create_and_run(self):
        steps = self.planner.plan('create n8n workflow "MyFlow" and then run it')
        intents = [s.intent for s in steps]
        self.assertIn("N8N_CREATE_WORKFLOW", intents)
        self.assertIn("N8N_RUN_WORKFLOW", intents)

    def test_plan_create_run_debug(self):
        steps = self.planner.plan(
            'create n8n workflow "MyFlow" then run and debug until it works')
        intents = [s.intent for s in steps]
        self.assertIn("N8N_CREATE_WORKFLOW", intents)
        self.assertIn("N8N_RUN_WORKFLOW", intents)
        self.assertIn("N8N_DEBUG_WORKFLOW", intents)

    def test_plan_debug_only(self):
        steps = self.planner.plan('debug n8n workflow "BrokenFlow"')
        self.assertEqual(steps[0].intent, "N8N_DEBUG_WORKFLOW")
        self.assertEqual(steps[0].params.get("workflow_name"), "BrokenFlow")

    def test_plan_scan_and_clean(self):
        steps = self.planner.plan('find and delete duplicates in C:/Downloads')
        intents = [s.intent for s in steps]
        self.assertIn("FIND_DUPLICATES_ONLY", intents)
        self.assertIn("CLEAN_DUPLICATES_KEEP_NEWEST", intents)

    def test_plan_dependency_ordering(self):
        steps = self.planner.plan('create n8n workflow "X" and then run it')
        run_step = next(s for s in steps if s.intent == "N8N_RUN_WORKFLOW")
        self.assertIn(0, run_step.depends_on)

    def test_plan_extracts_workflow_name_quoted(self):
        steps = self.planner.plan('create n8n workflow "Production Pipeline" and run')
        create = next(s for s in steps if s.intent == "N8N_CREATE_WORKFLOW")
        self.assertEqual(create.params.get("workflow_name"), "Production Pipeline")

    def test_plan_fallback_passthrough(self):
        steps = self.planner.plan('what is the weather today')
        self.assertEqual(steps[0].intent, "PASSTHROUGH")


# ---------------------------------------------------------------------------
# 3. Executor tests
# ---------------------------------------------------------------------------

class ExecutorTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_brain_exec_")
        mem = os.path.join(self.temp, "memory")
        os.makedirs(mem)
        self.ctrl = create_controller(mem, _noop_tools())

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_passthrough_step_calls_controller(self):
        from brain.planner import PlanStep
        executor = Executor(self.ctrl)
        steps = [PlanStep(intent="PASSTHROUGH", description="test",
                          params={"raw_message": 'create n8n workflow named "E2E Test"'})]
        results = executor.execute_plan(steps)
        self.assertEqual(len(results), 1)
        # Controller handled it → success (create_workflow is handled by controller)
        self.assertFalse(results[0].skipped)

    def test_dependency_skip_when_parent_fails(self):
        from brain.planner import PlanStep
        executor = Executor(self.ctrl)
        failing_tools = dict(_noop_tools())
        failing_tools["n8n_create_workflow"] = lambda a: json.dumps({"error": "API down"})
        self.ctrl.tools.update(failing_tools)

        steps = [
            PlanStep(intent="N8N_CREATE_WORKFLOW", description="create",
                     params={"workflow_name": "X"}),
            PlanStep(intent="N8N_RUN_WORKFLOW", description="run",
                     params={"workflow_name": "X"}, depends_on=[0]),
        ]
        results = executor.execute_plan(steps)
        self.assertEqual(len(results), 2)
        # Second step must be skipped because first failed.
        self.assertTrue(results[1].skipped)

    def test_all_steps_run_when_no_deps_fail(self):
        from brain.planner import PlanStep
        executor = Executor(self.ctrl)
        steps = [
            PlanStep(intent="PASSTHROUGH", description="s0",
                     params={"raw_message": 'create n8n workflow named "S0"'}),
            PlanStep(intent="PASSTHROUGH", description="s1",
                     params={"raw_message": 'create n8n workflow named "S1"'}),
        ]
        results = executor.execute_plan(steps)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].skipped)
        self.assertFalse(results[1].skipped)


# ---------------------------------------------------------------------------
# 4. Verifier tests
# ---------------------------------------------------------------------------

class VerifierTests(unittest.TestCase):

    def setUp(self):
        self.verifier = Verifier()

    def _ok(self, idx: int, intent: str = "STEP") -> StepResult:
        return StepResult(step_index=idx, intent=intent, success=True,
                          response="done")

    def _fail(self, idx: int, intent: str = "STEP") -> StepResult:
        return StepResult(step_index=idx, intent=intent, success=False,
                          error="something broke")

    def _skip(self, idx: int, intent: str = "STEP") -> StepResult:
        return StepResult(step_index=idx, intent=intent, success=False,
                          skipped=True, error="dependency failed")

    def test_all_ok(self):
        vr = self.verifier.verify([self._ok(0), self._ok(1)])
        self.assertTrue(vr.ok)
        self.assertEqual(vr.issues, [])
        self.assertIn("SUCCESS", vr.summary)

    def test_one_failure(self):
        vr = self.verifier.verify([self._ok(0), self._fail(1)])
        self.assertFalse(vr.ok)
        self.assertTrue(any("1" in issue for issue in vr.issues))
        self.assertIn(1, vr.retries)

    def test_skipped_step_reported(self):
        vr = self.verifier.verify([self._ok(0), self._skip(1)])
        self.assertFalse(vr.ok)
        self.assertTrue(any("skipped" in i.lower() for i in vr.issues))

    def test_empty_results(self):
        vr = self.verifier.verify([])
        self.assertFalse(vr.ok)

    def test_debug_stopped_reported(self):
        debug_result = StepResult(
            step_index=0, intent="N8N_DEBUG_WORKFLOW", success=True,
            response="stopped", tool_result={"status": "STOPPED", "reason": "max iters"})
        vr = self.verifier.verify([debug_result])
        self.assertFalse(vr.ok)
        self.assertTrue(any("stopped" in i.lower() for i in vr.issues))


# ---------------------------------------------------------------------------
# 5. BrainLayer – FAST path
# ---------------------------------------------------------------------------

class BrainFastPathTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_brain_fast_")
        mem = os.path.join(self.temp, "memory")
        os.makedirs(mem)
        self.brain = _make_brain(mem, _noop_tools())

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_create_workflow_is_fast(self):
        result = self.brain.handle('create n8n workflow named "Fast Test"')
        self.assertEqual(result["path"], "FAST")
        self.assertTrue(result["handled"])
        self.assertEqual(result["plan"], [])

    def test_fast_result_contains_response(self):
        result = self.brain.handle('create n8n workflow named "Fast Response Test"')
        self.assertIn("response", result)
        self.assertIsInstance(result["response"], str)

    def test_fast_result_verified_true(self):
        result = self.brain.handle('create n8n workflow named "Verify Test"')
        self.assertTrue(result.get("verified"))

    def test_debug_existing_workflow_is_fast(self):
        """debug single workflow → controller handles → FAST."""
        tools = dict(_noop_tools())
        tools["n8n_list_workflows"] = lambda a: json.dumps({
            "data": [{"id": "wf-1", "name": "My Flow", "active": False}]})
        tools["n8n_get_workflow"] = lambda a: json.dumps({
            "id": "wf-1", "name": "My Flow",
            "nodes": [{"id": "n1", "name": "Manual Trigger",
                        "type": "n8n-nodes-base.manualTrigger", "parameters": {}}],
            "connections": {}})

        brain = _make_brain(
            os.path.join(self.temp, "mem2"),
            tools,
        )
        os.makedirs(os.path.join(self.temp, "mem2"), exist_ok=True)

        result = brain.handle(
            'debug my n8n workflow "My Flow" until it runs successfully confirm')
        self.assertEqual(result["path"], "FAST")
        self.assertTrue(result["handled"])


# ---------------------------------------------------------------------------
# 6. BrainLayer – CLARIFY path
# ---------------------------------------------------------------------------

class BrainClarifyTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_brain_clarify_")
        mem = os.path.join(self.temp, "memory")
        os.makedirs(mem)
        self.brain = _make_brain(mem, {})

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_vague_fix_gets_clarify(self):
        result = self.brain.handle("fix")
        self.assertEqual(result["path"], "CLARIFY")

    def test_vague_debug_gets_clarify(self):
        result = self.brain.handle("debug")
        self.assertEqual(result["path"], "CLARIFY")

    def test_clarify_response_is_question(self):
        result = self.brain.handle("fix")
        self.assertIn("?", result["response"])

    def test_clarify_not_fully_handled(self):
        result = self.brain.handle("fix")
        # Clarify is "handled" in the sense that the brain responded,
        # but verified=False (no action taken).
        self.assertFalse(result.get("verified"))


# ---------------------------------------------------------------------------
# 7. BrainLayer – SLOW path (end-to-end)
# ---------------------------------------------------------------------------

class BrainSlowPathTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_brain_slow_")
        mem = os.path.join(self.temp, "memory")
        os.makedirs(mem)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def _mem(self, suffix: str) -> str:
        p = os.path.join(self.temp, suffix)
        os.makedirs(p, exist_ok=True)
        return p

    def test_create_and_run_produces_slow_path(self):
        """'create workflow X and then run it' → SLOW with 2-step plan."""
        brain = _make_brain(self._mem("m1"), _noop_tools())
        result = brain.handle('create n8n workflow "TestFlow" and then run it')
        self.assertEqual(result["path"], "SLOW")

    def test_slow_plan_has_expected_steps(self):
        brain = _make_brain(self._mem("m2"), _noop_tools())
        result = brain.handle('create n8n workflow "TestFlow" and then run it')
        plan = result["tool_result"]["plan"]
        intents = [s["intent"] for s in plan]
        self.assertIn("N8N_CREATE_WORKFLOW", intents)
        self.assertIn("N8N_RUN_WORKFLOW", intents)

    def test_slow_step_results_present(self):
        brain = _make_brain(self._mem("m3"), _noop_tools())
        result = brain.handle('create n8n workflow "TestFlow" and then run it')
        step_results = result["tool_result"]["step_results"]
        self.assertGreaterEqual(len(step_results), 1)

    def test_slow_verification_present(self):
        brain = _make_brain(self._mem("m4"), _noop_tools())
        result = brain.handle('create n8n workflow "TestFlow" and then run it')
        vr = result["tool_result"]["verification"]
        self.assertIn("ok", vr)
        self.assertIn("summary", vr)

    def test_slow_path_response_contains_summary(self):
        brain = _make_brain(self._mem("m5"), _noop_tools())
        result = brain.handle('create n8n workflow "TestFlow" and then run it')
        self.assertIn("[SLOW]", result["response"])

    def test_e2e_create_run_debug_chain(self):
        """Full chain: create → run → debug → SUCCESS."""
        wf_store = {}
        exec_store = {"exec-1": {"id": "exec-1", "status": "success",
                                  "workflowId": "wf-1", "data": {"resultData": {}}}}

        def create(a):
            wf_store["wf-1"] = {"id": "wf-1", "name": a.get("name", "X"),
                                 "nodes": [], "connections": {}}
            return json.dumps({"id": "wf-1", "name": a.get("name", "X")})

        tools = {
            "n8n_list_workflows": lambda a: json.dumps({"data": []}),
            "n8n_create_workflow": create,
            "n8n_get_workflow": lambda a: json.dumps(
                wf_store.get("wf-1", {"id": "wf-1", "name": "X",
                                      "nodes": [], "connections": {}})),
            "n8n_run_workflow": lambda a: json.dumps({"execution_id": "exec-1"}),
            "n8n_get_execution": lambda a: json.dumps(exec_store.get(
                a.get("execution_id", ""), {"id": "?", "status": "success",
                                            "data": {"resultData": {}}})),
            "n8n_get_executions": lambda a: json.dumps({"data": [
                {"id": "exec-1", "status": "success",
                 "startedAt": "2026-03-01T10:00:00Z"}]}),
        }

        brain = _make_brain(self._mem("m_e2e"), tools)
        result = brain.handle(
            'create n8n workflow "E2E Chain" then run and debug until it works')

        self.assertEqual(result["path"], "SLOW")
        self.assertIn("N8N_CREATE_WORKFLOW",
                      [s["intent"] for s in result["tool_result"]["plan"]])


# ---------------------------------------------------------------------------
# 8. BrainLayer – full end-to-end with controller in FAST then SLOW
# ---------------------------------------------------------------------------

class BrainRoutingIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_brain_route_")
        mem = os.path.join(self.temp, "memory")
        os.makedirs(mem)
        self.brain = _make_brain(mem, _noop_tools())

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_single_create_is_not_slow(self):
        """Single clean create → controller handles → FAST, no plan."""
        result = self.brain.handle('create n8n workflow named "Solo"')
        self.assertNotEqual(result["path"], "SLOW")

    def test_compound_request_goes_slow(self):
        result = self.brain.handle(
            'create n8n workflow "Compound" and then run it')
        self.assertEqual(result["path"], "SLOW")

    def test_brain_result_always_has_required_keys(self):
        for msg in [
            'create n8n workflow named "K1"',
            'create n8n workflow "K2" and then run it',
            "fix",
        ]:
            result = self.brain.handle(msg)
            for key in ("path", "handled", "response", "steps", "plan",
                        "verified", "verification"):
                self.assertIn(key, result, f"Missing key '{key}' for message: {msg!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
