#!/usr/bin/env python3
"""
Tests for P1: duplicate cleanup confirmation thresholds.

Scenarios:
  1. Below threshold → no confirmation, direct cleanup
  2. Files threshold exceeded (≥20 files) → confirmation requested
  3. Size threshold exceeded (≥500 MB) → confirmation requested
  4. Two-turn: threshold exceeded → confirm 'да' → cleanup executes
  5. Two-turn: threshold exceeded → cancel 'нет' → cancelled
  6. Follow-up (DELETE_OLD_DUPLICATES_FOLLOWUP) also triggers threshold
"""

import os
import shutil
import tempfile
import unittest

import controller
import controller as ctrl_module


# ─────────────────────────────────────────────
# Mock builders
# ─────────────────────────────────────────────

def make_clean_mock(n_files=0, size_mb=0.0, clean_result="No duplicates found in /tmp"):
    """Returns a clean_duplicates mock that reports n_files and size_mb in dry_run."""
    def mock(args):
        if args.get("mode") == "dry_run":
            size_str = f"({size_mb:.1f} MB)" if size_mb >= 1 else "(0.5 KB)"
            return (
                f"Dry run: found {n_files} duplicate groups.\n"
                f"Would move {n_files} file(s) {size_str} to global trash (reversible)."
            )
        return clean_result
    return mock


def make_ctrl(memory_dir, n_files=0, size_mb=0.0, clean_result="No duplicates found in /tmp"):
    tools = {
        "find_duplicates": lambda a: "No duplicates found in /tmp/test",
        "clean_duplicates": make_clean_mock(n_files, size_mb, clean_result),
    }
    return controller.create_controller(memory_dir, tools)


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class ThresholdTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_below_threshold_no_confirmation(self):
        """5 files, 10 MB → below threshold → direct cleanup."""
        c = make_ctrl(self.memory_dir, n_files=5, size_mb=10.0,
                      clean_result="No duplicates found in E:/Agent/skills")
        r = c.handle_request("очисти дубликаты в E:/Agent/skills")
        self.assertTrue(r.get("handled"))
        # No confirmation question
        self.assertNotIn("Подтверди", r.get("response", ""))
        self.assertIsNone(c.state.session.pending_intent)

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_files_threshold_exceeded_asks_confirm(self):
        """25 files → exceeds DUP_CONFIRM_FILES (20) → ask confirmation."""
        c = make_ctrl(self.memory_dir, n_files=25, size_mb=10.0)
        r = c.handle_request("очисти дубликаты в E:/Agent/skills")
        self.assertTrue(r.get("handled"))
        self.assertIn("Будет перемещено", r.get("response", ""))
        self.assertEqual(c.state.session.pending_intent, "CLEAN_DUPLICATES_CONFIRM")

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_size_threshold_exceeded_asks_confirm(self):
        """10 files, 600 MB → exceeds DUP_CONFIRM_MB (500) → ask confirmation."""
        c = make_ctrl(self.memory_dir, n_files=10, size_mb=600.0)
        r = c.handle_request("очисти дубликаты в E:/Agent/skills")
        self.assertTrue(r.get("handled"))
        self.assertIn("Будет перемещено", r.get("response", ""))
        self.assertIn("600.0 MB", r.get("response", ""))
        self.assertEqual(c.state.session.pending_intent, "CLEAN_DUPLICATES_CONFIRM")

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_confirm_yes_runs_cleanup(self):
        """Threshold exceeded → 'да' → real cleanup runs."""
        clean_result = "Cleaned 25 duplicate file(s); kept 25 original(s).\nFiles moved to global trash (reversible)."
        c = make_ctrl(self.memory_dir, n_files=25, size_mb=10.0, clean_result=clean_result)
        c.handle_request("очисти дубликаты в E:/Agent/skills")  # -> pending confirm
        r2 = c.handle_request("да")
        self.assertTrue(r2.get("handled"))
        self.assertIn("Cleaned", r2.get("response", ""))
        self.assertIsNone(c.state.session.pending_intent)

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_confirm_no_cancels(self):
        """Threshold exceeded → 'нет' → cancelled."""
        c = make_ctrl(self.memory_dir, n_files=25, size_mb=10.0)
        c.handle_request("очисти дубликаты в E:/Agent/skills")
        r2 = c.handle_request("нет")
        self.assertTrue(r2.get("handled"))
        self.assertIn("отмен", r2.get("response", "").lower())
        self.assertIsNone(c.state.session.pending_intent)

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_followup_also_triggers_threshold(self):
        """find → follow-up clean with 25 files → also triggers threshold."""
        c = make_ctrl(self.memory_dir, n_files=25, size_mb=10.0)
        c.handle_request("найди дубликаты в E:/Agent/skills")  # sets pending
        r = c.handle_request("удали старые")
        self.assertTrue(r.get("handled"))
        # Should show threshold confirmation (25 files > 20 threshold)
        self.assertIn("Будет перемещено", r.get("response", ""))
        self.assertEqual(c.state.session.pending_intent, "CLEAN_DUPLICATES_CONFIRM")


if __name__ == "__main__":
    unittest.main()
