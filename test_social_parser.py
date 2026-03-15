"""Tests for the social_parser template system.

Covers:
  TemplateRegistry      — list, load social_parser
  TemplateAdapter       — PLATFORM/TARGET not defaulted, OUTPUT gets default "none"
  IntentClassifier      — regex detection, param extraction, classify() routing
  ClarifyFlow           — two-turn (platform known, target missing)
                          three-turn (both platform and target missing)
  Integration           — live n8n (auto-skip if unavailable)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

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
# n8n connectivity helpers
# ---------------------------------------------------------------------------
N8N_BASE = "http://localhost:5678/api/v1"
_API_KEY = os.environ.get("N8N_API_KEY", "")
_HEADERS = {"X-N8N-API-KEY": _API_KEY, "Content-Type": "application/json"}
SKIP_REASON = "n8n unreachable or N8N_API_KEY missing"


def _n8n_reachable() -> bool:
    try:
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=3)
        return r.status_code == 200
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
# Helpers
# ---------------------------------------------------------------------------

def _make_controller():
    """Create a real Controller with a TEMP state dir (no shared session_state.json)."""
    from controller import create_controller
    import agent_v3
    return create_controller(tempfile.mkdtemp(), agent_v3.TOOLS)


def _make_classifier():
    from controller import IntentClassifier, StateManager
    tmpdir = tempfile.mkdtemp()
    sm = StateManager(tmpdir)
    return IntentClassifier(sm), sm


# ---------------------------------------------------------------------------
# 1. TemplateRegistry
# ---------------------------------------------------------------------------
class SocialParserRegistryTests(unittest.TestCase):

    def setUp(self):
        from skills.template_registry import TemplateRegistry
        self.registry = TemplateRegistry()

    def test_list_all_includes_social_parser(self):
        ids = [m.get("id") for m in self.registry.list_all()]
        self.assertIn("social_parser", ids)

    def test_load_social_parser(self):
        tpl = self.registry.load("social_parser")
        self.assertIsNotNone(tpl)
        self.assertIn("nodes", tpl)
        self.assertIn("connections", tpl)

    def test_social_parser_has_6_nodes(self):
        tpl = self.registry.load("social_parser")
        self.assertGreaterEqual(len(tpl["nodes"]), 6)

    def test_required_params_are_platform_and_target(self):
        tpl = self.registry.load("social_parser")
        req = tpl["_meta"]["required_params"]
        self.assertIn("PLATFORM", req)
        self.assertIn("TARGET", req)

    def test_find_by_social_keyword(self):
        tid = self.registry.find("social parser telegram")
        self.assertEqual(tid, "social_parser")

    def test_find_by_russian_keyword(self):
        tid = self.registry.find("парсинг соцсетей")
        self.assertEqual(tid, "social_parser")

    def test_find_by_telegram(self):
        tid = self.registry.find("telegram posts")
        self.assertEqual(tid, "social_parser")

    def test_meta_stripped_after_adapt(self):
        from skills.template_adapter import TemplateAdapter
        tpl = self.registry.load("social_parser")
        adapted = TemplateAdapter().adapt(tpl, {"PLATFORM": "telegram", "TARGET": "@chan"})
        self.assertNotIn("_meta", adapted)


# ---------------------------------------------------------------------------
# 2. TemplateAdapter
# ---------------------------------------------------------------------------
class SocialParserAdapterTests(unittest.TestCase):

    def setUp(self):
        from skills.template_registry import TemplateRegistry
        from skills.template_adapter import TemplateAdapter
        self.tpl = TemplateRegistry().load("social_parser")
        self.adapter = TemplateAdapter()

    def test_platform_not_defaulted(self):
        """PLATFORM is required — must not receive a default value."""
        missing = self.adapter.get_missing_required(self.tpl, {})
        self.assertIn("PLATFORM", missing)

    def test_target_not_defaulted(self):
        """TARGET is required — must not receive a default value."""
        missing = self.adapter.get_missing_required(self.tpl, {})
        self.assertIn("TARGET", missing)

    def test_output_gets_default_none(self):
        """OUTPUT is optional — adapter fills 'none' when absent."""
        result = self.adapter.adapt(self.tpl, {"PLATFORM": "telegram", "TARGET": "@chan"})
        raw = json.dumps(result)
        self.assertIn("none", raw)

    def test_get_missing_required_empty(self):
        missing = self.adapter.get_missing_required(self.tpl, {})
        self.assertIn("PLATFORM", missing)
        self.assertIn("TARGET", missing)

    def test_get_missing_required_partial(self):
        missing = self.adapter.get_missing_required(self.tpl, {"PLATFORM": "telegram"})
        self.assertIn("TARGET", missing)
        self.assertNotIn("PLATFORM", missing)

    def test_get_missing_required_full(self):
        missing = self.adapter.get_missing_required(
            self.tpl, {"PLATFORM": "telegram", "TARGET": "@mychannel"}
        )
        self.assertEqual(missing, [])

    def test_platform_substituted_in_code_node(self):
        result = self.adapter.adapt(self.tpl, {"PLATFORM": "instagram", "TARGET": "@user"})
        raw = json.dumps(result)
        self.assertIn("instagram", raw)

    def test_target_substituted_in_code_node(self):
        result = self.adapter.adapt(self.tpl, {"PLATFORM": "telegram", "TARGET": "@mychannel"})
        raw = json.dumps(result)
        self.assertIn("mychannel", raw)

    def test_workflow_name_substituted(self):
        result = self.adapter.adapt(
            self.tpl,
            {"PLATFORM": "twitter", "TARGET": "@dev", "WORKFLOW_NAME": "Dev Twitter Parser"},
        )
        self.assertEqual(result["name"], "Dev Twitter Parser")

    def test_6_nodes_preserved(self):
        result = self.adapter.adapt(self.tpl, {"PLATFORM": "telegram", "TARGET": "@chan"})
        self.assertGreaterEqual(len(result["nodes"]), 6)


# ---------------------------------------------------------------------------
# 3. IntentClassifier — regex detection
# ---------------------------------------------------------------------------
class SocialParserIntentTests(unittest.TestCase):

    def setUp(self):
        self.clf, _ = _make_classifier()

    # --- Regex detection ---

    def test_regex_detects_telegram_posts(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "хочу собирать посты из телеграм канала"
        ))

    def test_regex_detects_instagram_parse(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "парсить instagram аккаунты"
        ))

    def test_regex_detects_twitter_collect(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "нужно собирать посты из twitter"
        ))

    def test_regex_detects_social_parser_kw(self):
        self.assertTrue(self.clf._is_n8n_template_request_regex(
            "создай парсер соцсетей"
        ))

    def test_regex_not_triggered_by_simple_bot(self):
        """'создай телеграм бот' should NOT match social_parser template."""
        self.assertFalse(self.clf._is_n8n_template_request_regex(
            "создай телеграм бот"
        ))

    def test_regex_not_triggered_by_plain_workflow(self):
        self.assertFalse(self.clf._is_n8n_template_request_regex("создай workflow"))

    def test_detect_template_id_social(self):
        tid = self.clf._detect_template_id_from_message(
            "парсить telegram посты"
        )
        self.assertEqual(tid, "social_parser")

    def test_detect_template_id_content_factory(self):
        tid = self.clf._detect_template_id_from_message(
            "создай контент-завод для rss"
        )
        self.assertEqual(tid, "content_factory")

    # --- Param extraction ---

    def test_extract_platform_telegram(self):
        p = self.clf._extract_template_params("парсить посты из telegram канала")
        self.assertEqual(p["PLATFORM"], "telegram")

    def test_extract_platform_instagram(self):
        p = self.clf._extract_template_params("собирать посты из instagram")
        self.assertEqual(p["PLATFORM"], "instagram")

    def test_extract_target_at_handle(self):
        p = self.clf._extract_template_params(
            "хочу собирать посты из телеграм канала @durov"
        )
        self.assertEqual(p["TARGET"], "@durov")

    def test_extract_target_channel_keyword(self):
        p = self.clf._extract_template_params(
            "парсить telegram канал news_channel"
        )
        self.assertEqual(p["TARGET"], "news_channel")

    def test_extract_target_empty_when_absent(self):
        p = self.clf._extract_template_params("парсить посты из telegram")
        self.assertEqual(p["TARGET"], "")

    def test_extract_platform_empty_when_absent(self):
        p = self.clf._extract_template_params("хочу собирать посты из соцсетей")
        self.assertEqual(p["PLATFORM"], "")

    def test_auto_name_from_target(self):
        p = self.clf._extract_template_params(
            "парсить telegram канал @mychan"
        )
        self.assertIn("mychan", p["WORKFLOW_NAME"].lower())

    def test_auto_name_from_platform(self):
        p = self.clf._extract_template_params("собирать посты из twitter")
        self.assertIn("twitter", p["WORKFLOW_NAME"].lower())

    def test_template_id_is_social_parser(self):
        p = self.clf._extract_template_params(
            "хочу собирать посты из телеграм канала"
        )
        self.assertEqual(p["template_id"], "social_parser")

    # --- classify() routing ---

    def test_classify_routes_to_n8n_create_from_template(self):
        with patch.object(self.clf, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = self.clf.classify("парсить посты из telegram @chan")
            self.assertIsNotNone(result)
            intent, params = result
            self.assertEqual(intent, "N8N_CREATE_FROM_TEMPLATE")
            self.assertEqual(params.get("template_id"), "social_parser")

    def test_classify_sets_platform_from_message(self):
        with patch.object(self.clf, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = self.clf.classify("собирать посты из instagram @user")
            self.assertIsNotNone(result)
            _, params = result
            self.assertEqual(params.get("PLATFORM"), "instagram")


# ---------------------------------------------------------------------------
# 4. Handler tests (mock n8n)
# ---------------------------------------------------------------------------
class SocialParserHandlerTests(unittest.TestCase):

    def _make_ctrl_mock_n8n(self):
        ctrl = _make_controller()
        # Mock _call_tool_json to avoid real n8n calls.
        ctrl._call_tool_json = MagicMock(return_value={"data": [], "id": "mock-id-123"})
        return ctrl

    def test_handler_clarifies_when_platform_missing(self):
        ctrl = self._make_ctrl_mock_n8n()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = ctrl.handle_request("хочу собирать посты из соцсетей")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "clarify")
        self.assertIn("PLATFORM", result["tool_result"]["missing_param"])

    def test_handler_clarify_mentions_platform_options(self):
        ctrl = self._make_ctrl_mock_n8n()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = ctrl.handle_request("хочу собирать посты из соцсетей")
        resp = result.get("response", "").lower()
        self.assertTrue(
            "telegram" in resp or "платформ" in resp or "platform" in resp,
            f"Response should mention platform options: {resp!r}"
        )

    def test_handler_clarifies_when_target_missing(self):
        """Platform is known, target missing → ask for target."""
        ctrl = self._make_ctrl_mock_n8n()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = ctrl.handle_request("хочу собирать посты из telegram")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "clarify")
        self.assertIn("TARGET", result["tool_result"]["missing_param"])

    def test_handler_clarify_mentions_channel(self):
        ctrl = self._make_ctrl_mock_n8n()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = ctrl.handle_request("хочу собирать посты из telegram")
        resp = result.get("response", "").lower()
        self.assertTrue(
            "канал" in resp or "аккаунт" in resp or "channel" in resp or "@" in resp,
            f"Response should mention channel/account: {resp!r}"
        )

    def test_handler_saves_pending_state(self):
        ctrl = self._make_ctrl_mock_n8n()
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            ctrl.handle_request("хочу собирать посты из telegram")
        state = ctrl.state.session
        self.assertEqual(state.pending_intent, "N8N_TEMPLATE_AWAIT_PARAMS")
        self.assertIn("TARGET", state.pending_params.get("_missing_param", ""))

    def test_handler_returns_handled_true_with_full_params(self):
        ctrl = self._make_ctrl_mock_n8n()
        # Mock n8n to return a workflow id.
        # Call sequence after fix (workflow_id passed directly to debug handler):
        #   1. n8n_list_workflows  (existence check before create)
        #   2. n8n_create_workflow
        #   3. n8n_get_workflow    (debug handler loads full workflow JSON)
        #   4. n8n_get_executions  (iteration 1: no prior executions)
        #   5. n8n_run_workflow
        #   6. n8n_get_execution   (check status → success)
        ctrl._call_tool_json = MagicMock(side_effect=[
            {"data": []},                                              # 1. list_workflows → empty
            {"id": "wf-123", "name": "Mychan Social Parser"},         # 2. create
            {"id": "wf-123", "name": "Mychan Social Parser",          # 3. get_workflow (debug)
             "nodes": [], "connections": {}},
            {"data": []},                                              # 4. get_executions → empty
            {"execution_id": "exec-1", "webhook_triggered": True},    # 5. run_workflow
            {"id": "exec-1", "status": "success", "finished": True},  # 6. get_execution
        ])
        with patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": "social_parser",
        }):
            result = ctrl.handle_request(
                "парсить telegram канал @mychan"
            )
        self.assertTrue(result.get("handled"))
        self.assertNotEqual(result.get("tool_name"), "clarify")


# ---------------------------------------------------------------------------
# 5. ClarifyFlow — two-turn and three-turn conversations
# ---------------------------------------------------------------------------
class SocialParserClarifyFlowTests(unittest.TestCase):

    def _make_ctrl(self):
        ctrl = _make_controller()
        # Call sequence for full-flow tests (workflow_id now passed directly to debug handler):
        #   1. n8n_list_workflows  (existence check before create)
        #   2. n8n_create_workflow
        #   3. n8n_get_workflow    (debug handler loads full workflow JSON)
        #   4. n8n_get_executions  (iteration 1: no prior executions)
        #   5. n8n_run_workflow
        #   6. n8n_get_execution   (check status → success)
        ctrl._call_tool_json = MagicMock(side_effect=[
            {"data": []},                                              # 1. list_workflows → empty
            {"id": "wf-999", "name": "Test Social Parser"},           # 2. create
            {"id": "wf-999", "name": "Test Social Parser",            # 3. get_workflow (debug)
             "nodes": [], "connections": {}},
            {"data": []},                                              # 4. get_executions → empty
            {"execution_id": "exec-1", "webhook_triggered": True},    # 5. run_workflow
            {"id": "exec-1", "status": "success", "finished": True},  # 6. get_execution
        ])
        return ctrl

    def _patch_llm(self, ctrl, template_id="social_parser"):
        return patch.object(ctrl.intent_classifier, "_llm_classify_template", return_value={
            "is_template": True, "template_id": template_id,
        })

    # --- Two-turn: platform known, target missing ---

    def test_turn1_telegram_no_target_triggers_clarify(self):
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            result = ctrl.handle_request("хочу собирать посты из телеграм канала")
        self.assertEqual(result.get("tool_name"), "clarify")
        self.assertEqual(ctrl.state.session.pending_params.get("_missing_param"), "TARGET")

    def test_turn2_at_handle_completes_creation(self):
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            ctrl.handle_request("хочу собирать посты из телеграм канала")
        # Turn 2: provide target.
        result2 = ctrl.handle_request("@durov")
        self.assertTrue(result2.get("handled"))
        self.assertNotEqual(result2.get("tool_name"), "clarify")

    def test_pending_state_cleared_after_target_provided(self):
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            ctrl.handle_request("хочу собирать посты из телеграм канала")
        ctrl.handle_request("@durov")
        self.assertIsNone(ctrl.state.session.pending_intent)

    def test_turn2_platform_extracted_from_pending(self):
        """After providing the target, PLATFORM from turn 1 must be preserved."""
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            ctrl.handle_request("хочу собирать посты из телеграм канала")
        # Verify pending state has PLATFORM.
        self.assertEqual(ctrl.state.session.pending_params.get("PLATFORM"), "telegram")

    # --- Three-turn: both missing ---

    def test_three_turn_both_missing(self):
        """No platform, no target → 3 turns to complete."""
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            r1 = ctrl.handle_request("хочу собирать посты из соцсетей")
        # Turn 1: should ask for platform.
        self.assertEqual(r1.get("tool_name"), "clarify")
        self.assertEqual(ctrl.state.session.pending_params.get("_missing_param"), "PLATFORM")

        # Turn 2: provide platform.
        r2 = ctrl.handle_request("telegram")
        self.assertEqual(r2.get("tool_name"), "clarify")
        self.assertEqual(ctrl.state.session.pending_params.get("_missing_param"), "TARGET")

        # Turn 3: provide target.
        r3 = ctrl.handle_request("@mychannel")
        self.assertTrue(r3.get("handled"))
        self.assertNotEqual(r3.get("tool_name"), "clarify")

    def test_platform_normalized_from_russian(self):
        """Answering 'телеграм' to platform question → stored as 'telegram'."""
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            ctrl.handle_request("хочу собирать посты из соцсетей")
        ctrl.handle_request("телеграм")
        # After turn 2, pending should have PLATFORM=telegram.
        self.assertEqual(ctrl.state.session.pending_params.get("PLATFORM"), "telegram")

    def test_hashtag_target_extracted(self):
        """Target can be a hashtag like #news."""
        ctrl = self._make_ctrl()
        with self._patch_llm(ctrl):
            ctrl.handle_request("хочу собирать посты из телеграм канала")
        r2 = ctrl.handle_request("#technews")
        self.assertTrue(r2.get("handled"))


# ---------------------------------------------------------------------------
# 6. Integration tests — live n8n
# ---------------------------------------------------------------------------
class SocialParserIntegrationTests(unittest.TestCase):

    WORKFLOW_NAME_TELEGRAM = "Durov Social Parser"
    WORKFLOW_NAME_NOURL = "Social Parser"

    @classmethod
    def setUpClass(cls):
        if not _API_KEY or not _n8n_reachable():
            raise unittest.SkipTest(SKIP_REASON)
        _delete_workflow_by_name(cls.WORKFLOW_NAME_TELEGRAM)
        _delete_workflow_by_name(cls.WORKFLOW_NAME_NOURL)
        _delete_workflow_by_name("Telegram Social Parser")

    def tearDown(self):
        _delete_workflow_by_name(self.WORKFLOW_NAME_TELEGRAM)
        _delete_workflow_by_name(self.WORKFLOW_NAME_NOURL)
        _delete_workflow_by_name("Telegram Social Parser")

    def test_workflow_created_in_n8n(self):
        ctrl = _make_controller()
        result = ctrl.handle_request(
            "парсить telegram канал @durov"
        )
        self.assertTrue(result["handled"])
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        names = [w.get("name", "").strip().lower() for w in r.json().get("data", [])]
        found = any("social parser" in n or "durov" in n for n in names)
        self.assertTrue(found, f"No social parser workflow found. Workflows: {names}")

    def test_workflow_has_6_plus_nodes(self):
        ctrl = _make_controller()
        ctrl.handle_request("парсить telegram канал @durov")
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if "social parser" in w.get("name", "").lower() or "durov" in w.get("name", "").lower():
                detail = requests.get(
                    f"{N8N_BASE}/workflows/{w['id']}", headers=_HEADERS, timeout=5
                ).json()
                self.assertGreaterEqual(len(detail.get("nodes", [])), 6)
                return
        self.fail("Social parser workflow not found")

    def test_platform_and_target_injected(self):
        ctrl = _make_controller()
        ctrl.handle_request("парсить telegram канал @durov")
        time.sleep(0.5)
        r = requests.get(f"{N8N_BASE}/workflows", headers=_HEADERS, timeout=5)
        for w in r.json().get("data", []):
            if "social parser" in w.get("name", "").lower() or "durov" in w.get("name", "").lower():
                detail = requests.get(
                    f"{N8N_BASE}/workflows/{w['id']}", headers=_HEADERS, timeout=5
                ).json()
                raw = json.dumps(detail)
                self.assertIn("telegram", raw)
                self.assertIn("durov", raw)
                return
        self.fail("Social parser workflow not found")

    def test_message_without_target_returns_clarify(self):
        ctrl = _make_controller()
        result = ctrl.handle_request("хочу собирать посты из телеграм канала")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "clarify")

    def test_two_turn_creates_workflow(self):
        ctrl = _make_controller()
        r1 = ctrl.handle_request("хочу собирать посты из телеграм канала")
        self.assertEqual(r1.get("tool_name"), "clarify")
        # Provide the target.
        r2 = ctrl.handle_request("@durov")
        self.assertTrue(r2.get("handled"))
        self.assertNotEqual(r2.get("tool_name"), "clarify")


if __name__ == "__main__":
    unittest.main(verbosity=2)
