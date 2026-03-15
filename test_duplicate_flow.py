#!/usr/bin/env python3
"""
Tests for P0 duplicate-find → follow-up-clean flow.

Scenarios:
  1. Intent classification: "найди дубликаты" → FIND_DUPLICATES_ONLY
  2. Intent classification: "очисти дубликаты" → CLEAN_DUPLICATES_KEEP_NEWEST
  3. Two-turn: find → "удали старые" → DELETE_OLD_DUPLICATES_FOLLOWUP (keep=newest)
  4. Two-turn: find → "удали новые" → DELETE_OLD_DUPLICATES_FOLLOWUP (keep=oldest)
  5. Follow-up without prior scan context → not handled
  6. Validate cleanup handles "No duplicates found" (no error)
  7. Validate cleanup handles "Cleaned N files" → success
  8. Validate cleanup handles unexpected string → failure
"""

import os
import shutil
import tempfile
import unittest

from controller import create_controller, ResultValidator


# ─────────────────────────────────────────────
# Mock tools
# ─────────────────────────────────────────────

class FindDuplicatesMock:
    """Returns configurable result for find_duplicates."""
    def __init__(self, return_value="No duplicates found in /tmp/test"):
        self.return_value = return_value
        self.last_args = None

    def __call__(self, args):
        self.last_args = dict(args)
        return self.return_value


class CleanDuplicatesMock:
    """Returns configurable result for clean_duplicates."""
    def __init__(self, return_value="No duplicates found in /tmp/test"):
        self.return_value = return_value
        self.last_args = None

    def __call__(self, args):
        self.last_args = dict(args)
        return self.return_value


def make_controller(memory_dir, find_result=None, clean_result=None):
    find_mock = FindDuplicatesMock(
        return_value=find_result or "No duplicates found in /tmp/test"
    )
    clean_mock = CleanDuplicatesMock(
        return_value=clean_result or "No duplicates found in /tmp/test"
    )
    ctrl = create_controller(memory_dir, {
        "find_duplicates": find_mock,
        "clean_duplicates": clean_mock,
    })
    ctrl._find_mock = find_mock
    ctrl._clean_mock = clean_mock
    return ctrl


# ─────────────────────────────────────────────
# Intent classification tests
# ─────────────────────────────────────────────

class IntentClassificationTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()
        self.ctrl = make_controller(self.memory_dir)
        self.ic = self.ctrl.intent_classifier

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_duplicates_russian(self):
        result = self.ic.classify("найди дубликаты в E:/Agent/skills")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "FIND_DUPLICATES_ONLY")
        self.assertEqual(result[1]["path"], "E:/Agent/skills")

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_duplicates_show(self):
        result = self.ic.classify("покажи дубли в E:/Agent/skills")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "FIND_DUPLICATES_ONLY")

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_clean_duplicates_russian(self):
        result = self.ic.classify("очисти дубликаты в E:/Agent/skills")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "CLEAN_DUPLICATES_KEEP_NEWEST")

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_clean_duplicates_delete_verb(self):
        result = self.ic.classify("удали одинаковые файлы в E:/Agent/skills")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "CLEAN_DUPLICATES_KEEP_NEWEST")

    def test_no_match_returns_none(self):
        result = self.ic.classify("привет, как дела?")
        self.assertIsNone(result)


# ─────────────────────────────────────────────
# Follow-up: find → clean flow
# ─────────────────────────────────────────────

class DuplicateFollowUpFlowTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_then_delete_old_uses_keep_newest(self):
        ctrl = make_controller(self.memory_dir)
        r1 = ctrl.handle_request("найди дубликаты в E:/Agent/skills")
        self.assertTrue(r1.get("handled"), "R1 should be handled")

        r2 = ctrl.handle_request("удали старые")
        self.assertTrue(r2.get("handled"), "R2 should be handled")
        # 'удали старые' = delete old copies = keep newest
        self.assertEqual(ctrl._clean_mock.last_args.get("keep"), "newest")
        # pending intent cleared after cleanup
        self.assertIsNone(ctrl.state.session.pending_intent)

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_then_delete_new_uses_keep_oldest(self):
        ctrl = make_controller(self.memory_dir)
        ctrl.handle_request("найди дубликаты в E:/Agent/skills")

        r2 = ctrl.handle_request("удали новые")
        self.assertTrue(r2.get("handled"))
        # 'удали новые' = delete new copies = keep oldest
        self.assertEqual(ctrl._clean_mock.last_args.get("keep"), "oldest")

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_then_clean_uses_same_path(self):
        ctrl = make_controller(self.memory_dir)
        ctrl.handle_request("найди дубликаты в E:/Agent/skills")

        ctrl.handle_request("очисти")
        self.assertIsNotNone(ctrl._clean_mock.last_args)
        self.assertIn("E:/Agent/skills", ctrl._clean_mock.last_args.get("path", ""))

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_find_sets_pending_intent(self):
        ctrl = make_controller(self.memory_dir)
        ctrl.handle_request("найди дубликаты в E:/Agent/skills")
        self.assertEqual(ctrl.state.session.pending_intent, "CLEAN_DUPLICATES_AVAILABLE")
        self.assertEqual(ctrl.state.session.last_duplicates_path, "E:/Agent/skills")

    def test_no_prior_scan_followup_not_routed(self):
        """Follow-up without prior scan should not trigger DELETE_OLD_DUPLICATES_FOLLOWUP."""
        ctrl = make_controller(self.memory_dir)
        # No find_duplicates call first
        result = ctrl.intent_classifier.classify("удали старые")
        # Should not match DELETE_OLD_DUPLICATES_FOLLOWUP because pending_intent is not set
        if result is not None:
            self.assertNotEqual(result[0], "DELETE_OLD_DUPLICATES_FOLLOWUP")

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_second_find_resets_context_path(self):
        """A second find_duplicates call should update the path for follow-up."""
        ctrl = make_controller(self.memory_dir)
        ctrl.handle_request("найди дубликаты в E:/Agent/skills")
        ctrl.handle_request("найди дубликаты в E:/Agent/docs")
        self.assertEqual(ctrl.state.session.last_duplicates_path, "E:/Agent/docs")


# ─────────────────────────────────────────────
# ResultValidator tests
# ─────────────────────────────────────────────

class ValidateCleanupTests(unittest.TestCase):
    def test_no_duplicates_found_is_success(self):
        ok, err = ResultValidator.validate_cleanup("No duplicates found in /tmp/test")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_cleaned_n_files_is_success(self):
        ok, err = ResultValidator.validate_cleanup(
            "Cleaned 5 files. Moved to _trash."
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_moved_to_trash_is_success(self):
        ok, err = ResultValidator.validate_cleanup(
            "3 file(s) moved to _trash (reversible)"
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_error_string_is_failure(self):
        ok, err = ResultValidator.validate_cleanup("Error: permission denied")
        self.assertFalse(ok)

    def test_unexpected_format_is_failure(self):
        ok, err = ResultValidator.validate_cleanup("some unknown output")
        self.assertFalse(ok)
        self.assertIsNotNone(err)


class ValidateScanTests(unittest.TestCase):
    def test_no_duplicates_found_is_success(self):
        ok, err = ResultValidator.validate_duplicates_scan(
            "No duplicates found in /tmp/test"
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_found_groups_is_success(self):
        ok, err = ResultValidator.validate_duplicates_scan(
            "Found 3 groups of duplicates (8 files total)"
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_error_is_failure(self):
        ok, err = ResultValidator.validate_duplicates_scan("Error: path not found")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
