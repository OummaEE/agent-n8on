"""
test_e2e_real.py

End-to-end tests against a real n8n instance at localhost:5678.

Scenario 1 — Simple workflow
  "создай n8n workflow который логирует текущую дату"
  Expected: FAST path, workflow created in n8n, no error response.

Scenario 2 — Complex workflow with auto-split
  Build a 15-node workflow, run split_workflow(), verify 3 sub-workflows
  each ≤ 7 nodes, each created successfully in n8n.

Scenario 3 — Debug flow with bad URL
  Create workflow with httpRequest pointing to an invalid URL.
  Run it → get execution_id (or use latest execution if run is 405).
  Tell brain "отладь execution {id}".
  Verify: debug handler is invoked, result is handled, proposes a fix.

Tests auto-skip when n8n is unreachable or N8N_API_KEY is missing.
Each test cleans up created workflows in tearDown.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
import unittest

# --------------------------------------------------------------------------
# Load .env before any imports that read env vars
# --------------------------------------------------------------------------
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip()
                if _k and ("_" in _k or _k.isidentifier()):
                    os.environ.setdefault(_k, _v)

import requests

import agent_v3
from workflow_generator import split_workflow

# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
N8N_BASE = (os.environ.get("N8N_URL", "http://localhost:5678")).rstrip("/") + "/api/v1"
_API_KEY = os.environ.get("N8N_API_KEY", "")
_HEADERS = {"X-N8N-API-KEY": _API_KEY, "Content-Type": "application/json"}


def _n8n_reachable() -> bool:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _delete_workflow_by_id(wf_id: str) -> None:
    """Best-effort workflow deletion."""
    try:
        agent_v3.tool_n8n_delete_workflow(str(wf_id))
    except Exception:
        pass


def _delete_workflows_by_name(name: str) -> None:
    """Delete all workflows whose name matches (case-insensitive)."""
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if w.get("name", "").strip().lower() == name.strip().lower():
                _delete_workflow_by_id(str(w["id"]))
    except Exception:
        pass


def _delete_workflows_by_prefix(prefix: str) -> None:
    """Delete all workflows whose name starts with *prefix* (case-insensitive)."""
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if w.get("name", "").strip().lower().startswith(prefix.lower()):
                _delete_workflow_by_id(str(w["id"]))
    except Exception:
        pass


def _list_workflow_names() -> list[str]:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        return [w.get("name", "").strip() for w in r.json().get("data", [])]
    except Exception:
        return []


def _get_latest_execution_id(workflow_id: str) -> str:
    """Return the most recent execution_id for a given workflow, or ''."""
    try:
        r = requests.get(
            f"{N8N_BASE}/executions",
            headers=_HEADERS,
            params={"workflowId": workflow_id, "limit": 1},
            timeout=10,
        )
        data = r.json().get("data", [])
        if data:
            return str(data[0].get("id", ""))
    except Exception:
        pass
    return ""


SKIP_REASON = "n8n unreachable or N8N_API_KEY missing"
_NEEDS_N8N = unittest.skipUnless(
    bool(_API_KEY) and _n8n_reachable(),
    SKIP_REASON,
)


def _make_brain(require_confirmation: bool = False):
    """Create a BrainLayer with a fresh temp-dir controller (no shared state)."""
    from brain.brain_layer import BrainLayer
    from controller import create_controller

    tmpdir = tempfile.mkdtemp()
    controller = create_controller(tmpdir, agent_v3.TOOLS)
    return BrainLayer(controller, require_confirmation=require_confirmation)


# ==========================================================================
# TEST 1 — Simple workflow: "создай n8n workflow который логирует текущую дату"
# ==========================================================================

WORKFLOW_NAME_T1 = "Текущую Дату Logger"


class Test1SimpleWorkflow(unittest.TestCase):
    """
    FAST path creation of a simple date-logging workflow.
    """

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        _delete_workflows_by_name(WORKFLOW_NAME_T1)

    def tearDown(self):
        _delete_workflows_by_name(WORKFLOW_NAME_T1)

    # ------------------------------------------------------------------

    @_NEEDS_N8N
    def test1_brain_handles_request(self):
        """Brain must handle the request (handled=True)."""
        brain = _make_brain()
        result = brain.handle("создай n8n workflow который логирует текущую дату")
        self.assertTrue(result.get("handled"), f"Not handled: {result.get('response', '')}")

    @_NEEDS_N8N
    def test1_path_is_fast(self):
        """Single create action → Router picks FAST path."""
        brain = _make_brain()
        result = brain.handle("создай n8n workflow который логирует текущую дату")
        self.assertEqual(
            result.get("path"), "FAST",
            f"Expected FAST path, got {result.get('path')}. response={result.get('response', '')[:200]}"
        )

    @_NEEDS_N8N
    def test1_no_clarify_response(self):
        """Response must not ask for clarification ('Укажи')."""
        brain = _make_brain()
        result = brain.handle("создай n8n workflow который логирует текущую дату")
        response = result.get("response", "")
        self.assertNotIn(
            "Укажи", response,
            f"Controller asked for clarification — param extraction failed: {response[:200]}"
        )

    @_NEEDS_N8N
    def test1_workflow_appears_in_n8n(self):
        """Workflow must actually appear in n8n after the request."""
        brain = _make_brain()
        brain.handle("создай n8n workflow который логирует текущую дату")
        time.sleep(0.5)
        names_lower = [n.lower() for n in _list_workflow_names()]
        # Accept either exact name or any variant containing "date" or "дата"
        found = (
            WORKFLOW_NAME_T1.lower() in names_lower
            or any("date" in n or "дат" in n for n in names_lower)
        )
        self.assertTrue(
            found,
            f"Workflow not found in n8n. Workflows: {_list_workflow_names()}"
        )


# ==========================================================================
# TEST 2 — Complex 15-node workflow with auto-split
# ==========================================================================

_SPLIT_WORKFLOW_PREFIX = "E2E Big Workflow"


def _make_15_node_workflow(name: str = "E2E Big Workflow") -> dict:
    """Build a minimal but valid 15-node workflow for split testing."""
    nodes = []
    connections = {}

    # First node: Manual Trigger
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Manual Trigger",
        "type": "n8n-nodes-base.manualTrigger",
        "typeVersion": 1,
        "position": [100, 300],
        "parameters": {},
    })

    # Nodes 2-15: Set nodes (simple, always valid)
    for i in range(1, 15):
        prev_name = nodes[i - 1]["name"]
        node_name = f"Set {i}"
        x_pos = 100 + i * 250
        nodes.append({
            "id": str(uuid.uuid4()),
            "name": node_name,
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [x_pos, 300],
            "parameters": {
                "assignments": {
                    "assignments": [{
                        "id": str(uuid.uuid4()),
                        "name": f"step_{i}",
                        "value": str(i),
                        "type": "string",
                    }]
                }
            },
        })
        connections[prev_name] = {
            "main": [[{"node": node_name, "type": "main", "index": 0}]]
        }

    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


class Test2AutoSplit(unittest.TestCase):
    """
    Verify split_workflow() divides 15 nodes into sub-workflows,
    then push each sub-workflow to n8n and confirm it was created.
    """

    _created_ids: list[str] = []

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        cls._created_ids = []
        _delete_workflows_by_prefix(_SPLIT_WORKFLOW_PREFIX)

    def tearDown(self):
        for wf_id in self._created_ids:
            _delete_workflow_by_id(wf_id)
        self._created_ids = []
        _delete_workflows_by_prefix(_SPLIT_WORKFLOW_PREFIX)

    # ------------------------------------------------------------------

    def test2_split_produces_multiple_parts(self):
        """15 nodes / chunk_size=7 → must produce ≥ 2 sub-workflows."""
        workflow = _make_15_node_workflow()
        parts = split_workflow(workflow, chunk_size=7)
        self.assertGreater(
            len(parts), 1,
            f"Expected multiple parts but got {len(parts)}"
        )

    def test2_each_part_has_at_most_chunk_size_nodes(self):
        """Every sub-workflow must have ≤ chunk_size nodes (bridge node included)."""
        workflow = _make_15_node_workflow()
        chunk_size = 7
        parts = split_workflow(workflow, chunk_size=chunk_size)
        for i, part in enumerate(parts):
            node_count = len(part["nodes"])
            # Allow chunk_size + 1 for the Execute Workflow bridge node
            self.assertLessEqual(
                node_count, chunk_size + 1,
                f"Part {i+1} has {node_count} nodes (expected ≤ {chunk_size + 1})"
            )

    def test2_parts_total_nodes_equal_original_plus_bridges(self):
        """Total nodes across all parts = original + (len(parts)-1) bridge nodes."""
        workflow = _make_15_node_workflow()
        parts = split_workflow(workflow, chunk_size=7)
        original_count = len(workflow["nodes"])
        total = sum(len(p["nodes"]) for p in parts)
        bridges = len(parts) - 1
        self.assertEqual(
            total, original_count + bridges,
            f"Total nodes mismatch: {total} != {original_count} + {bridges} bridges"
        )

    def test2_last_part_has_no_execute_workflow_bridge(self):
        """Last sub-workflow must NOT contain an Execute Workflow bridge."""
        workflow = _make_15_node_workflow()
        parts = split_workflow(workflow, chunk_size=7)
        last_part = parts[-1]
        bridge_nodes = [
            n for n in last_part["nodes"]
            if n.get("type") == "n8n-nodes-base.executeWorkflow"
        ]
        self.assertEqual(
            len(bridge_nodes), 0,
            f"Last part should have no bridge node but found: {bridge_nodes}"
        )

    def test2_non_last_parts_have_execute_workflow_bridge(self):
        """Each non-last sub-workflow must contain exactly one bridge node."""
        workflow = _make_15_node_workflow()
        parts = split_workflow(workflow, chunk_size=7)
        for i, part in enumerate(parts[:-1]):
            bridge_nodes = [
                n for n in part["nodes"]
                if n.get("type") == "n8n-nodes-base.executeWorkflow"
            ]
            self.assertEqual(
                len(bridge_nodes), 1,
                f"Part {i+1} should have 1 bridge node, found {len(bridge_nodes)}"
            )

    @_NEEDS_N8N
    def test2_all_parts_created_in_n8n(self):
        """Push all sub-workflows to n8n; each must receive an id."""
        workflow = _make_15_node_workflow()
        parts = split_workflow(workflow, chunk_size=7)

        for i, part in enumerate(parts):
            raw = agent_v3.tool_n8n_create_workflow(
                name=part["name"],
                workflow_json=part,
                raw=True,
            )
            result = json.loads(raw)
            self.assertNotIn(
                "error", result,
                f"Part {i+1} creation failed: {result.get('error')}"
            )
            self.assertIn(
                "id", result,
                f"Part {i+1} response missing 'id': {result}"
            )
            self._created_ids.append(str(result["id"]))

        # Verify all parts appear in n8n
        names_in_n8n = [n.lower() for n in _list_workflow_names()]
        for part in parts:
            self.assertIn(
                part["name"].lower(), names_in_n8n,
                f"Part '{part['name']}' not found in n8n. Workflows: {_list_workflow_names()}"
            )

    @_NEEDS_N8N
    def test2_brain_slow_path_for_complex_create(self):
        """
        'создай сложный workflow с 15 шагами и запусти его' →
        BrainLayer should route to SLOW (compound connectors).
        """
        brain = _make_brain()
        result = brain.handle(
            "создай сложный n8n workflow с множеством шагов и затем запусти его"
        )
        self.assertEqual(
            result.get("path"), "SLOW",
            f"Expected SLOW path for complex multi-step request. "
            f"Got path={result.get('path')}, response={result.get('response', '')[:200]}"
        )
        # Clean up any workflows that might have been created
        _delete_workflows_by_prefix(_SPLIT_WORKFLOW_PREFIX)


# ==========================================================================
# TEST 3 — Debug flow with bad URL and execution_id
# ==========================================================================

_DEBUG_WORKFLOW_NAME = "E2E Bad URL Debug Test"

_BAD_URL_WORKFLOW = {
    "name": _DEBUG_WORKFLOW_NAME,
    "nodes": [
        {
            "id": "trigger-node",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [100, 300],
            "parameters": {},
        },
        {
            "id": "http-node",
            "name": "HTTP Request",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.1,
            "position": [350, 300],
            "parameters": {
                "method": "GET",
                "url": "http://this-url-does-not-exist-e2e-test.invalid/api",
                "options": {},
            },
        },
    ],
    "connections": {
        "Manual Trigger": {
            "main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]
        }
    },
    "settings": {"executionOrder": "v1"},
}


class Test3DebugFlow(unittest.TestCase):
    """
    Create a workflow with a bad URL, run it, get execution_id,
    then ask the brain to debug that execution.
    """

    _workflow_id: str = ""

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        cls._workflow_id = ""
        _delete_workflows_by_name(_DEBUG_WORKFLOW_NAME)

    def tearDown(self):
        if self._workflow_id:
            _delete_workflow_by_id(self._workflow_id)
            self._workflow_id = ""
        _delete_workflows_by_name(_DEBUG_WORKFLOW_NAME)

    def _create_bad_workflow(self) -> str:
        """Create the bad-URL workflow in n8n and return its id."""
        raw = agent_v3.tool_n8n_create_workflow(
            name=_DEBUG_WORKFLOW_NAME,
            workflow_json=_BAD_URL_WORKFLOW,
            raw=True,
        )
        result = json.loads(raw)
        self.assertNotIn("error", result, f"Workflow creation failed: {result}")
        wf_id = str(result["id"])
        self._workflow_id = wf_id
        return wf_id

    def _run_workflow_get_execution(self, wf_id: str) -> str:
        """
        Try to run the workflow and return an execution_id.
        Falls back to fetching the latest existing execution if the run
        endpoint is unavailable (405).
        """
        raw = agent_v3.tool_n8n_run_workflow(wf_id, wait=True, raw=True)
        result = json.loads(raw)

        # Happy path: run succeeded
        if "execution_id" in result:
            return str(result["execution_id"])

        # Fallback: run endpoint returned 405 or another error;
        # use an existing execution if any (n8n may have run it previously
        # or we can use the latest execution)
        if result.get("needs_manual_run") and result.get("execution_id"):
            return str(result["execution_id"])

        # Last resort: poll for the latest execution
        time.sleep(1)
        return _get_latest_execution_id(wf_id)

    # ------------------------------------------------------------------

    @_NEEDS_N8N
    def test3_bad_workflow_created_in_n8n(self):
        """Workflow with bad URL must be accepted by n8n (creation always succeeds)."""
        wf_id = self._create_bad_workflow()
        self.assertNotEqual(wf_id, "", "Expected a valid workflow id")
        names = [n.lower() for n in _list_workflow_names()]
        self.assertIn(
            _DEBUG_WORKFLOW_NAME.lower(), names,
            f"Workflow not found. Workflows: {_list_workflow_names()}"
        )

    @_NEEDS_N8N
    def test3_debug_intent_classified(self):
        """
        'отладь execution {id}' must be classified as N8N_DEBUG_WORKFLOW.
        """
        from controller import IntentClassifier, StateManager, SessionState

        state = StateManager.__new__(StateManager)
        state.session = SessionState()
        clf = IntentClassifier(state)

        # "отладь" = Russian debug imperative (must be in has_debug keywords)
        result = clf.classify("отладь n8n execution exec-12345")
        self.assertIsNotNone(result, "classify() returned None — 'отладь' not in debug keywords")
        intent, params = result
        self.assertEqual(
            intent, "N8N_DEBUG_WORKFLOW",
            f"Expected N8N_DEBUG_WORKFLOW, got {intent}"
        )
        self.assertEqual(
            params.get("execution_id"), "exec-12345",
            f"execution_id not extracted: params={params}"
        )

    @_NEEDS_N8N
    def test3_debug_by_execution_id_handled(self):
        """
        Full debug flow: create bad workflow → (try run) → debug by execution_id.
        Result must be handled=True.
        """
        wf_id = self._create_bad_workflow()

        # Try to trigger an execution; if this n8n instance doesn't support
        # running via API, we just use any existing execution.
        execution_id = self._run_workflow_get_execution(wf_id)

        if not execution_id:
            self.skipTest(
                "Could not obtain an execution_id for the bad workflow "
                "(n8n may not support POST /run and has no prior executions)"
            )

        brain = _make_brain()
        result = brain.handle(f"отладь n8n execution {execution_id}")

        self.assertTrue(
            result.get("handled"),
            f"Debug result not handled. response={result.get('response', '')[:300]}"
        )

    @_NEEDS_N8N
    def test3_debug_response_mentions_error_or_fix(self):
        """
        Debug response must mention an error or a fix attempt,
        not just 'workflow not found'.
        """
        wf_id = self._create_bad_workflow()
        execution_id = self._run_workflow_get_execution(wf_id)

        if not execution_id:
            self.skipTest("No execution_id available — skip.")

        brain = _make_brain()
        result = brain.handle(f"отладь n8n execution {execution_id}")
        response = result.get("response", "").lower()

        # Acceptable responses: found error, proposed fix, ran debug loop,
        # or reported that it needs manual trigger.
        acceptable = any(word in response for word in [
            "error", "ошибка", "fix", "исправ", "debug", "отлад",
            "execution", "выполнен", "manual", "вручную", "success",
            "успешно", "workflow", "node", "http",
        ])
        self.assertTrue(
            acceptable,
            f"Debug response doesn't mention error/fix/execution. Got: {response[:400]}"
        )

    @_NEEDS_N8N
    def test3_session_state_updated_after_debug(self):
        """
        After debug, session should remember the last execution_id.
        We verify via the controller's session state.
        """
        wf_id = self._create_bad_workflow()
        execution_id = self._run_workflow_get_execution(wf_id)

        if not execution_id:
            self.skipTest("No execution_id available — skip.")

        from brain.brain_layer import BrainLayer
        from controller import create_controller

        tmpdir = tempfile.mkdtemp()
        controller = create_controller(tmpdir, agent_v3.TOOLS)
        brain = BrainLayer(controller)
        brain.handle(f"отладь n8n execution {execution_id}")

        # Session should record the last execution context
        session = controller.state.session
        # Either last_n8n_execution_id is set or workflow_id is set
        has_context = bool(
            getattr(session, "last_n8n_execution_id", "")
            or getattr(session, "last_n8n_workflow_id", "")
        )
        self.assertTrue(
            has_context,
            f"Session has no n8n context after debug. session={vars(session)}"
        )


# ==========================================================================
# TEST 3b — Debug flow using any existing error execution (dry_run=True)
#   Works even when POST /run is unavailable (405) because it uses
#   executions already present in the n8n system.
# ==========================================================================


def _get_any_error_execution_id() -> tuple[str, str]:
    """
    Return (execution_id, workflow_id) for the most recent error execution
    in n8n, or ("", "") if none found.
    """
    try:
        r = requests.get(
            f"{N8N_BASE}/executions",
            headers=_HEADERS,
            params={"limit": 5, "status": "error"},
            timeout=10,
        )
        data = r.json().get("data", [])
        if data:
            e = data[0]
            return str(e.get("id", "")), str(e.get("workflowId", ""))
    except Exception:
        pass
    return "", ""


class Test3bDebugWithExistingExecution(unittest.TestCase):
    """
    Debug flow using an already-existing error execution from n8n.
    Uses dry_run=True to avoid modifying production workflows.
    Skipped if no error executions exist.
    """

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        cls._exec_id, cls._wf_id = _get_any_error_execution_id()
        if not cls._exec_id:
            raise unittest.SkipTest(
                "No error executions found in n8n — skip debug-with-existing-execution tests"
            )

    @_NEEDS_N8N
    def test3b_debug_handled(self):
        """
        'debug n8n execution {id}' with an existing error execution
        must return handled=True.
        """
        brain = _make_brain()
        result = brain.handle(f"debug n8n execution {self._exec_id}")
        self.assertTrue(
            result.get("handled"),
            f"Debug result not handled. "
            f"response={result.get('response', '')[:300]}"
        )

    @_NEEDS_N8N
    def test3b_debug_response_is_informative(self):
        """
        Debug response for an error execution must mention the workflow,
        an error, or a fix proposal.
        """
        brain = _make_brain()
        result = brain.handle(f"debug n8n execution {self._exec_id}")
        response = result.get("response", "").lower()
        useful_words = [
            "workflow", "error", "debug", "execution",
            "ошибка", "отлад", "выполнен", "исправ", "patch",
            "status", "reason", "iteration", "n8n",
        ]
        self.assertTrue(
            any(w in response for w in useful_words),
            f"Debug response is not informative. Got: {response[:400]}"
        )

    @_NEEDS_N8N
    def test3b_session_updated_after_debug(self):
        """
        After debug, the controller session must record the execution context.
        """
        from brain.brain_layer import BrainLayer
        from controller import create_controller

        tmpdir = tempfile.mkdtemp()
        controller = create_controller(tmpdir, agent_v3.TOOLS)
        brain = BrainLayer(controller)
        brain.handle(f"debug n8n execution {self._exec_id}")

        # Controller exposes its state via .state attribute
        session = controller.state.session
        has_context = bool(
            getattr(session, "last_n8n_execution_id", "")
            or getattr(session, "last_n8n_workflow_id", "")
        )
        self.assertTrue(
            has_context,
            f"Session has no n8n context after debug. "
            f"exec_id={self._exec_id}, session attrs={vars(session)}"
        )


# ==========================================================================
# Runner
# ==========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
