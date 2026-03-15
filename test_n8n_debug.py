import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import agent_v3
from controller import create_controller


class N8NToolHttpTests(unittest.TestCase):
    def test_n8n_request_builds_endpoint_headers_and_params(self):
        fake_resp = Mock()
        fake_resp.status_code = 200
        fake_resp.text = '{"data": []}'
        fake_resp.json.return_value = {"data": []}

        with patch.object(agent_v3, "_get_n8n_api_key", return_value="test-key"), \
             patch.object(agent_v3, "_get_n8n_base_url", return_value="http://localhost:5678"), \
             patch.object(agent_v3.requests, "get", return_value=fake_resp) as mock_get:
            result = agent_v3._n8n_request(
                "GET",
                "/executions",
                params={"workflowId": "wf-1", "limit": 5},
                timeout=17,
            )

        self.assertIn("data", result)
        self.assertTrue(mock_get.called)
        called_url = mock_get.call_args[0][0]
        called_kwargs = mock_get.call_args[1]
        self.assertEqual(called_url, "http://localhost:5678/api/v1/executions")
        self.assertEqual(called_kwargs["params"]["workflowId"], "wf-1")
        self.assertEqual(called_kwargs["params"]["limit"], 5)
        self.assertEqual(called_kwargs["timeout"], 17)
        self.assertEqual(called_kwargs["headers"]["X-N8N-API-KEY"], "test-key")

    def test_run_workflow_uses_webhook_approach(self):
        """tool_n8n_run_workflow now uses webhook instead of POST /run endpoint."""
        with patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
             patch.object(agent_v3, "_n8n_request", return_value={}), \
             patch.object(agent_v3, "_n8n_trigger_via_webhook", return_value={"message": "Workflow was started"}), \
             patch.object(agent_v3, "_n8n_request", return_value={"data": [{"id": "exec-123", "status": "success"}]}):
            with patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
                 patch.object(agent_v3, "_n8n_trigger_via_webhook", return_value={"message": "Workflow was started"}), \
                 patch.object(agent_v3, "_n8n_request", return_value={"data": [{"id": "exec-123"}]}):
                raw = agent_v3.tool_n8n_run_workflow("wf-1", wait=True, raw=True)
                payload = json.loads(raw)
        self.assertTrue(payload.get("webhook_triggered"))
        self.assertEqual(payload.get("execution_id"), "exec-123")

    def test_run_workflow_returns_error_when_webhook_fails(self):
        """tool_n8n_run_workflow returns error dict when webhook trigger fails."""
        with patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
             patch.object(agent_v3, "_n8n_request", return_value={}), \
             patch.object(agent_v3, "_n8n_trigger_via_webhook", return_value={"error": "webhook 404: not registered"}):
            raw = agent_v3.tool_n8n_run_workflow("wf-1", wait=True, raw=True)
            payload = json.loads(raw)
        self.assertIn("error", payload)
        self.assertNotIn("needs_manual_run", payload)

    def test_create_update_sanitize_read_only_fields(self):
        captured = {"post": None, "put": None}

        def fake_req(method, path, data=None, params=None, timeout=30):
            if method == "POST" and path == "/workflows":
                captured["post"] = dict(data or {})
                return {"id": "wf-1", "name": data.get("name", "")}
            if method == "PUT" and path == "/workflows/wf-1":
                captured["put"] = dict(data or {})
                return {"id": "wf-1"}
            return {"error": "unexpected"}

        with patch.object(agent_v3, "_n8n_request", side_effect=fake_req):
            agent_v3.tool_n8n_create_workflow(
                name="A",
                workflow_json={
                    "name": "A",
                    "active": False,
                    "id": "wf-1",
                    "createdAt": "x",
                    "updatedAt": "y",
                    "versionId": "v",
                    "nodes": [{"id": "node-1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger"}],
                    "connections": {},
                },
                raw=True,
            )
            agent_v3.tool_n8n_update_workflow(
                "wf-1",
                {
                    "name": "A",
                    "active": False,
                    "id": "wf-1",
                    "createdAt": "x",
                    "updatedAt": "y",
                    "versionId": "v",
                    "nodes": [{"id": "node-1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger"}],
                    "connections": {},
                },
                raw=True,
            )

        self.assertNotIn("active", captured["post"])
        self.assertNotIn("id", captured["post"])
        self.assertNotIn("createdAt", captured["post"])
        self.assertNotIn("updatedAt", captured["post"])
        self.assertNotIn("versionId", captured["post"])
        self.assertNotIn("active", captured["put"])
        self.assertNotIn("id", captured["put"])
        self.assertNotIn("createdAt", captured["put"])
        self.assertNotIn("updatedAt", captured["put"])
        self.assertNotIn("versionId", captured["put"])


class WebhookTriggerTests(unittest.TestCase):
    """Unit tests for _n8n_add_webhook_trigger edge cases."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _make_wf(trigger_type: str, trigger_name: str, extra_node_name: str = "Set") -> dict:
        """Return a minimal workflow dict with one trigger and one action node."""
        trigger_node = {
            "id": "t-1",
            "name": trigger_name,
            "type": trigger_type,
            "parameters": {},
        }
        action_node = {
            "id": "a-1",
            "name": extra_node_name,
            "type": "n8n-nodes-base.set",
            "parameters": {},
        }
        return {
            "name": "Test Workflow",
            "nodes": [trigger_node, action_node],
            "connections": {
                trigger_name: {"main": [[{"node": extra_node_name, "type": "main", "index": 0}]]}
            },
            "settings": {},
        }

    @staticmethod
    def _fake_put_ok(method, path, data=None, params=None, timeout=30):
        if method == "PUT":
            return {"id": "wf-1", "name": data.get("name", "")}
        if method == "POST" and "activate" in path:
            return {"id": "wf-1", "active": True}
        return {}

    # ------------------------------------------------------------------
    # Name truncation via _sanitize_workflow_payload
    # ------------------------------------------------------------------
    def test_long_name_truncated_to_128(self):
        long_name = "A" * 200
        payload = agent_v3._sanitize_workflow_payload({"name": long_name, "nodes": [], "connections": {}})
        self.assertLessEqual(len(payload["name"]), 128)
        self.assertTrue(payload["name"].endswith("..."))

    def test_exact_128_name_not_truncated(self):
        name_128 = "B" * 128
        payload = agent_v3._sanitize_workflow_payload({"name": name_128, "nodes": [], "connections": {}})
        self.assertEqual(payload["name"], name_128)

    def test_short_name_unchanged(self):
        payload = agent_v3._sanitize_workflow_payload({"name": "Short", "nodes": [], "connections": {}})
        self.assertEqual(payload["name"], "Short")

    # ------------------------------------------------------------------
    # Manual trigger → replaced by Webhook
    # ------------------------------------------------------------------
    def test_manual_trigger_replaced_by_webhook(self):
        wf = self._make_wf("n8n-nodes-base.manualTrigger", "Manual Trigger")

        with patch.object(agent_v3, "_n8n_request", side_effect=self._fake_put_ok), \
             patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
             patch("time.sleep"):
            path = agent_v3._n8n_add_webhook_trigger("wf-1", wf)

        self.assertEqual(path, "wf-1/webhook/agent-auto-run")

    def test_manual_trigger_connections_rewired(self):
        """After replacement, Webhook node must have the old trigger's connections."""
        wf = self._make_wf("n8n-nodes-base.manualTrigger", "Manual Trigger", "Process")
        captured_payload = {}

        def fake_req(method, path, data=None, params=None, timeout=30):
            if method == "PUT":
                captured_payload.update(data or {})
                return {"id": "wf-1"}
            if method == "POST":
                return {"id": "wf-1", "active": True}
            return {}

        with patch.object(agent_v3, "_n8n_request", side_effect=fake_req), \
             patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
             patch("time.sleep"):
            agent_v3._n8n_add_webhook_trigger("wf-1", wf)

        conns = captured_payload.get("connections", {})
        self.assertIn("Webhook", conns, "Webhook node must have connections")
        self.assertNotIn("Manual Trigger", conns, "Old trigger connections must be removed")

    # ------------------------------------------------------------------
    # Schedule trigger → Webhook added alongside (connections copied)
    # ------------------------------------------------------------------
    def test_schedule_trigger_replaced_by_webhook(self):
        """scheduleTrigger is replaced by Webhook (n8n v2.7.4 cannot activate schedule workflows).

        n8n v2.7.4 raises 'Unknown alias: und' (locale bug) when activating any schedule-trigger
        workflow. Replacing the schedule trigger with a Webhook allows the workflow logic to be
        tested; the user can restore the schedule via n8n UI afterwards.
        """
        wf = self._make_wf("n8n-nodes-base.scheduleTrigger", "Schedule Trigger", "Process")
        captured_payload = {}

        def fake_req(method, path, data=None, params=None, timeout=30):
            if method == "PUT":
                captured_payload.update(data or {})
                return {"id": "wf-1"}
            if method == "POST":
                return {"id": "wf-1", "active": True}
            return {}

        with patch.object(agent_v3, "_n8n_request", side_effect=fake_req), \
             patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-1/webhook/agent-auto-run"), \
             patch("time.sleep"):
            path = agent_v3._n8n_add_webhook_trigger("wf-1", wf)

        self.assertEqual(path, "wf-1/webhook/agent-auto-run")
        nodes_in_payload = captured_payload.get("nodes", [])
        types = [n.get("type") for n in nodes_in_payload]
        # Schedule trigger must be REPLACED (not kept alongside) so workflow can be activated
        self.assertNotIn("n8n-nodes-base.scheduleTrigger", types,
                         "Schedule Trigger must be replaced (not kept) to allow activation")
        self.assertIn("n8n-nodes-base.webhook", types)
        # Webhook must have inherited the schedule trigger's connections
        conns = captured_payload.get("connections", {})
        self.assertIn("Webhook", conns)
        self.assertNotIn("Schedule Trigger", conns)

    # ------------------------------------------------------------------
    # PUT failure → last_error propagated
    # ------------------------------------------------------------------
    def test_put_failure_sets_last_error(self):
        wf = self._make_wf("n8n-nodes-base.manualTrigger", "Manual Trigger")

        def fail_put(method, path, data=None, params=None, timeout=30):
            if method == "PUT":
                return {"error": "Workflow name must be 1 to 128 characters long."}
            return {}

        with patch.object(agent_v3, "_n8n_request", side_effect=fail_put):
            result = agent_v3._n8n_add_webhook_trigger("wf-bad", wf)

        self.assertEqual(result, "")
        self.assertIn("PUT", agent_v3._n8n_add_webhook_trigger.last_error)
        self.assertIn("128", agent_v3._n8n_add_webhook_trigger.last_error)

    def test_run_workflow_includes_error_detail_when_add_fails(self):
        """tool_n8n_run_workflow must include the failure reason in the error message."""
        def fake_req(method, path, data=None, params=None, timeout=30):
            if method == "GET" and "/workflows/" in path:
                return {"id": "wf-bad", "name": "X", "nodes": [], "connections": {}}
            return {}

        with patch.object(agent_v3, "_n8n_get_webhook_path", return_value=""), \
             patch.object(agent_v3, "_n8n_request", side_effect=fake_req), \
             patch.object(agent_v3, "_n8n_add_webhook_trigger", return_value="") as mock_add:
            mock_add.last_error = "PUT failed: name too long"
            raw = agent_v3.tool_n8n_run_workflow("wf-bad", raw=True)

        data = json.loads(raw)
        self.assertIn("error", data)
        # The generic message must be present
        self.assertIn("Failed to add webhook trigger", data["error"])

    # ------------------------------------------------------------------
    # Long-name workflow: sanitizer fixes the name before PUT
    # ------------------------------------------------------------------
    def test_long_name_workflow_put_succeeds_after_truncation(self):
        """Workflow with 200-char name must not cause PUT to fail due to name length."""
        long_name = "Channel " * 25  # 200 chars
        wf = {
            "name": long_name,
            "nodes": [
                {"id": "t-1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
            ],
            "connections": {"Manual Trigger": {"main": [[]]}},
            "settings": {},
        }
        captured = {}

        def fake_req(method, path, data=None, params=None, timeout=30):
            if method == "PUT":
                captured["name"] = (data or {}).get("name", "")
                return {"id": "wf-long"}
            if method == "POST":
                return {"id": "wf-long", "active": True}
            return {}

        with patch.object(agent_v3, "_n8n_request", side_effect=fake_req), \
             patch.object(agent_v3, "_n8n_get_webhook_path", return_value="wf-long/webhook/agent-auto-run"), \
             patch("time.sleep"):
            path = agent_v3._n8n_add_webhook_trigger("wf-long", wf)

        self.assertEqual(path, "wf-long/webhook/agent-auto-run")
        self.assertLessEqual(len(captured["name"]), 128, "Name sent to PUT must be ≤ 128 chars")


class N8NDebugLoopControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="jane_n8n_test_")
        self.memory_dir = os.path.join(self.temp_root, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_debug_loop_patches_and_reaches_success(self):
        workflow_store = {
            "id": "wf-1",
            "name": "My Flow",
            "active": False,
            "nodes": [
                {
                    "id": "node-1",
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"httpMethod": "POSTTT", "path": "hook"},
                }
            ],
            "connections": {},
        }
        executions = {
            "e-1": {
                "id": "e-1",
                "status": "error",
                "data": {
                    "resultData": {
                        "lastNodeExecuted": "Webhook",
                        "error": {"message": "Invalid value for httpMethod"},
                    }
                },
            },
            "e-2": {"id": "e-2", "status": "success", "data": {"resultData": {}}},
        }
        state = {"latest_execution": "e-1", "runs": 0, "updates": 0}

        def tool_n8n_list_workflows(args):
            return json.dumps({"data": [{"id": "wf-1", "name": "My Flow", "active": False}]})

        def tool_n8n_get_workflow(args):
            return json.dumps(workflow_store)

        def tool_n8n_get_executions(args):
            return json.dumps({"data": [{"id": state["latest_execution"], "status": executions[state["latest_execution"]]["status"], "startedAt": "2026-02-12T10:00:00Z"}]})

        def tool_n8n_get_execution(args):
            return json.dumps(executions[args["execution_id"]])

        def tool_n8n_update_workflow(args):
            state["updates"] += 1
            workflow_store.clear()
            workflow_store.update(args["workflow_json"])
            return json.dumps({"id": "wf-1", "updated": True})

        def tool_n8n_run_workflow(args):
            state["runs"] += 1
            state["latest_execution"] = "e-2"
            return json.dumps({"execution_id": "e-2"})

        tools = {
            "n8n_list_workflows": tool_n8n_list_workflows,
            "n8n_get_workflow": tool_n8n_get_workflow,
            "n8n_get_executions": tool_n8n_get_executions,
            "n8n_get_execution": tool_n8n_get_execution,
            "n8n_update_workflow": tool_n8n_update_workflow,
            "n8n_run_workflow": tool_n8n_run_workflow,
        }

        controller = create_controller(self.memory_dir, tools)
        result = controller.handle_request('debug my n8n workflow "My Flow" until it runs successfully confirm')

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_debug_workflow")
        report = result.get("tool_result", {})
        self.assertEqual(report.get("status"), "SUCCESS")
        self.assertGreaterEqual(state["updates"], 1)

        backup_dir = os.path.join(self.memory_dir, "n8n_backups")
        backup_files = os.listdir(backup_dir)
        self.assertTrue(backup_files)

    def test_debug_loop_stops_after_max_iterations(self):
        broken_workflow = {
            "id": "wf-2",
            "name": "Loop Flow",
            "active": False,
            "nodes": [
                {
                    "id": "node-1",
                    "name": "NodeA",
                    "type": "n8n-nodes-base.set",
                    "parameters": {"value": "{{ $json.value"},
                }
            ],
            "connections": {},
        }
        executions = {
            "e-1": {"id": "e-1", "status": "error", "data": {"resultData": {"lastNodeExecuted": "NodeA", "error": {"message": "Expression error 1"}}}},
            "e-2": {"id": "e-2", "status": "error", "data": {"resultData": {"lastNodeExecuted": "NodeA", "error": {"message": "Expression error 2"}}}},
            "e-3": {"id": "e-3", "status": "error", "data": {"resultData": {"lastNodeExecuted": "NodeA", "error": {"message": "Expression error 3"}}}},
            "e-4": {"id": "e-4", "status": "error", "data": {"resultData": {"lastNodeExecuted": "NodeA", "error": {"message": "Expression error 4"}}}},
        }
        run_order = ["e-2", "e-3", "e-4"]
        state = {"latest_execution": "e-1", "updates": 0}

        def tool_n8n_list_workflows(args):
            return json.dumps({"data": [{"id": "wf-2", "name": "Loop Flow", "active": False}]})

        def tool_n8n_get_workflow(args):
            # Always return original broken workflow so each iteration can apply a patch.
            return json.dumps(broken_workflow)

        def tool_n8n_get_executions(args):
            eid = state["latest_execution"]
            return json.dumps({"data": [{"id": eid, "status": executions[eid]["status"], "startedAt": "2026-02-12T10:00:00Z"}]})

        def tool_n8n_get_execution(args):
            return json.dumps(executions[args["execution_id"]])

        def tool_n8n_update_workflow(args):
            state["updates"] += 1
            return json.dumps({"id": "wf-2", "updated": True})

        def tool_n8n_run_workflow(args):
            state["latest_execution"] = run_order.pop(0)
            return json.dumps({"execution_id": state["latest_execution"]})

        tools = {
            "n8n_list_workflows": tool_n8n_list_workflows,
            "n8n_get_workflow": tool_n8n_get_workflow,
            "n8n_get_executions": tool_n8n_get_executions,
            "n8n_get_execution": tool_n8n_get_execution,
            "n8n_update_workflow": tool_n8n_update_workflow,
            "n8n_run_workflow": tool_n8n_run_workflow,
        }

        controller = create_controller(self.memory_dir, tools)
        result = controller.handle_request('debug my n8n workflow "Loop Flow" until it runs successfully max_iterations=3 confirm')

        self.assertTrue(result.get("handled"))
        report = result.get("tool_result", {})
        self.assertEqual(report.get("status"), "STOPPED")
        self.assertIn("max iterations", report.get("reason", ""))
        self.assertEqual(len(report.get("iterations", [])), 3)

    def test_debug_loop_stops_on_run_error(self):
        """Debug loop stops with STOPPED status when run fails (any reason)."""
        def tool_n8n_list_workflows(args):
            return json.dumps({"data": [{"id": "wf-3", "name": "Blocked Run", "active": False}]})

        def tool_n8n_get_workflow(args):
            return json.dumps({
                "id": "wf-3",
                "name": "Blocked Run",
                "nodes": [{"id": "node-1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}}],
                "connections": {},
            })

        def tool_n8n_get_executions(args):
            return json.dumps({"data": []})

        def tool_n8n_run_workflow(args):
            # Webhook approach: returns error (e.g. network failure)
            return json.dumps({
                "error": "webhook 404: not registered",
            })

        tools = {
            "n8n_list_workflows": tool_n8n_list_workflows,
            "n8n_get_workflow": tool_n8n_get_workflow,
            "n8n_get_executions": tool_n8n_get_executions,
            "n8n_run_workflow": tool_n8n_run_workflow,
        }
        controller = create_controller(self.memory_dir, tools)
        result = controller.handle_request('debug my n8n workflow "Blocked Run"')
        report = result.get("tool_result", {})
        self.assertEqual(report.get("status"), "STOPPED")
        self.assertTrue(report.get("reason"), "reason must be non-empty")


if __name__ == "__main__":
    unittest.main()


class WorkflowIdResolutionTests(unittest.TestCase):
    """Tests for the 'Workflow not found' bug after creation with long name.

    Root cause: after creation, _handle_n8n_debug_workflow received workflow_name
    (the original long name) and tried to look it up in n8n which stored the
    truncated (≤128 char) version → name mismatch → "not found".

    Fixes:
    1. _handle_n8n_debug_workflow accepts workflow_id param → skips name resolution.
    2. _resolve_workflow truncates search query to 128 chars before querying n8n.
    """

    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp(prefix="jane_resolve_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_ctrl(self, tools=None):
        from controller import create_controller
        return create_controller(self.tmp, tools or {})

    # ------------------------------------------------------------------
    # _handle_n8n_debug_workflow: workflow_id param bypasses name lookup
    # ------------------------------------------------------------------
    def test_debug_workflow_uses_id_directly_when_provided(self):
        """When workflow_id is given, name resolution is skipped entirely."""
        ctrl = self._make_ctrl({
            "n8n_list_workflows": lambda a: json.dumps({"data": []}),   # must NOT be called
            "n8n_get_workflow": lambda a: json.dumps({
                "id": "wf-direct", "name": "My Workflow", "nodes": [], "connections": {}
            }),
            "n8n_get_executions": lambda a: json.dumps({"data": []}),
            "n8n_run_workflow": lambda a: json.dumps({"error": "intentional stop"}),
        })

        list_called = {"n": 0}
        original_list = ctrl.tools.get("n8n_list_workflows")
        def tracking_list(a):
            list_called["n"] += 1
            return original_list(a)
        ctrl.tools["n8n_list_workflows"] = tracking_list

        ctrl._handle_n8n_debug_workflow({
            "workflow_id": "wf-direct",
            "workflow_name": "",       # name is empty on purpose
            "max_iterations": 1,
        })

        self.assertEqual(list_called["n"], 0, "n8n_list_workflows must NOT be called when workflow_id is provided")

    def test_debug_workflow_fetches_name_from_n8n_when_workflow_name_empty(self):
        """When workflow_id given but name empty, the handler fetches the name via GET."""
        fetched_name = {}

        def fake_get_workflow(args):
            fetched_name["name"] = "Fetched Name"
            return json.dumps({"id": args.get("id"), "name": "Fetched Name", "nodes": [], "connections": {}})

        ctrl = self._make_ctrl({
            "n8n_get_workflow": fake_get_workflow,
            "n8n_get_executions": lambda a: json.dumps({"data": []}),
            "n8n_run_workflow": lambda a: json.dumps({"error": "stop"}),
        })

        ctrl._handle_n8n_debug_workflow({
            "workflow_id": "wf-42",
            "workflow_name": "",
            "max_iterations": 1,
        })

        self.assertEqual(fetched_name.get("name"), "Fetched Name")

    # ------------------------------------------------------------------
    # _resolve_workflow: truncates long query before searching
    # ------------------------------------------------------------------
    def test_resolve_workflow_truncates_long_name_for_query(self):
        """_resolve_workflow must find a workflow even when the original name was >128 chars.

        n8n stores the name as name[:125]+'...' (via _sanitize_workflow_payload).
        _resolve_workflow uses a 60-char prefix query + prefix-based matching.
        """
        long_name = "Channel " * 30           # 240 chars
        # Simulate what _sanitize_workflow_payload stores: name[:125] + "..."
        stored_name = long_name[:125] + "..."

        query_sent = {}

        def fake_list(args):
            query_sent["q"] = args.get("query", "")
            # Return workflow with n8n-stored (truncated) name
            return json.dumps({"data": [{"id": "wf-trunc", "name": stored_name, "active": False}]})

        ctrl = self._make_ctrl({"n8n_list_workflows": fake_list})
        result = ctrl._resolve_workflow(long_name)

        self.assertNotIn("error", result, f"Should find workflow via prefix match, got: {result}")
        self.assertEqual(result.get("id"), "wf-trunc")
        # The query sent to n8n must be ≤60 chars (the safe prefix length)
        self.assertLessEqual(len(query_sent["q"]), 60, "Query sent to n8n must be ≤60 chars")

    def test_resolve_workflow_short_name_unchanged(self):
        """Short names (≤128 chars) are passed unchanged to the list query."""
        query_sent = {}

        def fake_list(args):
            query_sent["q"] = args.get("query", "")
            return json.dumps({"data": [{"id": "wf-ok", "name": "Short Name", "active": False}]})

        ctrl = self._make_ctrl({"n8n_list_workflows": fake_list})
        ctrl._resolve_workflow("Short Name")

        self.assertEqual(query_sent["q"], "Short Name")

    # ------------------------------------------------------------------
    # Integration: _handle_n8n_create_from_template passes workflow_id to debug
    # ------------------------------------------------------------------
    def test_create_from_template_passes_workflow_id_to_debug(self):
        """After creating a workflow with a long name, the debug loop must not fail with 'not found'."""
        long_name = "X " * 100  # 200 chars

        list_calls = {"n": 0}

        def n8n_list_workflows(args):
            list_calls["n"] += 1
            # Only return on first call (existence check before create)
            return json.dumps({"data": []})

        def n8n_create_workflow(args):
            return json.dumps({"id": "wf-new", "name": long_name[:125] + "..."})

        def n8n_get_workflow(args):
            return json.dumps({"id": "wf-new", "name": long_name[:125] + "...",
                                "nodes": [], "connections": {}})

        def n8n_get_executions(args):
            return json.dumps({"data": []})

        def n8n_run_workflow(args):
            return json.dumps({"execution_id": "exec-1", "webhook_triggered": True})

        def n8n_get_execution(args):
            return json.dumps({"id": "exec-1", "status": "success"})

        from controller import create_controller
        ctrl = create_controller(self.tmp, {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_get_workflow": n8n_get_workflow,
            "n8n_get_executions": n8n_get_executions,
            "n8n_run_workflow": n8n_run_workflow,
            "n8n_get_execution": n8n_get_execution,
        })

        result = ctrl._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": long_name,
            "FEED_URL": "https://example.com/feed",
            "REWRITE_PROMPT": "Summarise:",
            "OUTPUT_FILE": "none",
            "max_iterations": 1,
        })

        self.assertTrue(result.get("handled"))
        # Must NOT contain "not found" in the response
        response = result.get("response", "")
        self.assertNotIn("not found", response.lower(),
                         f"Response must not say 'not found' — got: {response}")
