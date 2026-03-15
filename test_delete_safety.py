#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
import uuid

import agent_v3


class DeleteSafetyTests(unittest.TestCase):
    def test_delete_inside_allowed_folder_succeeds_and_moves_to_global_trash(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            src = os.path.join(tmpdir, f"inside_allowed_{uuid.uuid4().hex}.txt")
            expected_trash = agent_v3.get_global_trash_path(src)
            with open(src, "w", encoding="utf-8") as f:
                f.write("ok")

            result = agent_v3.tool_delete_files([src], allowed_folder=tmpdir)
            self.assertIn("Moved to global trash:", result)
            self.assertNotIn("Blocked", result)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(expected_trash))
            self._cleanup_trash_artifact(expected_trash)

    def test_delete_file_from_nested_folder_preserves_global_trash_path(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            nested = os.path.join(tmpdir, "nested", "level")
            os.makedirs(nested, exist_ok=True)
            src = os.path.join(nested, f"sample_{uuid.uuid4().hex}.txt")
            expected_trash = agent_v3.get_global_trash_path(src)
            with open(src, "w", encoding="utf-8") as f:
                f.write("hello")

            result = agent_v3.tool_delete_files([src], allowed_folder=tmpdir)

            self.assertIn("Moved to global trash:", result)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(expected_trash))
            self.assertTrue(expected_trash.endswith(os.path.join("nested", "level", os.path.basename(src))))
            self._cleanup_trash_artifact(expected_trash)

    def test_delete_is_reversible_file_exists_in_trash(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            first = os.path.join(tmpdir, f"recover_me_{uuid.uuid4().hex}.txt")
            with open(first, "w", encoding="utf-8") as f:
                f.write("reversible")
            first_expected = agent_v3.get_global_trash_path(first)
            agent_v3.tool_delete_files([first], allowed_folder=tmpdir)

            with open(first, "w", encoding="utf-8") as f:
                f.write("reversible-again")
            result = agent_v3.tool_delete_files([first], allowed_folder=tmpdir)
            self.assertIn("Moved to global trash:", result)

            drive_root = agent_v3.get_drive_root(first)
            relative_dir = os.path.dirname(agent_v3.get_relative_from_drive(first))
            trash_dir = os.path.join(drive_root, "_TRASH", relative_dir)
            moved = [name for name in os.listdir(trash_dir) if name.startswith(os.path.splitext(os.path.basename(first))[0])]
            self.assertGreaterEqual(len(moved), 2, "Expected collision-safe unique names in global trash")
            self.assertTrue(os.path.exists(first_expected))
            self._cleanup_trash_artifact(first_expected)
            for name in moved:
                if name == os.path.basename(first_expected):
                    continue
                self._cleanup_trash_artifact(os.path.join(trash_dir, name))

    def test_permanent_delete_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "guard.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("guard")

            result = agent_v3.tool_delete_files([src], permanent=True, allowed_folder=tmpdir)
            self.assertIn("Blocked", result)
            self.assertTrue(os.path.exists(src))

    def test_windows_path_normalization_allows_mixed_separators(self):
        if os.name != "nt":
            self.skipTest("Windows-only path normalization test")

        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            src_native = os.path.join(tmpdir, "mixed_sep.txt")
            with open(src_native, "w", encoding="utf-8") as f:
                f.write("mixed")
            expected_trash = agent_v3.get_global_trash_path(src_native)

            path_backslashes = src_native.replace("/", "\\")
            allowed_folder_slashes = tmpdir.replace("\\", "/")
            result = agent_v3.tool_delete_files([path_backslashes], allowed_folder=allowed_folder_slashes)

            self.assertIn("Moved to global trash:", result)
            self.assertFalse(os.path.exists(src_native))
            self.assertTrue(os.path.exists(expected_trash))
            self._cleanup_trash_artifact(expected_trash)

    def test_clean_duplicates_uses_global_trash(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            folder_a = os.path.join(tmpdir, "a")
            folder_b = os.path.join(tmpdir, "b")
            os.makedirs(folder_a, exist_ok=True)
            os.makedirs(folder_b, exist_ok=True)

            duplicate_name = f"dup_{uuid.uuid4().hex}.txt"
            file_a = os.path.join(folder_a, duplicate_name)
            file_b = os.path.join(folder_b, duplicate_name)
            with open(file_a, "w", encoding="utf-8") as f:
                f.write("same-content")
            with open(file_b, "w", encoding="utf-8") as f:
                f.write("same-content")

            result = agent_v3.tool_clean_duplicates(tmpdir, keep="newest", allowed_folder=tmpdir)
            self.assertIn("moved to global trash", result)

            missing = file_a if not os.path.exists(file_a) else file_b
            expected_trash = agent_v3.get_global_trash_path(missing)
            self.assertTrue(os.path.exists(expected_trash))
            self._cleanup_trash_artifact(expected_trash)

    def _cleanup_trash_artifact(self, path: str):
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
