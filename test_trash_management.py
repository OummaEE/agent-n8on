#!/usr/bin/env python3
"""
Tests for P1 trash management: restore, list, purge with confirmation.

Covers:
  1. tool_restore_from_trash: restores file to original path
  2. tool_list_trash: lists trash contents, handles empty
  3. tool_purge_trash: blocked without confirm; deletes with confirm
  4. _original_path_from_trash: path reconstruction
  5. Controller intents: LIST_TRASH / PURGE_TRASH / RESTORE_FROM_TRASH
  6. PURGE_TRASH two-turn confirmation flow
  7. PURGE_TRASH cancellation
"""

import os
import shutil
import tempfile
import unittest

import agent_v3
from agent_v3 import (
    tool_restore_from_trash,
    tool_list_trash,
    tool_purge_trash,
    _original_path_from_trash,
    get_global_trash_path,
    _move_to_trash,
)
from controller import create_controller


# ─────────────────────────────────────────────
# Unit tests for agent_v3 trash functions
# ─────────────────────────────────────────────

class OriginalPathFromTrashTests(unittest.TestCase):
    def test_windows_path_reconstruction(self):
        trash_path = r"E:\_TRASH\Agent\file.txt"
        result = _original_path_from_trash(trash_path)
        self.assertIsNotNone(result)
        self.assertIn("file.txt", result)
        self.assertNotIn("_TRASH", result)

    def test_returns_none_for_non_trash_path(self):
        result = _original_path_from_trash(r"E:\Agent\file.txt")
        self.assertIsNone(result)

    def test_returns_none_for_empty_path(self):
        result = _original_path_from_trash("")
        self.assertIsNone(result)


class RestoreFromTrashTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_restore_moves_file_back(self):
        # Create a file and move it to trash
        orig_file = os.path.join(self.base_dir, "restore_me.txt")
        with open(orig_file, "w", encoding="utf-8") as f:
            f.write("restore test")

        trash_path = _move_to_trash(orig_file)
        self.assertTrue(os.path.exists(trash_path))
        self.assertFalse(os.path.exists(orig_file))

        result = tool_restore_from_trash(trash_path)
        self.assertIn("Restored", result)
        # After restore, trash item should be gone
        self.assertFalse(os.path.exists(trash_path))

    def test_restore_nonexistent_returns_error(self):
        result = tool_restore_from_trash("/nonexistent/_TRASH/file.txt")
        self.assertIn("Not found", result)

    def test_restore_non_trash_path_returns_error(self):
        f = os.path.join(self.base_dir, "normal.txt")
        with open(f, "w") as fp:
            fp.write("x")
        result = tool_restore_from_trash(f)
        self.assertIn("Cannot determine original path", result)


class ListTrashTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_empty_trash_returns_empty_message(self):
        # Use a temp drive-like folder that has no _TRASH
        result = tool_list_trash(drive=self.base_dir)
        self.assertIn("empty", result.lower())

    def test_lists_files_after_trash(self):
        orig_file = os.path.join(self.base_dir, "listed.txt")
        with open(orig_file, "w", encoding="utf-8") as f:
            f.write("x" * 500)
        _move_to_trash(orig_file)
        # list_trash scans all drives, so this will scan real system —
        # just check it returns something string-like
        result = tool_list_trash()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


class PurgeTrashTests(unittest.TestCase):
    def test_requires_confirm(self):
        result = tool_purge_trash(confirm=False)
        self.assertIn("confirm=True", result)
        self.assertNotIn("Purged", result)

    def test_purge_with_confirm_empties_trash(self):
        base = tempfile.mkdtemp()
        try:
            orig_file = os.path.join(base, "purge_me.txt")
            with open(orig_file, "w", encoding="utf-8") as f:
                f.write("data")
            trash_path = _move_to_trash(orig_file)
            self.assertTrue(os.path.exists(trash_path))

            # Purge the drive this file is on
            drive_letter = os.path.splitdrive(trash_path)[0]  # e.g. 'C:'
            drive = drive_letter if drive_letter else None
            result = tool_purge_trash(drive=drive, confirm=True)
            self.assertIn("Purged", result)
            self.assertFalse(os.path.exists(trash_path))
        finally:
            shutil.rmtree(base, ignore_errors=True)


# ─────────────────────────────────────────────
# Controller intent tests
# ─────────────────────────────────────────────

def make_ctrl(memory_dir):
    """Controller with stub trash tools."""
    return create_controller(memory_dir, {
        "list_trash": lambda args: "Trash is empty.",
        "restore_from_trash": lambda args: f"Restored: {args.get('path')}",
        "purge_trash": lambda args: (
            "Purged 0 item(s) from _TRASH permanently." if args.get("confirm")
            else "Purge requires confirm=True."
        ),
    })


class TrashIntentTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()
        self.ctrl = make_ctrl(self.memory_dir)
        self.ic = self.ctrl.intent_classifier

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    def test_list_trash_russian(self):
        result = self.ic.classify("покажи корзину")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "LIST_TRASH")

    def test_list_trash_english(self):
        result = self.ic.classify("list trash")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "LIST_TRASH")

    def test_purge_trash_russian(self):
        result = self.ic.classify("очисти корзину")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "PURGE_TRASH")

    def test_purge_trash_without_confirm_flag(self):
        result = self.ic.classify("очисти корзину")
        self.assertEqual(result[1].get("confirm"), False)

    @unittest.skipUnless(os.name == "nt", "Windows path required")
    def test_restore_from_trash_detected(self):
        result = self.ic.classify(r"восстанови E:\_TRASH\Agent\file.txt из корзины")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "RESTORE_FROM_TRASH")


class PurgeTwoTurnFlowTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()
        self.ctrl = make_ctrl(self.memory_dir)

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    def test_purge_asks_confirmation(self):
        r = self.ctrl.handle_request("очисти корзину")
        self.assertTrue(r.get("handled"))
        self.assertIn("уверены", r.get("response", "").lower())
        self.assertEqual(self.ctrl.state.session.pending_intent, "PURGE_TRASH_CONFIRM")

    def test_purge_confirm_yes_executes(self):
        self.ctrl.handle_request("очисти корзину")
        r = self.ctrl.handle_request("да")
        self.assertTrue(r.get("handled"))
        self.assertIn("Purged", r.get("response", ""))
        self.assertIsNone(self.ctrl.state.session.pending_intent)

    def test_purge_confirm_no_cancels(self):
        self.ctrl.handle_request("очисти корзину")
        r = self.ctrl.handle_request("нет")
        self.assertTrue(r.get("handled"))
        self.assertIn("отмен", r.get("response", "").lower())
        self.assertIsNone(self.ctrl.state.session.pending_intent)

    def test_list_trash_is_handled(self):
        r = self.ctrl.handle_request("покажи корзину")
        self.assertTrue(r.get("handled"))
        self.assertIn("empty", r.get("response", "").lower())


if __name__ == "__main__":
    unittest.main()
