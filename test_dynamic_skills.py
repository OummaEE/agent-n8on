"""
test_dynamic_skills.py

Tests for Improvement 3: Dynamic Skills
  - _find_relevant_skill() keyword-to-file mapping
  - Skill content injected into SLOW path result
  - learned_lessons.md loaded when non-empty
  - Graceful fallback when files are missing
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from brain.brain_layer import BrainLayer
from brain.executor import StepResult
from brain.verifier import VerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_brain(skills_dir: Path | None = None) -> BrainLayer:
    tmpdir = Path(tempfile.mkdtemp())
    ctrl = MagicMock()
    ctrl.handle_request.return_value = {
        "handled": True, "response": "ok", "tool_name": "x",
        "tool_result": None, "steps": [],
    }
    ctrl._call_tool_json = MagicMock(return_value={"execution_id": "eid"})
    brain = BrainLayer(
        ctrl,
        rules_file=tmpdir / "rules.md",
        skills_dir=skills_dir or tmpdir,
    )
    brain.executor = MagicMock()
    brain.executor.execute_plan.return_value = [
        StepResult(step_index=0, intent="PASSTHROUGH",
                   success=True, response="done"),
    ]
    brain.verifier = MagicMock()
    brain.verifier.verify.return_value = VerificationResult(
        ok=True, summary="SUCCESS: 1/1 steps OK"
    )
    return brain


def _skills_dir_with_files() -> Path:
    """Create a temp dir with all three skill files."""
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "debug_n8n_workflow.md").write_text(
        "# Debug Instructions\nStep 1: get execution_id\n", encoding="utf-8"
    )
    (tmpdir / "create_complex_workflow.md").write_text(
        "# Complex Workflow\nMax 10 nodes per workflow.\n", encoding="utf-8"
    )
    (tmpdir / "handle_api_errors.md").write_text(
        "# API Errors\nHTTP 429: rate limit\n", encoding="utf-8"
    )
    (tmpdir / "learned_lessons.md").write_text(
        "", encoding="utf-8"
    )
    return tmpdir


# ---------------------------------------------------------------------------
# _find_relevant_skill — keyword matching
# ---------------------------------------------------------------------------

class FindRelevantSkillTests(unittest.TestCase):

    def setUp(self):
        self.skills_dir = _skills_dir_with_files()
        self.brain = _make_brain(self.skills_dir)

    # Debug keywords
    def test_debug_keyword_en(self):
        result = self.brain._find_relevant_skill("debug my n8n workflow")
        self.assertIsNotNone(result)
        self.assertIn("Debug", result)

    def test_debug_keyword_ru(self):
        result = self.brain._find_relevant_skill("исправь ошибку в workflow")
        self.assertIsNotNone(result)
        self.assertIn("Debug", result)

    def test_execution_keyword(self):
        result = self.brain._find_relevant_skill("check execution 123 why did it fail")
        self.assertIsNotNone(result)
        self.assertIn("Debug", result)

    def test_error_keyword(self):
        result = self.brain._find_relevant_skill("workflow упал с ошибкой")
        self.assertIsNotNone(result)
        self.assertIn("Debug", result)

    # Complex workflow keywords
    def test_complex_keyword(self):
        result = self.brain._find_relevant_skill("create complex workflow with many steps")
        self.assertIsNotNone(result)
        self.assertIn("Complex", result)

    def test_sub_workflow_keyword(self):
        result = self.brain._find_relevant_skill("разбить на sub-workflow части")
        self.assertIsNotNone(result)
        self.assertIn("Complex", result)

    # API error keywords
    def test_http_429_keyword(self):
        result = self.brain._find_relevant_skill("getting 429 rate limit errors")
        self.assertIsNotNone(result)
        self.assertIn("API Errors", result)

    def test_http_401_keyword(self):
        result = self.brain._find_relevant_skill("401 unauthorized error")
        self.assertIsNotNone(result)
        self.assertIn("API Errors", result)

    def test_rate_limit_keyword(self):
        result = self.brain._find_relevant_skill("API rate limit exceeded")
        self.assertIsNotNone(result)
        self.assertIn("API Errors", result)

    # No match
    def test_no_match_returns_none(self):
        result = self.brain._find_relevant_skill("покажи список файлов в папке")
        self.assertIsNone(result)

    def test_empty_message_returns_none(self):
        result = self.brain._find_relevant_skill("")
        self.assertIsNone(result)

    def test_skill_file_missing_returns_none(self):
        """Keyword matches but file deleted → returns None gracefully."""
        (self.skills_dir / "debug_n8n_workflow.md").unlink()
        result = self.brain._find_relevant_skill("debug workflow error")
        self.assertIsNone(result)

    def test_returned_content_is_string(self):
        result = self.brain._find_relevant_skill("debug workflow error")
        self.assertIsInstance(result, str)

    def test_no_skills_dir_returns_none(self):
        """Missing skills dir → no crash, returns None."""
        import shutil
        empty_dir = Path(tempfile.mkdtemp())
        brain = _make_brain(empty_dir)
        shutil.rmtree(str(empty_dir))
        result = brain._find_relevant_skill("debug workflow")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _get_learned_lessons
# ---------------------------------------------------------------------------

class GetLearnedLessonsTests(unittest.TestCase):

    def test_empty_file_returns_empty_string(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._get_learned_lessons()
        self.assertEqual(result, "")

    def test_file_with_content_returned(self):
        skills_dir = _skills_dir_with_files()
        (skills_dir / "learned_lessons.md").write_text(
            "[2026-03-03] [n8n] → [err] → [fix] → [rule]\n", encoding="utf-8"
        )
        brain = _make_brain(skills_dir)
        result = brain._get_learned_lessons()
        self.assertIn("rule", result)

    def test_missing_file_returns_empty_string(self):
        tmpdir = Path(tempfile.mkdtemp())
        # No learned_lessons.md in tmpdir
        brain = _make_brain(tmpdir)
        result = brain._get_learned_lessons()
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Slow path integration — skill_context in result
# ---------------------------------------------------------------------------

class SlowPathSkillContextTests(unittest.TestCase):

    def test_skill_context_in_result_when_debug_message(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._slow_path("debug my n8n workflow and fix the error")
        self.assertIn("skill_context", result)
        self.assertIn("Debug", result["skill_context"])

    def test_no_skill_context_when_no_match(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._slow_path("покажи список файлов в папке D:/docs и удали дубликаты")
        self.assertNotIn("skill_context", result)

    def test_learned_lessons_in_result_when_non_empty(self):
        skills_dir = _skills_dir_with_files()
        (skills_dir / "learned_lessons.md").write_text(
            "[2026-03-03] [n8n] → [err] → [fix] → [Always check rule]\n",
            encoding="utf-8",
        )
        brain = _make_brain(skills_dir)
        result = brain._slow_path("create n8n workflow and then run it")
        self.assertIn("learned_lessons", result)
        self.assertIn("Always check rule", result["learned_lessons"])

    def test_no_learned_lessons_key_when_empty_file(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._slow_path("create n8n workflow and then run it")
        self.assertNotIn("learned_lessons", result)

    def test_skill_context_is_string(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._slow_path("debug n8n workflow")
        if "skill_context" in result:
            self.assertIsInstance(result["skill_context"], str)

    def test_api_error_skill_injected_for_http_errors(self):
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain._slow_path(
            "workflow падает с ошибкой 429 rate limit и нужно добавить retry"
        )
        self.assertIn("skill_context", result)
        self.assertIn("API Errors", result["skill_context"])

    def test_handle_slow_message_result_has_skill_via_full_pipeline(self):
        """Full handle() pipeline for SLOW message includes skill_context."""
        skills_dir = _skills_dir_with_files()
        brain = _make_brain(skills_dir)
        result = brain.handle(
            "debug my n8n workflow и запусти исправленный"
        )
        # Should be SLOW path result with skill_context
        if result["path"] == "SLOW" and result["tool_name"] == "brain_slow_path":
            self.assertIn("skill_context", result)


if __name__ == "__main__":
    unittest.main()
