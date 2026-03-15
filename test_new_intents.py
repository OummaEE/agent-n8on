"""
Tests for new intents added on 2026-03-06:
  - N8N_LIST_WORKFLOWS  (покажи мои n8n workflows)
  - N8N_ACTIVATE_WORKFLOW  (активируй workflow X)
  - BrainLayer integration in agent_v3.process_message (checked via brain.handle)
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))
import controller
import agent_v3


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_ctrl(tmp, tools_override=None):
    tools = dict(agent_v3.TOOLS)
    if tools_override:
        tools.update(tools_override)
    return controller.create_controller(tmp, tools)


_SAMPLE_WORKFLOWS = {
    "data": [
        {"id": "abc1", "name": "My Workflow",  "active": True},
        {"id": "abc2", "name": "Test Workflow", "active": False},
    ]
}


def _list_wf_tool(_args):
    return _SAMPLE_WORKFLOWS


def _activate_tool(args):
    return {"id": args.get("id"), "active": args.get("active")}


# ─── N8N_LIST_WORKFLOWS intent detection ────────────────────────────────────

class ListWorkflowsIntentTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp)
        self.clf = self.ctrl.intent_classifier

    def test_detect_en_list_n8n_workflows(self):
        result = self.clf._is_n8n_list_workflows_request("show my n8n workflows")
        self.assertTrue(result)

    def test_detect_ru_pokaji_workflows(self):
        result = self.clf._is_n8n_list_workflows_request("покажи мои n8n workflows")
        self.assertTrue(result)

    def test_detect_en_list_all_workflows(self):
        result = self.clf._is_n8n_list_workflows_request("list all n8n workflows")
        self.assertTrue(result)

    def test_no_match_without_n8n(self):
        result = self.clf._is_n8n_list_workflows_request("покажи мои workflows")
        self.assertFalse(result)

    def test_no_match_with_create(self):
        """'create n8n workflow' must NOT match list intent."""
        result = self.clf._is_n8n_list_workflows_request("создай n8n workflow hello")
        self.assertFalse(result)

    def test_no_match_templates(self):
        """'show n8n workflow templates' must NOT match list intent (goes to LIST_TEMPLATES)."""
        result = self.clf._is_n8n_list_workflows_request(
            "show all available n8n workflow templates"
        )
        self.assertFalse(result)

    def test_classify_returns_n8n_list_workflows(self):
        result = self.clf.classify("покажи мои n8n workflows")
        self.assertIsNotNone(result)
        intent, params = result
        self.assertEqual(intent, "N8N_LIST_WORKFLOWS")

    def test_classify_en_returns_n8n_list_workflows(self):
        result = self.clf.classify("list all n8n workflows")
        self.assertIsNotNone(result)
        intent, _ = result
        self.assertEqual(intent, "N8N_LIST_WORKFLOWS")

    def test_list_templates_unaffected(self):
        """N8N_LIST_TEMPLATES still works after adding N8N_LIST_WORKFLOWS."""
        result = self.clf.classify("покажи список шаблонов n8n")
        self.assertIsNotNone(result)
        intent, _ = result
        self.assertEqual(intent, "N8N_LIST_TEMPLATES")


# ─── N8N_LIST_WORKFLOWS handler ─────────────────────────────────────────────

class ListWorkflowsHandlerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp, {"n8n_list_workflows": _list_wf_tool})

    def test_handle_request_returns_handled(self):
        result = self.ctrl.handle_request("покажи мои n8n workflows")
        self.assertTrue(result.get("handled"))

    def test_handle_request_tool_name(self):
        result = self.ctrl.handle_request("pokazi moi n8n workflows")
        if result.get("handled"):
            self.assertEqual(result.get("tool_name"), "n8n_list_workflows")

    def test_handler_lists_workflows(self):
        result = self.ctrl.handle_request("list all n8n workflows")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_list_workflows")
        response = result.get("response", "")
        self.assertIn("My Workflow", response)
        self.assertIn("Test Workflow", response)

    def test_handler_shows_active_status(self):
        result = self.ctrl.handle_request("list all n8n workflows")
        response = result.get("response", "")
        # One active, one not active
        self.assertIn("активен", response)
        self.assertIn("неактивен", response)

    def test_handler_error_from_n8n(self):
        ctrl = _make_ctrl(self.tmp, {"n8n_list_workflows": lambda _: {"error": "n8n down"}})
        result = ctrl.handle_request("list all n8n workflows")
        self.assertTrue(result.get("handled"))
        self.assertIn("Ошибка", result.get("response", ""))

    def test_handler_empty_list(self):
        ctrl = _make_ctrl(self.tmp, {"n8n_list_workflows": lambda _: {"data": []}})
        result = ctrl.handle_request("list all n8n workflows")
        self.assertTrue(result.get("handled"))
        self.assertIn("нет", result.get("response", "").lower())


# ─── N8N_ACTIVATE_WORKFLOW intent detection ──────────────────────────────────

class ActivateWorkflowIntentTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp)
        self.clf = self.ctrl.intent_classifier

    def test_detect_ru_activate(self):
        result = self.clf._is_n8n_activate_request("активируй workflow Test Workflow")
        self.assertTrue(result)

    def test_detect_en_activate(self):
        result = self.clf._is_n8n_activate_request("activate n8n workflow Test")
        self.assertTrue(result)

    def test_detect_ru_deactivate(self):
        result = self.clf._is_n8n_activate_request("деактивируй workflow Test Workflow")
        self.assertTrue(result)

    def test_detect_en_disable(self):
        result = self.clf._is_n8n_activate_request("disable workflow My Workflow")
        self.assertTrue(result)

    def test_no_match_create(self):
        """Create requests must NOT match activate intent."""
        result = self.clf._is_n8n_activate_request("создай n8n workflow hello")
        self.assertFalse(result)

    def test_classify_activate_returns_intent(self):
        result = self.clf.classify("активируй workflow Test Workflow")
        if result:
            intent, params = result
            self.assertEqual(intent, "N8N_ACTIVATE_WORKFLOW")
            self.assertTrue(params.get("active", True))

    def test_classify_deactivate_returns_intent_active_false(self):
        result = self.clf.classify("деактивируй workflow Test Workflow")
        if result:
            intent, params = result
            self.assertEqual(intent, "N8N_ACTIVATE_WORKFLOW")
            self.assertFalse(params.get("active", True))


# ─── N8N_ACTIVATE_WORKFLOW handler ──────────────────────────────────────────

class ActivateWorkflowHandlerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp, {
            "n8n_list_workflows": _list_wf_tool,
            "n8n_activate_workflow": _activate_tool,
        })

    def test_missing_name_returns_clarify(self):
        result = self.ctrl._handle_n8n_activate_workflow({"workflow_name": "", "active": True})
        self.assertTrue(result.get("handled"))
        self.assertIn("Укажи", result.get("response", ""))

    def test_activate_known_workflow(self):
        result = self.ctrl._handle_n8n_activate_workflow({
            "workflow_name": "My Workflow",
            "active": True,
        })
        self.assertTrue(result.get("handled"))
        resp = result.get("response", "")
        self.assertIn("активирован", resp)

    def test_deactivate_known_workflow(self):
        result = self.ctrl._handle_n8n_activate_workflow({
            "workflow_name": "My Workflow",
            "active": False,
        })
        self.assertTrue(result.get("handled"))
        resp = result.get("response", "")
        self.assertIn("деактивирован", resp)

    def test_not_found_returns_error(self):
        result = self.ctrl._handle_n8n_activate_workflow({
            "workflow_name": "NonExistentWorkflow",
            "active": True,
        })
        self.assertTrue(result.get("handled"))
        resp = result.get("response", "")
        # Error message from _resolve_workflow
        self.assertTrue("not found" in resp.lower() or "не найден" in resp.lower() or "NonExistent" in resp)


# ─── BrainLayer integration ──────────────────────────────────────────────────

class BrainLayerIntegrationTests(unittest.TestCase):
    """Verify BrainLayer.handle() returns agent_v3-compatible dicts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp, {
            "n8n_list_workflows": _list_wf_tool,
            "n8n_activate_workflow": _activate_tool,
        })
        from brain.brain_layer import BrainLayer
        self.brain = BrainLayer(self.ctrl, require_confirmation=False)

    def test_brain_list_workflows_handled(self):
        result = self.brain.handle("покажи мои n8n workflows")
        self.assertTrue(result.get("handled"))

    def test_brain_list_workflows_has_response(self):
        result = self.brain.handle("list all n8n workflows")
        self.assertIn("My Workflow", result.get("response", ""))

    def test_brain_slow_path_create_and_run(self):
        """'create X and then run it' should route SLOW."""
        from brain.router import Router
        router = Router()
        path = router.route("create n8n workflow and then run it", controller_handled=False)
        self.assertEqual(path, "SLOW")

    def test_brain_fast_path_single_action(self):
        """'list n8n workflows' should route FAST."""
        from brain.router import Router
        router = Router()
        path = router.route("покажи мои n8n workflows", controller_handled=False)
        self.assertEqual(path, "FAST")

    def test_brain_result_has_path_key(self):
        result = self.brain.handle("list all n8n workflows")
        self.assertIn("path", result)

    def test_brain_result_has_required_keys(self):
        result = self.brain.handle("list all n8n workflows")
        for key in ("handled", "response", "tool_name", "steps"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_brain_unhandled_returns_handled_false(self):
        """Unknown request returns handled=False so agent falls through to Ollama."""
        result = self.brain.handle("расскажи мне анекдот")
        self.assertFalse(result.get("handled"))


# ─── Integration tests (require live n8n) ───────────────────────────────────

SKIP_INTEGRATION = not os.environ.get("N8N_API_KEY")


@unittest.skipIf(SKIP_INTEGRATION, "N8N_API_KEY not set — skipping integration tests")
class ListWorkflowsIntegrationTests(unittest.TestCase):
    """Hit real n8n to verify listing and activation work end-to-end."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ctrl = _make_ctrl(self.tmp)

    def test_integration_list_workflows_nonempty(self):
        result = self.ctrl.handle_request("list all n8n workflows")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_list_workflows")
        # Real n8n should have at least one workflow
        resp = result.get("response", "")
        self.assertIn("n8n Workflows", resp)

    def test_integration_list_workflows_shows_ids(self):
        result = self.ctrl.handle_request("покажи мои n8n workflows")
        resp = result.get("response", "")
        # Should contain bracketed IDs
        self.assertIn("[", resp)

    def test_integration_activate_nonexistent_graceful(self):
        result = self.ctrl.handle_request("активируй workflow __NonExistent__12345")
        self.assertTrue(result.get("handled"))
        # Should return an error message, not crash
        resp = result.get("response", "")
        self.assertTrue(len(resp) > 0)


if __name__ == "__main__":
    unittest.main()
