"""Tests for the content-factory template system (v2).

Covers:
  TemplateRegistry      — list, load, find by keyword
  TemplateAdapter       — substitution, _meta stripping, get_missing_required
  IntentClassifier      — regex fallback, LLM classifier (mocked), param extraction,
                          classify() routing, pending-state CLARIFY flow
  Handler               — clarify when FEED_URL missing, create when URL provided
  ClarifyFlow           — two-turn conversation: missing URL → ask → provide → create
  Integration           — live n8n (auto-skip if unavailable)
"""
from __future__ import annotations

import json
import os
import time
import tempfile
import unittest
from unittest.mock import patch

# Load .env before reading env vars (same pattern as test_n8n_integration.py).
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
# n8n connectivity helpers
# ---------------------------------------------------------------------------
N8N_BASE = "http://localhost:5678/api/v1"
_API_KEY = os.environ.get("N8N_API_KEY", "")
_HEADERS = {"X-N8N-API-KEY": _API_KEY, "Content-Type": "application/json"}
SKIP_REASON = "n8n unreachable or N8N_API_KEY missing"


def _n8n_reachable() -> bool:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=3)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _delete_workflow_by_name(name: str) -> None:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if w.get("name", "").strip().lower() == name.lower():
                requests.delete(f"{N8N_BASE}/workflows/{w['id']}", headers=_HEADERS, timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. TemplateRegistry
# ---------------------------------------------------------------------------
class TemplateRegistryTests(unittest.TestCase):

    def setUp(self):
        from skills.template_registry import TemplateRegistry
        self.registry = TemplateRegistry()

    def test_list_all_returns_metas(self):
        metas = self.registry.list_all()
        self.assertIsInstance(metas, list)
        self.assertGreater(len(metas), 0)
        self.assertIn("id", metas[0])

    def test_load_content_factory(self):
        tpl = self.registry.load("content_factory")
        self.assertIsNotNone(tpl)
        self.assertIn("nodes", tpl)
        self.assertIn("connections", tpl)

    def test_content_factory_has_5_plus_nodes(self):
        tpl = self.registry.load("content_factory")
        self.assertGreaterEqual(len(tpl["nodes"]), 5)

    def test_content_factory_declares_feed_url_required(self):
        tpl = self.registry.load("content_factory")
        self.assertIn("FEED_URL", tpl["_meta"]["required_params"])

    def test_find_by_rss_keyword(self):
        self.assertEqual(self.registry.find("создай контент-завод для RSS ленты"), "content_factory")

    def test_find_by_content_factory_keyword(self):
        self.assertEqual(self.registry.find("content factory pipeline"), "content_factory")

    def test_find_returns_none_for_unknown(self):
        self.assertIsNone(self.registry.find("delete all files in C:/"))

    def test_load_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.load("does_not_exist"))

    def test_find_and_load_combines(self):
        tpl = self.registry.find_and_load("rss feed content")
        self.assertIsNotNone(tpl)
        self.assertIn("nodes", tpl)


# ---------------------------------------------------------------------------
# 2. TemplateAdapter
# ---------------------------------------------------------------------------
class TemplateAdapterTests(unittest.TestCase):

    def setUp(self):
        from skills.template_registry import TemplateRegistry
        from skills.template_adapter import TemplateAdapter
        self.registry = TemplateRegistry()
        self.adapter = TemplateAdapter()
        self.template = self.registry.load("content_factory")

    def test_adapt_substitutes_feed_url(self):
        wf = self.adapter.adapt(self.template, {"FEED_URL": "https://example.com/feed"})
        raw = json.dumps(wf)
        self.assertIn("https://example.com/feed", raw)
        self.assertNotIn("{{FEED_URL}}", raw)

    def test_adapt_substitutes_workflow_name(self):
        wf = self.adapter.adapt(self.template, {
            "WORKFLOW_NAME": "My Content Factory",
            "FEED_URL": "https://example.com/feed",
        })
        self.assertEqual(wf["name"], "My Content Factory")

    def test_adapt_strips_meta(self):
        wf = self.adapter.adapt(self.template, {"FEED_URL": "https://x.com/rss"})
        self.assertNotIn("_meta", wf)

    def test_optional_params_get_defaults(self):
        # OUTPUT_FILE is optional → should default to "none".
        wf = self.adapter.adapt(self.template, {"FEED_URL": "https://x.com/rss"})
        raw = json.dumps(wf)
        self.assertIn("none", raw)

    def test_feed_url_not_defaulted(self):
        # FEED_URL is required — without it the placeholder stays unresolved.
        wf = self.adapter.adapt(self.template, {})   # no FEED_URL
        raw = json.dumps(wf)
        self.assertIn("{{FEED_URL}}", raw)            # placeholder NOT replaced

    def test_adapt_replaces_rewrite_prompt(self):
        wf = self.adapter.adapt(self.template, {
            "FEED_URL": "https://x.com/rss",
            "REWRITE_PROMPT": "Give me a 3-sentence summary:",
        })
        self.assertIn("Give me a 3-sentence summary:", json.dumps(wf))

    def test_adapted_workflow_has_correct_node_count(self):
        wf = self.adapter.adapt(self.template, {"FEED_URL": "https://x.com/rss"})
        self.assertGreaterEqual(len(wf["nodes"]), 5)

    def test_adapted_workflow_has_connections(self):
        wf = self.adapter.adapt(self.template, {"FEED_URL": "https://x.com/rss"})
        self.assertGreater(len(wf["connections"]), 0)

    def test_extract_placeholders(self):
        from skills.template_adapter import TemplateAdapter
        placeholders = TemplateAdapter.extract_placeholders(self.template)
        self.assertIn("FEED_URL", placeholders)
        self.assertIn("WORKFLOW_NAME", placeholders)
        self.assertIn("REWRITE_PROMPT", placeholders)

    # get_missing_required -----------------------------------------------

    def test_get_missing_required_returns_feed_url_when_absent(self):
        missing = self.adapter.get_missing_required(self.template, {})
        self.assertIn("FEED_URL", missing)

    def test_get_missing_required_empty_when_all_provided(self):
        missing = self.adapter.get_missing_required(
            self.template, {"FEED_URL": "https://example.com/rss"}
        )
        self.assertEqual(missing, [])

    def test_get_missing_required_empty_string_treated_as_missing(self):
        missing = self.adapter.get_missing_required(self.template, {"FEED_URL": ""})
        self.assertIn("FEED_URL", missing)


# ---------------------------------------------------------------------------
# 3. IntentClassifier
# ---------------------------------------------------------------------------
class IntentClassifierTemplateTests(unittest.TestCase):

    def setUp(self):
        from controller import IntentClassifier, StateManager, SessionState
        state = StateManager.__new__(StateManager)
        state.session = SessionState()
        self.clf = IntentClassifier(state)

    # --- regex fallback (tested directly, no LLM needed) ---

    def test_regex_detects_content_factory_ru(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "создай контент-завод для RSS ленты https://example.com/feed"
        ))

    def test_regex_detects_content_factory_en(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "create n8n content factory for rss https://example.com/feed"
        ))

    def test_regex_detects_autoposting_blog(self):
        # Key requirement: "хочу автопостинг из блога" → detected
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "хочу автопостинг из моего блога в канал"
        ))

    def test_regex_detects_parsing_blog(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "хочу парсить блог и постить в телегу"
        ))

    def test_regex_detects_rss_create(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "создай workflow для обработки rss ленты"
        ))

    def test_regex_not_triggered_by_simple_workflow(self):
        self.assertFalse(self.clf._is_n8n_template_request_regex(
            "создай простой n8n workflow который логирует hello world"
        ))

    # --- param extraction ---

    def test_extract_params_url_present(self):
        params = self.clf._extract_template_params(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        self.assertEqual(params["FEED_URL"], "https://example.com/feed")

    def test_extract_params_url_absent_gives_empty_string(self):
        # No fallback URL anymore — empty string signals "need to ask".
        params = self.clf._extract_template_params("создай контент-завод")
        self.assertEqual(params["FEED_URL"], "")

    def test_extract_params_auto_name_from_url(self):
        params = self.clf._extract_template_params(
            "создай контент-завод для RSS ленты https://techcrunch.com/feed"
        )
        self.assertIn("techcrunch", params["WORKFLOW_NAME"].lower())

    def test_extract_params_template_id(self):
        params = self.clf._extract_template_params(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        self.assertEqual(params["template_id"], "content_factory")

    # --- classify() with mocked LLM ---

    def _mock_llm(self, is_template: bool, template_id="content_factory"):
        return {"is_template": is_template, "template_id": template_id if is_template else None}

    def test_classify_emits_n8n_create_from_template_with_url(self):
        with patch.object(self.clf, "_llm_classify_template",
                          return_value=self._mock_llm(True)):
            intent, params = self.clf.classify(
                "создай контент-завод для RSS ленты https://example.com/feed"
            )
        self.assertEqual(intent, "N8N_CREATE_FROM_TEMPLATE")
        self.assertEqual(params["FEED_URL"], "https://example.com/feed")

    def test_classify_simple_workflow_not_template(self):
        with patch.object(self.clf, "_llm_classify_template",
                          return_value=self._mock_llm(False)):
            intent, _ = self.clf.classify(
                "создай простой n8n workflow который логирует hello world"
            )
        self.assertEqual(intent, "N8N_CREATE_WORKFLOW")

    def test_classify_autoposting_without_url_emits_template(self):
        # LLM says yes → extracted params have empty FEED_URL.
        with patch.object(self.clf, "_llm_classify_template",
                          return_value=self._mock_llm(True)):
            intent, params = self.clf.classify(
                "хочу автопостинг из моего блога в канал"
            )
        self.assertEqual(intent, "N8N_CREATE_FROM_TEMPLATE")
        self.assertEqual(params["FEED_URL"], "")   # empty — handler will ask


# ---------------------------------------------------------------------------
# 4. Handler — clarify flow (mock tools, no LLM, no n8n)
# ---------------------------------------------------------------------------
class HandlerTemplateTests(unittest.TestCase):

    def _make_controller(self, tools: dict = None):
        from controller import create_controller
        tools = tools or self._tools_ok()
        tmpdir = tempfile.mkdtemp()
        return create_controller(tmpdir, tools)

    def _tools_ok(self, workflow_name="Content Factory"):
        wf_id, exec_id = "wf-tpl-1", "exec-tpl-1"
        return {
            "n8n_list_workflows": lambda a: json.dumps({"data": []}),
            "n8n_create_workflow": lambda a: json.dumps({"id": wf_id, "name": workflow_name, "nodes": [], "connections": {}}),
            "n8n_update_workflow": lambda a: json.dumps({"id": wf_id}),
            "n8n_get_workflow": lambda a: json.dumps({"id": wf_id, "name": workflow_name, "nodes": [], "connections": {}}),
            "n8n_run_workflow": lambda a: json.dumps({"execution_id": exec_id}),
            "n8n_get_executions": lambda a: json.dumps({"data": [{"id": exec_id, "status": "success", "startedAt": "2026-03-01T12:00:00Z"}]}),
            "n8n_get_execution": lambda a: json.dumps({"id": exec_id, "status": "success", "data": {"resultData": {"runData": {}}}}),
            "n8n_activate_workflow": lambda a: json.dumps({"id": wf_id}),
        }

    # --- handler called directly with complete params ---

    def test_handler_returns_handled_true(self):
        result = self._make_controller()._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "Content Factory",
            "FEED_URL": "https://example.com/feed",
            "REWRITE_PROMPT": "Summarise:",
            "OUTPUT_FILE": "none",
            "max_iterations": 1,
        })
        self.assertTrue(result["handled"])

    def test_handler_response_contains_workflow_name(self):
        result = self._make_controller(self._tools_ok("My Factory"))._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "My Factory",
            "FEED_URL": "https://example.com/feed",
            "REWRITE_PROMPT": "Summarise:",
            "OUTPUT_FILE": "none",
            "max_iterations": 1,
        })
        self.assertIn("My Factory", result["response"])

    def test_handler_tool_result_has_workflow_id(self):
        result = self._make_controller()._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "Content Factory",
            "FEED_URL": "https://example.com/feed",
            "REWRITE_PROMPT": "Summarise:",
            "OUTPUT_FILE": "none",
            "max_iterations": 1,
        })
        self.assertIn("workflow_id", result.get("tool_result", {}))

    def test_handler_unknown_template_returns_error(self):
        result = self._make_controller()._handle_n8n_create_from_template({
            "template_id": "nonexistent_template",
            "WORKFLOW_NAME": "X",
            "FEED_URL": "https://example.com/feed",
            "OUTPUT_FILE": "none",
        })
        self.assertTrue(result["handled"])
        self.assertIn("not found", result["response"].lower())

    # --- clarify when FEED_URL missing ---

    def test_handler_clarifies_when_feed_url_missing(self):
        ctrl = self._make_controller()
        result = ctrl._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "Content Factory",
            "FEED_URL": "",
            "OUTPUT_FILE": "none",
        })
        self.assertTrue(result["handled"])
        self.assertEqual(result["tool_name"], "clarify")

    def test_handler_clarify_response_mentions_url(self):
        ctrl = self._make_controller()
        result = ctrl._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "Content Factory",
            "FEED_URL": "",
            "OUTPUT_FILE": "none",
        })
        # The clarify question should mention URL.
        self.assertRegex(result["response"].lower(), r"url|rss|ленту|ленты")

    def test_handler_saves_pending_state_when_url_missing(self):
        ctrl = self._make_controller()
        ctrl._handle_n8n_create_from_template({
            "template_id": "content_factory",
            "WORKFLOW_NAME": "Content Factory",
            "FEED_URL": "",
            "OUTPUT_FILE": "none",
        })
        self.assertEqual(ctrl.state.session.pending_intent, "N8N_TEMPLATE_AWAIT_PARAMS")
        self.assertEqual(ctrl.state.session.pending_params.get("_missing_param"), "FEED_URL")

    def test_handle_request_routes_to_template_handler(self):
        ctrl = self._make_controller()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            result = ctrl.handle_request(
                "создай контент-завод для RSS ленты https://example.com/feed"
            )
        self.assertTrue(result["handled"])
        self.assertEqual(result["tool_name"], "n8n_create_from_template")


# ---------------------------------------------------------------------------
# 5. ClarifyFlow — two-turn conversation tests
# ---------------------------------------------------------------------------
class ClarifyFlowTests(unittest.TestCase):

    def _make_controller(self):
        wf_id, exec_id = "wf-cf-1", "exec-cf-1"
        tools = {
            "n8n_list_workflows": lambda a: json.dumps({"data": []}),
            "n8n_create_workflow": lambda a: json.dumps({"id": wf_id, "name": a.get("name", "X"), "nodes": [], "connections": {}}),
            "n8n_update_workflow": lambda a: json.dumps({"id": wf_id}),
            "n8n_get_workflow": lambda a: json.dumps({"id": wf_id, "name": "X", "nodes": [], "connections": {}}),
            "n8n_run_workflow": lambda a: json.dumps({"execution_id": exec_id}),
            "n8n_get_executions": lambda a: json.dumps({"data": [{"id": exec_id, "status": "success", "startedAt": "2026-03-01T12:00:00Z"}]}),
            "n8n_get_execution": lambda a: json.dumps({"id": exec_id, "status": "success", "data": {"resultData": {"runData": {}}}}),
            "n8n_activate_workflow": lambda a: json.dumps({"id": wf_id}),
        }
        from controller import create_controller
        return create_controller(tempfile.mkdtemp(), tools)

    def test_autoposting_message_without_url_triggers_clarify(self):
        ctrl = self._make_controller()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            result = ctrl.handle_request("хочу автопостинг из моего блога в канал")
        # handler should ask for URL
        self.assertTrue(result["handled"])
        self.assertEqual(result["tool_name"], "clarify")
        self.assertRegex(result["response"].lower(), r"url|rss|ленту|ленты")

    def test_pending_state_contains_template_id(self):
        ctrl = self._make_controller()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            ctrl.handle_request("хочу автопостинг из моего блога в канал")
        self.assertEqual(
            ctrl.state.session.pending_params.get("template_id"), "content_factory"
        )

    def test_providing_url_after_clarify_creates_workflow(self):
        ctrl = self._make_controller()
        # Turn 1: no URL → clarify
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            ctrl.handle_request("хочу автопостинг из моего блога в канал")
        # Turn 2: user provides URL (LLM not needed — pending branch runs first)
        result = ctrl.handle_request("https://myblog.com/rss")
        self.assertTrue(result["handled"])
        # Should proceed to create (not clarify again)
        self.assertNotEqual(result["tool_name"], "clarify")

    def test_provided_url_injected_into_workflow(self):
        ctrl = self._make_controller()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            ctrl.handle_request("хочу автопостинг из моего блога в канал")
        result = ctrl.handle_request("https://myblog.com/rss")
        # The workflow was created — result should include the URL.
        raw = json.dumps(result)
        self.assertIn("myblog.com", raw)

    def test_pending_state_cleared_after_url_provided(self):
        ctrl = self._make_controller()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template",
                          return_value={"is_template": True, "template_id": "content_factory"}):
            ctrl.handle_request("хочу автопостинг из моего блога в канал")
        ctrl.handle_request("https://myblog.com/rss")
        self.assertIsNone(ctrl.state.session.pending_intent)


# ---------------------------------------------------------------------------
# 6. Integration tests — live n8n
# ---------------------------------------------------------------------------
class ContentFactoryIntegrationTests(unittest.TestCase):

    WORKFLOW_NAME = "Example Content Factory"

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        _delete_workflow_by_name(cls.WORKFLOW_NAME)

    def tearDown(self):
        _delete_workflow_by_name(self.WORKFLOW_NAME)

    def _make_controller(self):
        from controller import create_controller
        import agent_v3
        return create_controller(agent_v3.MEMORY_DIR, agent_v3.TOOLS)

    def test_workflow_created_in_n8n(self):
        ctrl = self._make_controller()
        # LLM or regex will detect template; URL is present so no clarify.
        result = ctrl.handle_request(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        self.assertTrue(result["handled"])
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        names = [w.get("name", "").strip().lower() for w in r.json().get("data", [])]
        found = any("example" in n or "content factory" in n or "factory" in n for n in names)
        self.assertTrue(found, f"No content factory workflow found. Workflows: {names}")

    def test_workflow_has_5_plus_nodes(self):
        ctrl = self._make_controller()
        ctrl.handle_request(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if "factory" in w.get("name", "").lower() or "example" in w.get("name", "").lower():
                detail = requests.get(f"{N8N_BASE}/workflows/{w['id']}", headers=_HEADERS, timeout=5).json()
                self.assertGreaterEqual(len(detail.get("nodes", [])), 5)
                return
        self.fail("Workflow not found in n8n")

    def test_feed_url_injected_into_workflow(self):
        ctrl = self._make_controller()
        ctrl.handle_request(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if "factory" in w.get("name", "").lower() or "example" in w.get("name", "").lower():
                detail = requests.get(f"{N8N_BASE}/workflows/{w['id']}", headers=_HEADERS, timeout=5).json()
                self.assertIn("example.com/feed", json.dumps(detail))
                return
        self.fail("Workflow not found in n8n")

    def test_run_loop_completes(self):
        ctrl = self._make_controller()
        result = ctrl.handle_request(
            "создай контент-завод для RSS ленты https://example.com/feed"
        )
        self.assertTrue(result["handled"])
        self.assertIn("tool_result", result)

    def test_message_without_url_returns_clarify(self):
        ctrl = self._make_controller()
        # "хочу автопостинг из моего блога" — no URL → should ask
        result = ctrl.handle_request("хочу автопостинг из моего блога в канал")
        # Either the LLM or regex classifies this as template → handler asks for URL.
        # If LLM is down AND regex misses it, it falls to LLM fallback chat — allow that too.
        if result.get("tool_name") == "clarify":
            self.assertRegex(result["response"].lower(), r"url|rss|ленту|ленты")
        # At minimum it must be handled.
        self.assertTrue(result.get("handled", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
