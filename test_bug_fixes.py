"""
Tests for three bugs fixed in controller.py:

Bug 1: "Show all available n8n workflow templates" returned "GOOD" instead of template list.
Bug 2: Multiple Telegram channels via comma/space not parsed — agent re-asked TARGET.
Bug 3: After workflow creation n8n returns 405 on POST run — agent crashed instead of
       telling user to run manually.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch


def _make_controller(memory_dir, extra_tools=None):
    from controller import create_controller
    tools = {}
    if extra_tools:
        tools.update(extra_tools)
    return create_controller(memory_dir, tools)


class Bug1ListTemplatesIntent(unittest.TestCase):
    """Bug 1: 'Show all available n8n workflow templates' → must return template list, not 'GOOD'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jane_bug1_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _template_list_tool(self, args):
        return json.dumps({
            "text": "=== n8n Workflow Templates (5) ===\n  daily_website_monitor\n  email_digest\n  rss_to_telegram\n  kommun_parser_schedule\n  backup_files_daily"
        })

    def test_classify_show_templates_en(self):
        ctrl = _make_controller(self.tmp, {"n8n_template_list": self._template_list_tool})
        result = ctrl.intent_classifier.classify("Show all available n8n workflow templates")
        self.assertIsNotNone(result, "Should classify as a known intent, not fall through to LLM")
        intent, _ = result
        self.assertEqual(intent, "N8N_LIST_TEMPLATES")

    def test_classify_list_templates_variations(self):
        ctrl = _make_controller(self.tmp, {"n8n_template_list": self._template_list_tool})
        for msg in [
            "list n8n templates",
            "what templates are available",
            "which templates do you have",
            "display available templates",
            "покажи список шаблонов",
            "какие шаблоны доступны",
        ]:
            with self.subTest(msg=msg):
                result = ctrl.intent_classifier.classify(msg)
                self.assertIsNotNone(result, f"Should classify '{msg}'")
                self.assertEqual(result[0], "N8N_LIST_TEMPLATES", f"Wrong intent for: {msg}")

    def test_classify_create_not_confused_with_list(self):
        """'create a template workflow' should NOT trigger N8N_LIST_TEMPLATES."""
        ctrl = _make_controller(self.tmp, {"n8n_template_list": self._template_list_tool})
        result = ctrl.intent_classifier.classify("create a template workflow from rss")
        if result:
            self.assertNotEqual(result[0], "N8N_LIST_TEMPLATES")

    def test_handle_request_returns_template_list(self):
        ctrl = _make_controller(self.tmp, {"n8n_template_list": self._template_list_tool})
        result = ctrl.handle_request("Show all available n8n workflow templates")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_template_list")
        response = result.get("response", "")
        # Response must contain actual template info, not "GOOD"
        self.assertNotEqual(response.strip(), "GOOD", "Response must not be 'GOOD'")
        self.assertIn("template", response.lower())

    def test_handle_request_response_not_good(self):
        """Regression: ensure 'GOOD' string is never the sole response."""
        ctrl = _make_controller(self.tmp, {"n8n_template_list": self._template_list_tool})
        result = ctrl.handle_request("Show all available n8n workflow templates")
        response = result.get("response", "")
        self.assertNotEqual(response.strip().upper(), "GOOD")


class Bug2MultiChannelTargetParsing(unittest.TestCase):
    """Bug 2: Multiple Telegram channels via comma/space must be captured as a list, not re-asked."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jane_bug2_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get_classifier(self):
        ctrl = _make_controller(self.tmp, {})
        return ctrl.intent_classifier

    def test_extract_multiple_handles_comma(self):
        clf = self._get_classifier()
        params = clf._extract_template_params(
            "parse telegram channels @chan1, @chan2, @chan3"
        )
        target = params.get("TARGET", "")
        self.assertIn("@chan1", target)
        self.assertIn("@chan2", target)
        self.assertIn("@chan3", target)

    def test_extract_multiple_handles_space_separated(self):
        clf = self._get_classifier()
        params = clf._extract_template_params(
            "monitor telegram @news_channel @tech_channel @finance_channel"
        )
        target = params.get("TARGET", "")
        self.assertIn("@news_channel", target)
        self.assertIn("@tech_channel", target)
        self.assertIn("@finance_channel", target)

    def test_await_params_target_multi_channel(self):
        """When agent asks for TARGET and user replies with multiple @handles, all are captured."""
        ctrl = _make_controller(self.tmp, {})
        # Simulate pending state for TARGET param
        ctrl.state.session.pending_intent = "N8N_TEMPLATE_AWAIT_PARAMS"
        ctrl.state.session.pending_params = {
            "template_id": "social_parser",
            "PLATFORM": "telegram",
            "_missing_param": "TARGET",
        }
        ctrl.state.save()

        result = ctrl.intent_classifier.classify("@channel_one, @channel_two, @channel_three")
        self.assertIsNotNone(result)
        intent, pending = result
        self.assertEqual(intent, "N8N_CREATE_FROM_TEMPLATE")
        target = pending.get("TARGET", "")
        self.assertIn("@channel_one", target, "First channel must be captured")
        self.assertIn("@channel_two", target, "Second channel must be captured")
        self.assertIn("@channel_three", target, "Third channel must be captured")

    def test_await_params_target_single_channel_still_works(self):
        """Single channel still works after fix."""
        ctrl = _make_controller(self.tmp, {})
        ctrl.state.session.pending_intent = "N8N_TEMPLATE_AWAIT_PARAMS"
        ctrl.state.session.pending_params = {
            "template_id": "social_parser",
            "PLATFORM": "telegram",
            "_missing_param": "TARGET",
        }
        ctrl.state.save()

        result = ctrl.intent_classifier.classify("@mychannel")
        self.assertIsNotNone(result)
        _, pending = result
        self.assertEqual(pending.get("TARGET"), "@mychannel")

    def test_no_double_ask_when_multiple_channels_provided(self):
        """After user provides multiple channels, pending_intent must be cleared (no re-ask)."""
        ctrl = _make_controller(self.tmp, {})
        ctrl.state.session.pending_intent = "N8N_TEMPLATE_AWAIT_PARAMS"
        ctrl.state.session.pending_params = {
            "template_id": "social_parser",
            "PLATFORM": "telegram",
            "_missing_param": "TARGET",
        }
        ctrl.state.save()

        ctrl.intent_classifier.classify("@chan_a, @chan_b")
        # After classify, pending_intent must be cleared
        self.assertIsNone(ctrl.state.session.pending_intent)


class Bug3Graceful405OnWorkflowRun(unittest.TestCase):
    """Bug 3: When n8n returns 405 on POST /run after workflow creation, agent must NOT crash
    but instead return a friendly message with the n8n UI URL."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jane_bug3_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # All required params for 'content_factory' recipe (from n8n_recipes.py).
    _CF_PARAMS = {
        "sheet_id": "sheet-123",
        "sheet_range": "A:A",
        "notion_db_id": "notion-db-1",
        "notion_credential": "Notion account",
    }

    def _tools_with_webhook_run(self, workflow_id="wf-ok"):
        """Tool set where n8n_run_workflow succeeds via webhook (new default behavior)."""

        def n8n_list_workflows(args):
            return json.dumps({"data": []})

        def n8n_validate_workflow(args):
            return json.dumps({"valid": True, "errors": []})

        def n8n_create_workflow(args):
            return json.dumps({"id": workflow_id, "name": args.get("name", "Test")})

        def n8n_run_workflow(args):
            return json.dumps({
                "execution_id": "exec-wh-1",
                "webhook_triggered": True,
            })

        def n8n_get_execution(args):
            return json.dumps({"id": "exec-wh-1", "status": "success", "finished": True})

        def n8n_get_executions(args):
            return json.dumps({"data": [{"id": "exec-wh-1", "status": "success"}]})

        return {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_validate_workflow": n8n_validate_workflow,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_run_workflow": n8n_run_workflow,
            "n8n_get_execution": n8n_get_execution,
            "n8n_get_executions": n8n_get_executions,
        }

    def test_build_workflow_webhook_run_succeeds(self):
        """_handle_n8n_build_workflow now uses webhook to run — no 405 fallback."""
        tools = self._tools_with_webhook_run("wf-build-ok")
        ctrl = _make_controller(self.tmp, tools)

        result = ctrl._handle_n8n_build_workflow({
            "recipe_key": "content_factory",
            "workflow_name": "Test Webhook Workflow",
            "params": self._CF_PARAMS,
            "raw_user_message": "build content factory workflow",
        })

        self.assertTrue(result.get("handled"))
        response = result.get("response", "")
        # Must NOT crash or say error
        self.assertNotIn("crashed", response.lower())
        self.assertIn("workflow", response.lower())
        # Must NOT say needs_manual_run anymore
        tool_result = result.get("tool_result", {})
        self.assertFalse(tool_result.get("needs_manual_run"), "needs_manual_run must be False")

    def test_webhook_run_response_contains_workflow_id(self):
        """Webhook-run response must mention the workflow id."""
        tools = self._tools_with_webhook_run("wf-12345")
        ctrl = _make_controller(self.tmp, tools)

        result = ctrl._handle_n8n_build_workflow({
            "recipe_key": "content_factory",
            "workflow_name": "ID Check Workflow",
            "params": self._CF_PARAMS,
            "raw_user_message": "build workflow",
        })

        response = result.get("response", "")
        self.assertIn("wf-12345", response, "Response must include the workflow id")

    def test_create_from_template_webhook_run(self):
        """_handle_n8n_create_from_template now runs via webhook — no manual fallback."""
        wf_id = "tpl-ok"
        wf_name = "Test Template OK"
        list_calls = {"n": 0}

        def n8n_list_workflows(args):
            list_calls["n"] += 1
            if list_calls["n"] == 1:
                return json.dumps({"data": []})
            return json.dumps({"data": [{"id": wf_id, "name": wf_name, "active": False}]})

        def n8n_create_workflow(args):
            return json.dumps({"id": wf_id, "name": args.get("name", "Tpl")})

        def n8n_run_workflow(args):
            return json.dumps({"execution_id": "exec-tpl-1", "webhook_triggered": True})

        def n8n_get_executions(args):
            return json.dumps({"data": [{"id": "exec-tpl-1", "status": "success"}]})

        def n8n_get_workflow(args):
            return json.dumps({"id": wf_id, "name": wf_name, "nodes": [], "connections": {}})

        def n8n_get_execution(args):
            return json.dumps({"id": "exec-tpl-1", "status": "success", "finished": True})

        tools = {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_run_workflow": n8n_run_workflow,
            "n8n_get_executions": n8n_get_executions,
            "n8n_get_workflow": n8n_get_workflow,
            "n8n_get_execution": n8n_get_execution,
        }
        ctrl = _make_controller(self.tmp, tools)

        result = ctrl._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": wf_name,
            "FEED_URL": "https://example.com/feed",
            "REWRITE_PROMPT": "Summarise:",
            "OUTPUT_FILE": "none",
            "max_iterations": 1,
        })

        self.assertTrue(result.get("handled"))
        response = result.get("response", "")
        # Must not crash; must not say needs_manual_run
        self.assertNotIn("вручную", response.lower())
        self.assertNotIn("manually", response.lower())
        tool_result = result.get("tool_result", {})
        self.assertFalse(tool_result.get("needs_manual_run"))

    def test_successful_run_still_works(self):
        """When run succeeds (not 405), the normal flow is preserved."""
        def n8n_list_workflows(args):
            return json.dumps({"data": []})

        def n8n_validate_workflow(args):
            return json.dumps({"valid": True, "errors": []})

        def n8n_create_workflow(args):
            return json.dumps({"id": "wf-ok", "name": args.get("name", "OK")})

        def n8n_run_workflow(args):
            return json.dumps({"execution_id": "exec-ok"})

        def n8n_get_execution(args):
            return json.dumps({"id": "exec-ok", "status": "success", "data": {"resultData": {}}})

        tools = {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_validate_workflow": n8n_validate_workflow,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_run_workflow": n8n_run_workflow,
            "n8n_get_execution": n8n_get_execution,
        }
        ctrl = _make_controller(self.tmp, tools)

        result = ctrl._handle_n8n_build_workflow({
            "recipe_key": "content_factory",
            "workflow_name": "Success Workflow",
            "params": self._CF_PARAMS,
            "raw_user_message": "build workflow",
        })

        self.assertTrue(result.get("handled"))
        tool_result = result.get("tool_result", {})
        # Normal success: needs_manual_run must NOT be set
        self.assertFalse(tool_result.get("needs_manual_run", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
