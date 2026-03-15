"""E2E integration test: full pipeline for a real n8n workflow creation request.

Flow under test:
  User message → BrainLayer.handle()
                    → Router (FAST, single action)
                    → controller.handle_request()
                        → IntentClassifier → N8N_CREATE_WORKFLOW
                        → _handle_n8n_create_workflow()
                            → n8n POST /workflows
  Assertions:
    - result["handled"] is True
    - result["path"]  == "FAST"
    - workflow appears in n8n via GET /workflows

Tests auto-skip when:
  - n8n is unreachable (localhost:5678)
  - N8N_API_KEY env-var is missing
"""
from __future__ import annotations

import os
import time
import unittest

# Load .env before reading env vars.
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
N8N_BASE = "http://localhost:5678/api/v1"
_API_KEY = os.environ.get("N8N_API_KEY", "")
_HEADERS = {"X-N8N-API-KEY": _API_KEY, "Content-Type": "application/json"}


def _n8n_reachable() -> bool:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=3)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _delete_workflow_by_name(name: str) -> None:
    """Best-effort cleanup."""
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if w.get("name", "").strip().lower() == name.lower():
                requests.delete(
                    f"{N8N_BASE}/workflows/{w['id']}",
                    headers=_HEADERS,
                    timeout=5,
                )
    except Exception:
        pass


SKIP_REASON = "n8n unreachable or N8N_API_KEY missing"


# ---------------------------------------------------------------------------
# Unit tests (no n8n needed)
# ---------------------------------------------------------------------------
class ParamExtractionTests(unittest.TestCase):
    """Verify _extract_n8n_create_params handles the E2E message correctly."""

    def setUp(self):
        from controller import IntentClassifier
        self.clf = IntentClassifier.__new__(IntentClassifier)

    def test_log_message_extracted(self):
        params = self.clf._extract_n8n_create_params(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertEqual(params["set_message"], "hello world")

    def test_name_auto_generated(self):
        params = self.clf._extract_n8n_create_params(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertEqual(params["workflow_name"], "Hello World Logger")

    def test_set_node_added(self):
        params = self.clf._extract_n8n_create_params(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertIn("set", params["node_types"])

    def test_logs_english_pattern(self):
        params = self.clf._extract_n8n_create_params(
            "create n8n workflow that logs hello world"
        )
        self.assertEqual(params["set_message"], "hello world")
        self.assertEqual(params["workflow_name"], "Hello World Logger")

    def test_prints_pattern(self):
        params = self.clf._extract_n8n_create_params(
            "create n8n workflow that prints test message"
        )
        self.assertEqual(params["set_message"], "test message")

    def test_quoted_name_takes_priority_over_auto(self):
        params = self.clf._extract_n8n_create_params(
            "создай n8n workflow 'My Logger' который логирует hello world"
        )
        self.assertEqual(params["workflow_name"], "My Logger")
        self.assertEqual(params["set_message"], "hello world")


class BrainRouteTests(unittest.TestCase):
    """Verify BrainLayer routes the E2E message correctly (no n8n needed)."""

    def setUp(self):
        from brain.router import Router
        self.router = Router()

    def test_message_routes_fast(self):
        msg = "создай простой n8n workflow который логирует hello world"
        path = self.router.route(msg, controller_handled=False)
        # Single-action create — no compound connectors → FAST
        self.assertEqual(path, "FAST")

    def test_classifier_emits_n8n_create(self):
        from controller import IntentClassifier, StateManager, SessionState
        state = StateManager.__new__(StateManager)
        state.session = SessionState()
        clf = IntentClassifier(state)
        intent, params = clf.classify(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertEqual(intent, "N8N_CREATE_WORKFLOW")
        self.assertEqual(params["workflow_name"], "Hello World Logger")
        self.assertEqual(params["set_message"], "hello world")


# ---------------------------------------------------------------------------
# Integration tests (require live n8n)
# ---------------------------------------------------------------------------
class BrainE2EIntegrationTests(unittest.TestCase):
    """Full pipeline: BrainLayer → Controller → real n8n API."""

    WORKFLOW_NAME = "Hello World Logger"

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        # Clean up any leftover from a previous test run.
        _delete_workflow_by_name(cls.WORKFLOW_NAME)

    def setUp(self):
        """Clear any stale session state (pending_intent etc.) before each test."""
        import agent_v3
        session_file = os.path.join(agent_v3.MEMORY_DIR, "session_state.json")
        if os.path.exists(session_file):
            import json as _json
            try:
                with open(session_file, encoding="utf-8") as _f:
                    data = _json.load(_f)
                data.pop("pending_intent", None)
                data.pop("pending_params", None)
                with open(session_file, "w", encoding="utf-8") as _f:
                    _json.dump(data, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def tearDown(self):
        _delete_workflow_by_name(self.WORKFLOW_NAME)

    def _make_brain(self):
        from brain.brain_layer import BrainLayer
        from controller import create_controller
        import agent_v3
        controller = create_controller(agent_v3.MEMORY_DIR, agent_v3.TOOLS)
        return BrainLayer(controller)

    # ------------------------------------------------------------------
    def test_brain_handles_request(self):
        brain = self._make_brain()
        result = brain.handle(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertTrue(result["handled"], f"Not handled: {result}")
        self.assertNotIn(
            "Укажи", result.get("response", ""),
            "Controller asked for a name — params extraction failed",
        )

    def test_workflow_appears_in_n8n(self):
        brain = self._make_brain()
        brain.handle("создай простой n8n workflow который логирует hello world")
        time.sleep(0.5)  # give n8n a moment
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        names = [w.get("name", "").strip().lower() for w in r.json().get("data", [])]
        self.assertIn(
            self.WORKFLOW_NAME.lower(), names,
            f"Workflow not found in n8n. Workflows: {names}",
        )

    def test_path_is_fast(self):
        brain = self._make_brain()
        result = brain.handle(
            "создай простой n8n workflow который логирует hello world"
        )
        self.assertEqual(result["path"], "FAST")

    def test_create_and_run_routes_slow(self):
        """'create ... and then run' must go through SLOW path."""
        brain = self._make_brain()
        result = brain.handle(
            "создай n8n workflow который логирует hello world и затем запусти его"
        )
        self.assertEqual(result["path"], "SLOW")


if __name__ == "__main__":
    unittest.main(verbosity=2)
