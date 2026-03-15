"""
test_learning_loop.py

Tests for Improvement 1: Active Learning Loop
  - _load_learned_rules() reads rules from learned_rules.md
  - _save_learned_rule() appends new rule to file and updates in-memory list
  - Slow path result includes learned_rules when rules exist
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from brain.brain_layer import BrainLayer
from brain.executor import StepResult
from brain.verifier import VerificationResult


def _make_brain(rules_file: Path, skills_dir: Path | None = None) -> BrainLayer:
    """Create a BrainLayer with a temp rules file and mocked controller."""
    ctrl = MagicMock()
    ctrl.handle_request.return_value = {
        "handled": True, "response": "ok", "tool_name": "x",
        "tool_result": None, "steps": [],
    }
    ctrl._call_tool_json = MagicMock(return_value={"execution_id": "eid"})
    brain = BrainLayer(
        ctrl,
        rules_file=rules_file,
        skills_dir=skills_dir or Path(tempfile.mkdtemp()),
    )
    return brain


class LoadLearnedRulesTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.rules_file = self.tmpdir / "learned_rules.md"

    def test_missing_file_returns_empty_list(self):
        """No file → no rules, no crash."""
        brain = _make_brain(self.rules_file)
        self.assertEqual(brain._learned_rules, [])

    def test_empty_file_returns_empty_list(self):
        self.rules_file.write_text("", encoding="utf-8")
        brain = _make_brain(self.rules_file)
        self.assertEqual(brain._learned_rules, [])

    def test_header_lines_not_loaded(self):
        """Lines not starting with '[' are ignored (comments/headers)."""
        self.rules_file.write_text(
            "# Learned Rules\n\nFormat: ...\n", encoding="utf-8"
        )
        brain = _make_brain(self.rules_file)
        self.assertEqual(brain._learned_rules, [])

    def test_single_rule_loaded(self):
        self.rules_file.write_text(
            "[2026-03-03] [n8n] → [wrong url] → [fixed] → [Validate URLs]\n",
            encoding="utf-8",
        )
        brain = _make_brain(self.rules_file)
        self.assertEqual(len(brain._learned_rules), 1)
        self.assertIn("Validate URLs", brain._learned_rules[0])

    def test_multiple_rules_all_loaded(self):
        self.rules_file.write_text(
            "[2026-01-01] [ctx1] → [e1] → [f1] → [r1]\n"
            "[2026-01-02] [ctx2] → [e2] → [f2] → [r2]\n"
            "[2026-01-03] [ctx3] → [e3] → [f3] → [r3]\n",
            encoding="utf-8",
        )
        brain = _make_brain(self.rules_file)
        self.assertEqual(len(brain._learned_rules), 3)


class SaveLearnedRuleTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.rules_file = self.tmpdir / "learned_rules.md"

    def test_save_creates_file_if_missing(self):
        brain = _make_brain(self.rules_file)
        self.assertFalse(self.rules_file.exists())
        brain._save_learned_rule("ctx", "err", "fix", "rule")
        self.assertTrue(self.rules_file.exists())

    def test_saved_format_contains_all_fields(self):
        brain = _make_brain(self.rules_file)
        brain._save_learned_rule("myctx", "myerr", "myfix", "myrule")
        content = self.rules_file.read_text(encoding="utf-8")
        self.assertIn("myctx", content)
        self.assertIn("myerr", content)
        self.assertIn("myfix", content)
        self.assertIn("myrule", content)

    def test_saved_format_has_date(self):
        from datetime import date
        brain = _make_brain(self.rules_file)
        brain._save_learned_rule("c", "e", "f", "r")
        content = self.rules_file.read_text(encoding="utf-8")
        self.assertIn(str(date.today()), content)

    def test_save_appends_to_existing_file(self):
        self.rules_file.write_text(
            "[2026-01-01] [old] → [x] → [y] → [z]\n", encoding="utf-8"
        )
        brain = _make_brain(self.rules_file)
        brain._save_learned_rule("new_ctx", "e", "f", "r")
        content = self.rules_file.read_text(encoding="utf-8")
        self.assertIn("old", content)
        self.assertIn("new_ctx", content)

    def test_save_updates_in_memory_list(self):
        brain = _make_brain(self.rules_file)
        self.assertEqual(len(brain._learned_rules), 0)
        brain._save_learned_rule("c", "e", "f", "r")
        self.assertEqual(len(brain._learned_rules), 1)

    def test_multiple_saves_accumulate(self):
        brain = _make_brain(self.rules_file)
        brain._save_learned_rule("c1", "e1", "f1", "r1")
        brain._save_learned_rule("c2", "e2", "f2", "r2")
        self.assertEqual(len(brain._learned_rules), 2)

    def test_saved_rule_loadable_on_next_init(self):
        """Rule saved to file is present when a new BrainLayer is created."""
        brain = _make_brain(self.rules_file)
        brain._save_learned_rule("ctx", "err", "fix", "rule text here")
        # New instance reads same file
        brain2 = _make_brain(self.rules_file)
        self.assertTrue(
            any("rule text here" in r for r in brain2._learned_rules)
        )


class LearnedRulesInSlowPathTests(unittest.TestCase):
    """Verify that slow path result exposes learned_rules when rules exist."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.rules_file = self.tmpdir / "learned_rules.md"

    def _make_brain_with_mocked_executor(self, rules_content: str) -> BrainLayer:
        self.rules_file.write_text(rules_content, encoding="utf-8")
        brain = _make_brain(self.rules_file)
        # Mock executor + verifier so _slow_path doesn't call real controller
        brain.executor = MagicMock()
        brain.executor.execute_plan.return_value = [
            StepResult(step_index=0, intent="PASSTHROUGH", success=True,
                       response="done"),
        ]
        brain.verifier = MagicMock()
        brain.verifier.verify.return_value = VerificationResult(
            ok=True, summary="SUCCESS: 1/1 steps OK"
        )
        return brain

    def test_rules_in_result_when_file_has_entries(self):
        brain = self._make_brain_with_mocked_executor(
            "[2026-03-03] [n8n] → [err] → [fix] → [rule A]\n"
        )
        result = brain._slow_path("create n8n workflow and then run it")
        self.assertIn("learned_rules", result)
        self.assertEqual(len(result["learned_rules"]), 1)
        self.assertIn("rule A", result["learned_rules"][0])

    def test_no_rules_key_when_file_empty(self):
        brain = self._make_brain_with_mocked_executor("")
        result = brain._slow_path("create n8n workflow and then run it")
        self.assertNotIn("learned_rules", result)


if __name__ == "__main__":
    unittest.main()
