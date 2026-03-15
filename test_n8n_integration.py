"""Integration test: create a simple workflow via real n8n API.

Skipped automatically if N8N_API_KEY or N8N_URL env vars are missing
or n8n is unreachable.
"""

import json
import os
import unittest

# Load .env manually (project has no python-dotenv dependency guaranteed).
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip()
                if _k and _k.isidentifier() or "_" in _k:
                    os.environ.setdefault(_k, _v)

import agent_v3


def _n8n_reachable() -> bool:
    try:
        import requests
        r = requests.get(
            f"{agent_v3._get_n8n_base_url()}/api/v1/workflows",
            headers={"X-N8N-API-KEY": agent_v3._get_n8n_api_key() or ""},
            timeout=5,
        )
        return r.status_code < 500
    except Exception:
        return False


SKIP_REASON = "n8n not reachable or N8N_API_KEY not set"
NEEDS_N8N = unittest.skipUnless(
    bool(agent_v3._get_n8n_api_key()) and _n8n_reachable(),
    SKIP_REASON,
)

SIMPLE_WORKFLOW = {
    "name": "__test_integration_workflow__",
    "nodes": [
        {
            "id": "node-trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [240, 300],
            "parameters": {},
        },
        {
            "id": "node-set",
            "name": "Set",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [480, 300],
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "assign-1",
                            "name": "message",
                            "value": "hello",
                            "type": "string",
                        }
                    ]
                }
            },
        },
    ],
    "connections": {
        "Manual Trigger": {
            "main": [[{"node": "Set", "type": "main", "index": 0}]]
        }
    },
    "settings": {"executionOrder": "v1"},
}

# Fields that n8n rejects (400 "must NOT have additional properties").
READ_ONLY_FIELDS = ("active", "id", "createdAt", "updatedAt", "versionId")


class N8NIntegrationCreateTest(unittest.TestCase):

    _created_id: str = ""

    def tearDown(self):
        """Delete the test workflow from n8n after each test."""
        if self._created_id:
            try:
                agent_v3.tool_n8n_delete_workflow(self._created_id)
            except Exception:
                pass
            self._created_id = ""

    @NEEDS_N8N
    def test_create_simple_workflow_no_400(self):
        """POST /workflows with clean payload must return 200 and an id."""
        raw = agent_v3.tool_n8n_create_workflow(
            name=SIMPLE_WORKFLOW["name"],
            workflow_json=SIMPLE_WORKFLOW,
            raw=True,
        )
        result = json.loads(raw)

        self.assertNotIn(
            "error", result,
            msg=f"n8n returned an error: {result.get('error')}",
        )
        self.assertIn("id", result, msg=f"No 'id' in response: {result}")
        self._created_id = str(result["id"])

    @NEEDS_N8N
    def test_sanitize_strips_read_only_before_post(self):
        """Sending a payload with read-only fields must still succeed (they are stripped)."""
        dirty = dict(SIMPLE_WORKFLOW)
        dirty["name"] = "__test_integration_dirty__"
        dirty["active"] = False
        dirty["id"] = "fake-id-123"
        dirty["createdAt"] = "2026-01-01T00:00:00Z"
        dirty["updatedAt"] = "2026-01-01T00:00:00Z"
        dirty["versionId"] = "v-fake"

        raw = agent_v3.tool_n8n_create_workflow(
            name=dirty["name"],
            workflow_json=dirty,
            raw=True,
        )
        result = json.loads(raw)

        self.assertNotIn(
            "error", result,
            msg=f"n8n returned 400 — read-only fields not stripped: {result.get('error')}",
        )
        self.assertIn("id", result)
        self._created_id = str(result["id"])

    @NEEDS_N8N
    def test_response_does_not_include_read_only_in_sent_payload(self):
        """Verify _sanitize_workflow_payload removes all forbidden fields."""
        from agent_v3 import _sanitize_workflow_payload

        dirty = {
            "name": "X",
            "active": True,
            "id": "abc",
            "createdAt": "t",
            "updatedAt": "t",
            "versionId": "v",
            "nodes": [],
            "connections": {},
        }
        clean = _sanitize_workflow_payload(dirty)

        for field in READ_ONLY_FIELDS:
            self.assertNotIn(
                field, clean,
                msg=f"_sanitize_workflow_payload did not remove '{field}'",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ---------------------------------------------------------------------------
# Webhook-based run tests (2026-03-04)
# ---------------------------------------------------------------------------

class WebhookRunTests(unittest.TestCase):
    """Integration tests for tool_n8n_run_workflow via webhook approach."""

    _wf_id: str = ""

    @classmethod
    def _api_key(cls):
        return agent_v3._get_n8n_api_key()

    @classmethod
    def _headers(cls):
        return {"X-N8N-API-KEY": cls._api_key()}

    def _create_simple_workflow(self, name="__test_wh_run__"):
        """Create a minimal manualTrigger→Set workflow and return its id."""
        import requests as _req
        payload = {
            "name": name,
            "nodes": [
                {"parameters": {}, "id": "tr-wh", "name": "Manual Trigger",
                 "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [240, 300]},
                {"parameters": {"assignments": {"assignments": [
                    {"id": "r1", "name": "ok", "value": "webhook-run", "type": "string"}
                ]}, "options": {}},
                 "id": "set-wh", "name": "Set", "type": "n8n-nodes-base.set",
                 "typeVersion": 3.4, "position": [460, 300]},
            ],
            "connections": {"Manual Trigger": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
            "settings": {"executionOrder": "v1"},
        }
        r = _req.post(
            f"{agent_v3._get_n8n_base_url()}/api/v1/workflows",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        self.assertIn(r.status_code, (200, 201), f"Create failed: {r.text[:200]}")
        return r.json().get("id", "")

    def _delete_workflow(self, wf_id):
        import requests as _req
        try:
            _req.post(f"{agent_v3._get_n8n_base_url()}/api/v1/workflows/{wf_id}/deactivate",
                      headers=self._headers(), timeout=10)
            _req.delete(f"{agent_v3._get_n8n_base_url()}/api/v1/workflows/{wf_id}",
                        headers=self._headers(), timeout=10)
        except Exception:
            pass

    @NEEDS_N8N
    def test_run_workflow_returns_execution_id(self):
        """tool_n8n_run_workflow must return an execution_id when run via webhook."""
        wf_id = self._create_simple_workflow("__test_wh_exec_id__")
        try:
            result_str = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            result = json.loads(result_str)
            self.assertNotIn("error", result, f"Run failed: {result}")
            self.assertTrue(result.get("webhook_triggered"), "webhook_triggered must be True")
            exec_id = result.get("execution_id", "")
            self.assertTrue(exec_id, "execution_id must be non-empty")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_run_workflow_execution_is_success(self):
        """Execution triggered via webhook must have status=success."""
        wf_id = self._create_simple_workflow("__test_wh_success__")
        try:
            result_str = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            result = json.loads(result_str)
            exec_id = result.get("execution_id", "")
            self.assertTrue(exec_id, "No execution_id returned")

            exec_str = agent_v3.tool_n8n_get_execution(exec_id, raw=True)
            exec_obj = json.loads(exec_str)
            self.assertEqual(exec_obj.get("status"), "success",
                             f"Expected success, got: {exec_obj.get('status')}")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_webhook_path_in_db_after_run(self):
        """After run, webhook_entity table must contain an entry for the workflow."""
        wf_id = self._create_simple_workflow("__test_wh_db__")
        try:
            agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            path = agent_v3._n8n_get_webhook_path(wf_id)
            self.assertTrue(path, "Webhook path must be in DB after run")
            self.assertIn(wf_id, path, "Webhook path must contain workflow_id")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_sanitize_payload_allows_put(self):
        """_sanitize_workflow_payload must produce a payload PUT /workflows accepts."""
        import requests as _req
        wf_id = self._create_simple_workflow("__test_sanitize_put__")
        try:
            wf = agent_v3._n8n_request("GET", f"/workflows/{wf_id}", timeout=20)
            self.assertNotIn("error", wf, f"GET failed: {wf}")
            payload = agent_v3._sanitize_workflow_payload(wf)
            r = _req.put(
                f"{agent_v3._get_n8n_base_url()}/api/v1/workflows/{wf_id}",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload, timeout=20,
            )
            self.assertEqual(r.status_code, 200,
                             f"PUT with sanitized payload failed {r.status_code}: {r.text[:200]}")
        finally:
            self._delete_workflow(wf_id)

# ---------------------------------------------------------------------------
# Long-name and schedule-trigger run tests (2026-03-04 bug fix)
# ---------------------------------------------------------------------------

class LongNameAndScheduleTriggerTests(unittest.TestCase):
    """Integration tests for the long-name truncation + schedule-trigger webhook bugs."""

    def _delete_workflow(self, wf_id):
        import requests as _req
        try:
            key = agent_v3._get_n8n_api_key()
            base = agent_v3._get_n8n_base_url()
            h = {"X-N8N-API-KEY": key}
            _req.post(f"{base}/api/v1/workflows/{wf_id}/deactivate", headers=h, timeout=10)
            _req.delete(f"{base}/api/v1/workflows/{wf_id}", headers=h, timeout=10)
        except Exception:
            pass

    def _create_workflow_with_long_name(self, name: str) -> str:
        """Create workflow directly via API (no sanitizer) to get a long-name workflow in n8n."""
        import requests as _req
        key = agent_v3._get_n8n_api_key()
        base = agent_v3._get_n8n_base_url()
        payload = {
            "name": name,
            "nodes": [
                {"parameters": {}, "id": "tr-ln", "name": "Manual Trigger",
                 "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [240, 300]},
                {"parameters": {"assignments": {"assignments": [
                    {"id": "r1", "name": "ok", "value": "long-name-test", "type": "string"}
                ]}, "options": {}},
                 "id": "set-ln", "name": "Set", "type": "n8n-nodes-base.set",
                 "typeVersion": 3.4, "position": [460, 300]},
            ],
            "connections": {"Manual Trigger": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
            "settings": {"executionOrder": "v1"},
        }
        r = _req.post(
            f"{base}/api/v1/workflows",
            headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        self.assertIn(r.status_code, (200, 201), f"Create failed: {r.text[:200]}")
        return r.json().get("id", "")

    def _create_workflow_with_schedule_trigger(self, name: str) -> str:
        import requests as _req
        key = agent_v3._get_n8n_api_key()
        base = agent_v3._get_n8n_base_url()
        payload = {
            "name": name,
            "nodes": [
                {"parameters": {"rule": {"interval": [{"field": "day"}]}},
                 "id": "tr-sc", "name": "Schedule Trigger",
                 "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [240, 300]},
                {"parameters": {"assignments": {"assignments": [
                    {"id": "r1", "name": "ok", "value": "schedule-test", "type": "string"}
                ]}, "options": {}},
                 "id": "set-sc", "name": "Set", "type": "n8n-nodes-base.set",
                 "typeVersion": 3.4, "position": [460, 300]},
            ],
            "connections": {"Schedule Trigger": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
            "settings": {"executionOrder": "v1"},
        }
        r = _req.post(
            f"{base}/api/v1/workflows",
            headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        self.assertIn(r.status_code, (200, 201), f"Create failed: {r.text[:200]}")
        return r.json().get("id", "")

    @NEEDS_N8N
    def test_run_workflow_with_long_name_succeeds(self):
        """Workflow whose name is >128 chars must still be triggerable via webhook."""
        long_name = ("@chan_" + "x" * 10 + ", ") * 15  # ~195 chars
        wf_id = self._create_workflow_with_long_name(long_name)
        try:
            result_str = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            result = json.loads(result_str)
            self.assertNotIn("error", result,
                             f"Expected success for long-name workflow, got: {result}")
            self.assertTrue(result.get("webhook_triggered"))
            self.assertTrue(result.get("execution_id"), "execution_id must be non-empty")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_run_workflow_with_schedule_trigger_succeeds(self):
        """Workflow with Schedule Trigger must be runnable on-demand via webhook."""
        wf_id = self._create_workflow_with_schedule_trigger("__test_schedule_trigger_run__")
        try:
            result_str = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            result = json.loads(result_str)
            self.assertNotIn("error", result,
                             f"Expected success for schedule-trigger workflow, got: {result}")
            self.assertTrue(result.get("webhook_triggered"))
            self.assertTrue(result.get("execution_id"), "execution_id must be non-empty")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_schedule_trigger_replaced_by_webhook_for_testing(self):
        """n8n v2.7.4 cannot activate schedule-trigger workflows (locale bug 'Unknown alias: und').

        _n8n_add_webhook_trigger must REPLACE the schedule trigger with a Webhook so
        activation succeeds and the workflow logic can be verified.
        """
        import requests as _req
        wf_id = self._create_workflow_with_schedule_trigger("__test_sched_replaced__")
        try:
            result_str = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
            result = json.loads(result_str)
            self.assertNotIn("error", result,
                             f"Expected success after schedule trigger replaced: {result}")
            key = agent_v3._get_n8n_api_key()
            base = agent_v3._get_n8n_base_url()
            r = _req.get(f"{base}/api/v1/workflows/{wf_id}",
                         headers={"X-N8N-API-KEY": key}, timeout=10)
            wf = r.json()
            types = [n.get("type") for n in wf.get("nodes", [])]
            self.assertNotIn("n8n-nodes-base.scheduleTrigger", types,
                             "Schedule Trigger must be replaced (activation fails with locale bug)")
            self.assertIn("n8n-nodes-base.webhook", types,
                          "Webhook node must replace the Schedule Trigger")
        finally:
            self._delete_workflow(wf_id)

    @NEEDS_N8N
    def test_sanitize_truncates_name_before_put(self):
        """_sanitize_workflow_payload must truncate name to ≤128 chars."""
        long_name = "Z" * 200
        payload = agent_v3._sanitize_workflow_payload({"name": long_name, "nodes": [], "connections": {}})
        self.assertLessEqual(len(payload["name"]), 128)

        # Also verify the truncated payload is actually accepted by n8n
        import requests as _req
        wf_id = self._create_workflow_with_long_name("__test_truncate_check__")
        try:
            wf = agent_v3._n8n_request("GET", f"/workflows/{wf_id}", timeout=20)
            clean = agent_v3._sanitize_workflow_payload(wf)
            r = _req.put(
                f"{agent_v3._get_n8n_base_url()}/api/v1/workflows/{wf_id}",
                headers={"X-N8N-API-KEY": agent_v3._get_n8n_api_key(), "Content-Type": "application/json"},
                json=clean, timeout=20,
            )
            self.assertEqual(r.status_code, 200,
                             f"PUT with truncated name failed {r.status_code}: {r.text[:200]}")
        finally:
            self._delete_workflow(wf_id)
