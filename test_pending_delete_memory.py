#!/usr/bin/env python3
import os
import shutil
import tempfile
import time
import unittest

from controller import create_controller


class DeleteToolSpy:
    last_delete_args = None

    @staticmethod
    def delete_files(args):
        DeleteToolSpy.last_delete_args = dict(args)
        paths = args.get("paths", [])
        permanent = bool(args.get("permanent"))
        confirm = bool(args.get("confirm"))

        if permanent and not confirm:
            return "Blocked: permanent delete requires permanent=true and confirm=true."

        moved = []
        for path in paths:
            if not os.path.exists(path):
                continue
            if permanent:
                os.remove(path)
                moved.append("(permanent)")
            else:
                trash_path = f"{path}.trash"
                os.makedirs(os.path.dirname(trash_path), exist_ok=True)
                shutil.move(path, trash_path)
                moved.append(trash_path)

        if moved:
            return f"Successfully moved {len(moved)} item(s)"
        return "Nothing to delete."


class PendingDeleteMemoryTests(unittest.TestCase):
    def setUp(self):
        self.memory_dir = tempfile.mkdtemp()
        self.controller = create_controller(
            self.memory_dir,
            {"delete_files": DeleteToolSpy.delete_files},
        )

    def tearDown(self):
        shutil.rmtree(self.memory_dir, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_blocked_permanent_delete_then_followup_moves_same_file_to_trash(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            file_path = os.path.join(tmpdir, "pending_delete_test.txt").replace("\\", "/")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("data")

            blocked = self.controller.handle_request(f"delete permanently {file_path}")
            self.assertTrue(blocked.get("handled"))
            self.assertIn("Blocked: permanent delete requires", blocked.get("response", ""))

            pending = self.controller.state.get_pending_delete()
            self.assertIsNotNone(pending)
            self.assertEqual(pending["full_path"], file_path)

            followup = self.controller.handle_request("в корзину")
            self.assertTrue(followup.get("handled"))
            self.assertEqual(followup.get("tool_name"), "delete_files")

            self.assertEqual(DeleteToolSpy.last_delete_args["paths"], [file_path])
            self.assertEqual(DeleteToolSpy.last_delete_args["allowed_folder"], os.path.dirname(file_path))
            self.assertFalse(os.path.exists(file_path))
            self.assertTrue(os.path.exists(f"{file_path}.trash"))
            self.assertIsNone(self.controller.state.get_pending_delete())

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_pending_delete_timeout_clears_memory(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            file_path = os.path.join(tmpdir, "timeout_delete_test.txt").replace("\\", "/")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("data")

            self.controller.state.set_pending_delete(
                full_path=file_path,
                folder=os.path.dirname(file_path),
                requested_mode="permanent",
            )
            self.controller.state.session.pending_delete["timestamp"] = time.time() - 301
            self.controller.state.save()

            result = self.controller.handle_request("в корзину")
            self.assertFalse(result.get("handled"))
            self.assertIsNone(self.controller.state.get_pending_delete())

    @unittest.skipUnless(os.name == "nt", "Windows path extraction required")
    def test_new_explicit_delete_overwrites_pending_context(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            file1 = os.path.join(tmpdir, "first.txt").replace("\\", "/")
            file2 = os.path.join(tmpdir, "second.txt").replace("\\", "/")
            for path in [file1, file2]:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("data")

            self.controller.handle_request(f"delete permanently {file1}")
            self.controller.handle_request(f"delete permanently {file2}")

            followup = self.controller.handle_request("move to trash")
            self.assertTrue(followup.get("handled"))
            self.assertEqual(DeleteToolSpy.last_delete_args["paths"], [file2])
            self.assertTrue(os.path.exists(file1), "Old pending file should remain untouched")
            self.assertFalse(os.path.exists(file2), "Latest pending file should be moved")


if __name__ == "__main__":
    unittest.main()
