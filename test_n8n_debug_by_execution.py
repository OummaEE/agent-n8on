"""Tests for debug flow driven by execution_id.

Covers:
  1. Intent classifier extracts execution_id from various message formats.
  2. Classifier falls back to session context when no explicit target given.
  3. _handle_n8n_debug_workflow accepts execution_id, resolves workflowId,
     and uses the seed execution on iteration 1.
  4. If seed execution already succeeded → report SUCCESS immediately.
  5. If seed execution failed → apply patch, re-run, report.
  6. Session state persists last execution_id and workflow_id after the loop.
  7. Missing workflowId on execution → clear error returned.
"""

import json
import os
import shutil
import tempfile
import unittest

from controller import create_controller


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_execution(eid, status, workflow_id="wf-1", node_name="", error_msg=""):
    base = {
        "id": eid,
        "status": status,
        "workflowId": workflow_id,
        "workflowData": {"name": "My Flow"},
        "data": {"resultData": {}},
    }
    if status != "success" and (node_name or error_msg):
        base["data"]["resultData"] = {
            "lastNodeExecuted": node_name,
            "error": {"message": error_msg or "generic error"},
        }
    return base


def _make_tools(workflow_store, executions, run_order, state):
    """Return mock tools dict for the debug loop."""

    def n8n_list_workflows(args):
        return json.dumps({"data": [{"id": "wf-1", "name": "My Flow", "active": False}]})

    def n8n_get_workflow(args):
        return json.dumps(workflow_store)

    def n8n_get_execution(args):
        eid = args.get("execution_id", "")
        ex = executions.get(eid)
        if ex is None:
            return json.dumps({"error": f"execution {eid} not found"})
        return json.dumps(ex)

    def n8n_get_executions(args):
        eid = state["latest"]
        ex = executions.get(eid)
        if ex is None:
            return json.dumps({"data": []})
        return json.dumps({"data": [{"id": eid, "status": ex["status"], "startedAt": "2026-03-01T10:00:00Z"}]})

    def n8n_update_workflow(args):
        state["updates"] += 1
        workflow_store.clear()
        workflow_store.update(args["workflow_json"])
        return json.dumps({"id": "wf-1", "updated": True})

    def n8n_run_workflow(args):
        state["runs"] += 1
        if run_order:
            state["latest"] = run_order.pop(0)
        return json.dumps({"execution_id": state["latest"]})

    return {
        "n8n_list_workflows": n8n_list_workflows,
        "n8n_get_workflow": n8n_get_workflow,
        "n8n_get_execution": n8n_get_execution,
        "n8n_get_executions": n8n_get_executions,
        "n8n_update_workflow": n8n_update_workflow,
        "n8n_run_workflow": n8n_run_workflow,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class IntentExtractionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_debug_exec_")
        self.mem = os.path.join(self.temp, "memory")
        os.makedirs(self.mem)
        self.ctrl = create_controller(self.mem, {})

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    # --- execution_id extraction ---

    def test_extract_execution_id_plain(self):
        eid = self.ctrl.intent_classifier._extract_execution_id_from_message(
            "debug n8n execution 12345"
        )
        self.assertEqual(eid, "12345")

    def test_extract_execution_id_equals(self):
        eid = self.ctrl.intent_classifier._extract_execution_id_from_message(
            "fix n8n workflow, execution_id=abc-XYZ-99"
        )
        self.assertEqual(eid, "abc-XYZ-99")

    def test_extract_execution_id_colon(self):
        eid = self.ctrl.intent_classifier._extract_execution_id_from_message(
            "analyze n8n execution: exec-007"
        )
        # "execution: exec-007" → extraction group is "exec-007"
        self.assertTrue(len(eid) >= 2)

    def test_extract_execution_id_russian(self):
        eid = self.ctrl.intent_classifier._extract_execution_id_from_message(
            "почему упало n8n выполнение exec-999"
        )
        self.assertEqual(eid, "exec-999")

    def test_extract_execution_id_absent(self):
        eid = self.ctrl.intent_classifier._extract_execution_id_from_message(
            "debug n8n workflow My Flow"
        )
        self.assertEqual(eid, "")

    # --- classify emits execution_id in params ---

    def test_classify_debug_with_execution_id(self):
        result = self.ctrl.intent_classifier.classify(
            'debug n8n execution 42 why did it fail'
        )
        self.assertIsNotNone(result)
        intent, params = result
        self.assertEqual(intent, "N8N_DEBUG_WORKFLOW")
        self.assertEqual(params.get("execution_id"), "42")

    def test_classify_debug_with_workflow_name(self):
        result = self.ctrl.intent_classifier.classify(
            'debug my n8n workflow "Test Flow" until it runs'
        )
        self.assertIsNotNone(result)
        intent, params = result
        self.assertEqual(intent, "N8N_DEBUG_WORKFLOW")
        self.assertEqual(params.get("workflow_name"), "Test Flow")
        self.assertEqual(params.get("execution_id", ""), "")

    def test_classify_debug_falls_back_to_session_execution(self):
        # Pre-populate session context.
        self.ctrl.state.session.last_n8n_execution_id = "session-exec-1"
        self.ctrl.state.session.last_n8n_workflow_id = "wf-99"

        # Message that triggers debug intent but has no explicit execution_id or workflow name.
        result = self.ctrl.intent_classifier.classify(
            'n8n выполнение, почему ошибка'
        )
        self.assertIsNotNone(result)
        intent, params = result
        self.assertIn(intent, {"N8N_DEBUG_WORKFLOW", "N8N_FIX_WORKFLOW"})
        self.assertEqual(params.get("execution_id"), "session-exec-1")


class DebugByExecutionIdTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="jane_debug_exec_")
        self.mem = os.path.join(self.temp, "memory")
        os.makedirs(self.mem)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_seed_execution_success_no_run_needed(self):
        """If the provided execution is already successful, report SUCCESS without re-running."""
        wf = {"id": "wf-1", "name": "My Flow", "nodes": [
            {"id": "n1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
        ], "connections": {}}
        executions = {
            "exec-ok": _make_execution("exec-ok", "success", workflow_id="wf-1"),
        }
        state = {"latest": "exec-ok", "runs": 0, "updates": 0}
        tools = _make_tools(wf, executions, [], state)

        ctrl = create_controller(self.mem, tools)
        result = ctrl._handle_n8n_debug_workflow({
            "workflow_name": "",
            "execution_id": "exec-ok",
            "max_iterations": 3,
            "dry_run": False,
            "confirm_sensitive_patch": False,
        })

        self.assertTrue(result.get("handled"))
        report = result.get("tool_result", {})
        self.assertEqual(report.get("status"), "SUCCESS")
        self.assertEqual(state["runs"], 0, "Should not re-run a successful execution")

    def test_seed_execution_error_triggers_patch_and_rerun(self):
        """Seed execution is failing → patch applied → re-run → SUCCESS."""
        wf = {"id": "wf-1", "name": "My Flow", "nodes": [
            {"id": "n1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "parameters": {"httpMethod": "POSTTT", "path": "hook"}},
        ], "connections": {}}
        executions = {
            "exec-err": _make_execution("exec-err", "error", "wf-1", "Webhook", "Invalid value for httpMethod"),
            "exec-ok": _make_execution("exec-ok", "success", "wf-1"),
        }
        state = {"latest": "exec-err", "runs": 0, "updates": 0}
        tools = _make_tools(wf, executions, ["exec-ok"], state)

        ctrl = create_controller(self.mem, tools)
        result = ctrl._handle_n8n_debug_workflow({
            "workflow_name": "",
            "execution_id": "exec-err",
            "max_iterations": 3,
            "dry_run": False,
            "confirm_sensitive_patch": True,
        })

        self.assertTrue(result.get("handled"))
        report = result.get("tool_result", {})
        self.assertEqual(report.get("status"), "SUCCESS")
        self.assertGreaterEqual(state["updates"], 1, "Should have patched the workflow")
        self.assertGreaterEqual(state["runs"], 1, "Should have re-run after patch")

    def test_execution_not_found_returns_error(self):
        """Unknown execution_id → handled=True with error message."""
        tools = {
            "n8n_get_execution": lambda args: json.dumps({"error": "execution not found"}),
        }
        ctrl = create_controller(self.mem, tools)
        result = ctrl._handle_n8n_debug_workflow({
            "workflow_name": "",
            "execution_id": "nonexistent-999",
            "max_iterations": 3,
            "dry_run": False,
            "confirm_sensitive_patch": False,
        })
        self.assertTrue(result.get("handled"))
        self.assertIn("nonexistent-999", result.get("response", ""))

    def test_execution_missing_workflow_id_returns_error(self):
        """Execution exists but has no workflowId → clear error."""
        tools = {
            "n8n_get_execution": lambda args: json.dumps({"id": "exec-1", "status": "error"}),
        }
        ctrl = create_controller(self.mem, tools)
        result = ctrl._handle_n8n_debug_workflow({
            "workflow_name": "",
            "execution_id": "exec-1",
            "max_iterations": 3,
            "dry_run": False,
            "confirm_sensitive_patch": False,
        })
        self.assertTrue(result.get("handled"))
        self.assertIn("workflowId", result.get("response", ""))

    def test_session_state_updated_after_debug_loop(self):
        """After debug loop completes, last execution_id and workflow_id are in session.

        Uses execution_id path so _resolve_workflow is bypassed and wf-7 resolves correctly.
        """
        wf = {"id": "wf-7", "name": "Stateful Flow", "nodes": [
            {"id": "n1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "parameters": {"httpMethod": "BADMETHOD", "path": "hook"}},
        ], "connections": {}}
        executions = {
            "exec-A": _make_execution("exec-A", "error", "wf-7", "Webhook", "Invalid value for httpMethod"),
            "exec-B": _make_execution("exec-B", "success", "wf-7"),
        }
        state = {"latest": "exec-A", "runs": 0, "updates": 0}
        tools = _make_tools(wf, executions, ["exec-B"], state)

        ctrl = create_controller(self.mem, tools)
        # Provide execution_id so we skip _resolve_workflow and go directly to wf-7.
        ctrl._handle_n8n_debug_workflow({
            "workflow_name": "",
            "execution_id": "exec-A",
            "max_iterations": 3,
            "dry_run": False,
            "confirm_sensitive_patch": True,
        })

        self.assertEqual(ctrl.state.session.last_n8n_workflow_id, "wf-7")
        self.assertIsNotNone(ctrl.state.session.last_n8n_execution_id)

    def test_handle_request_routes_debug_by_execution(self):
        """handle_request('debug n8n execution exec-X ...') routes to debug handler."""
        wf = {"id": "wf-1", "name": "My Flow", "nodes": [
            {"id": "n1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
        ], "connections": {}}
        executions = {
            "exec-X": _make_execution("exec-X", "success", "wf-1"),
        }
        state = {"latest": "exec-X", "runs": 0, "updates": 0}
        tools = _make_tools(wf, executions, [], state)

        ctrl = create_controller(self.mem, tools)
        result = ctrl.handle_request(
            'debug n8n execution exec-X why did it fail'
        )
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_debug_workflow")

    def test_handle_request_debug_falls_back_to_session(self):
        """'n8n workflow error' with session context → uses last execution_id."""
        wf = {"id": "wf-1", "name": "My Flow", "nodes": [
            {"id": "n1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
        ], "connections": {}}
        executions = {
            "last-exec": _make_execution("last-exec", "success", "wf-1"),
        }
        state = {"latest": "last-exec", "runs": 0, "updates": 0}
        tools = _make_tools(wf, executions, [], state)

        ctrl = create_controller(self.mem, tools)
        ctrl.state.session.last_n8n_execution_id = "last-exec"

        result = ctrl.handle_request('n8n workflow error почему ошибка')
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_debug_workflow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
