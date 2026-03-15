#!/usr/bin/env python3
"""
Ð¢ÐµÑÑ‚Ñ‹ Ð´Ð»Ñ Agent Controller Layer

Ð˜Ð¡ÐŸÐžÐ›Ð¬Ð—ÐžÐ’ÐÐÐ˜Ð•:
    python test_controller.py
"""

import os
import sys
import json
import tempfile
from typing import Dict, Any


# Mock tools Ð´Ð»Ñ Ñ‚ÐµÑÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ (ÑÐ¼ÑƒÐ»ÑÑ†Ð¸Ñ TOOLS Ð¸Ð· agent_v3)
class MockTools:
    """ÐœÐ¾Ðº-Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ Ñ‚ÐµÑÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ"""
    
    @staticmethod
    def find_duplicates(args: Dict) -> str:
        path = args["path"]
        return f"""Found 3 groups of duplicates (8 files total, ~150 MB wasted space).
ACTION: Use clean_duplicates tool to automatically move older copies to trash.

Top 3 largest duplicate groups:
  photo.jpg (50 MB):
    - {path}/photo.jpg  [2024-01-15 10:30]
    - {path}/backup/photo.jpg  [2024-01-10 09:00]
  
  document.pdf (30 MB):
    - {path}/document.pdf  [2024-02-01 14:20]
    - {path}/old/document.pdf  [2024-01-20 11:00]
"""
    
    @staticmethod
    def clean_duplicates(args: Dict) -> str:
        path = args["path"]
        keep = args.get("keep", "newest")
        return f"""Cleaned 4 duplicate files, freed ~100 MB
Kept 4 originals ({keep} copy of each)
Files moved to _trash folders (recoverable!)

Kept files (first 4):
  âœ“ photo.jpg â€” {path}/photo.jpg
  âœ“ document.pdf â€” {path}/document.pdf
"""
    
    @staticmethod
    def organize_folder(args: Dict) -> str:
        path = args["path"]
        return f"""Organized {path}:
- Created folders: Documents/, Images/, Videos/, Archives/
- Moved 47 files
- 0 errors
"""
    
    @staticmethod
    def disk_usage(args: Dict) -> str:
        path = args["path"]
        return f"""Disk usage for {path}:
Total: 15.2 GB
  Documents: 5.1 GB (33%)
  Images: 8.3 GB (55%)
  Videos: 1.8 GB (12%)
"""
    
    @staticmethod
    def browse_as_me(args: Dict) -> str:
        url = args["url"]
        return f"""Opened {url} in Chrome with your profile.
Session active. Cookies loaded.
"""


def create_mock_tools() -> Dict:
    """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ mock-Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ð¾Ð²"""
    return {
        "find_duplicates": MockTools.find_duplicates,
        "clean_duplicates": MockTools.clean_duplicates,
        "organize_folder": MockTools.organize_folder,
        "disk_usage": MockTools.disk_usage,
        "browse_as_me": MockTools.browse_as_me,
    }


# ============================================================
# TEST SUITE
# ============================================================

class ControllerTests:
    """ÐÐ°Ð±Ð¾Ñ€ Ñ‚ÐµÑÑ‚Ð¾Ð² Ð´Ð»Ñ ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»Ð»ÐµÑ€Ð°"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.memory_dir = tempfile.mkdtemp()
        
        # Import controller
        try:
            from controller import create_controller
            self.controller = create_controller(self.memory_dir, create_mock_tools())
        except ImportError:
            print("âŒ ERROR: controller.py not found")
            print("   Make sure controller.py is in the same directory")
            sys.exit(1)
    
    def run_all(self):
        """Ð—Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ñ‚ÐµÑÑ‚Ñ‹"""
        print("=" * 70)
        print("AGENT CONTROLLER LAYER â€” TEST SUITE")
        print("=" * 70)
        print()
        
        # Intent Classification Tests
        print("ðŸ“‹ INTENT CLASSIFICATION TESTS")
        print("-" * 70)
        self.test_clean_duplicates_intent()
        self.test_find_duplicates_intent()
        self.test_followup_intent()
        self.test_organize_intent()
        self.test_disk_usage_intent()
        self.test_browse_intent()
        self.test_no_intent()
        print()
        
        # Workflow Planning Tests
        print("ðŸ“ WORKFLOW PLANNING TESTS")
        print("-" * 70)
        self.test_workflow_duplicates_cleanup()
        self.test_workflow_duplicates_scan()
        print()
        
        # Policy Engine Tests
        print("ðŸ›¡ï¸  POLICY ENGINE TESTS")
        print("-" * 70)
        self.test_policy_safe_operation()
        self.test_policy_forbidden_path()
        self.test_policy_nonexistent_file()
        self.test_policy_delete_outside_allowed_folder()
        print()

        
        # State Manager Tests
        print("ðŸ’¾ STATE MANAGER TESTS")
        print("-" * 70)
        self.test_state_save_load()
        self.test_state_duplicates_context()
        print()
        
        # Integration Tests
        print("ðŸš€ INTEGRATION TESTS")
        print("-" * 70)
        self.test_full_workflow_clean_duplicates()
        self.test_full_workflow_followup()
        print()
        
        # Summary
        print("=" * 70)
        print(f"RESULTS: {self.passed} passed, {self.failed} failed")
        print("=" * 70)
        
        return self.failed == 0
    
    def assert_equal(self, actual, expected, test_name: str):
        """ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ñ€Ð°Ð²ÐµÐ½ÑÑ‚Ð²Ð°"""
        if actual == expected:
            print(f"  âœ… {test_name}")
            self.passed += 1
        else:
            print(f"  âŒ {test_name}")
            print(f"     Expected: {expected}")
            print(f"     Got: {actual}")
            self.failed += 1
    
    def assert_true(self, condition, test_name: str):
        """ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¸ÑÑ‚Ð¸Ð½Ð½Ð¾ÑÑ‚Ð¸"""
        if condition:
            print(f"  âœ… {test_name}")
            self.passed += 1
        else:
            print(f"  âŒ {test_name}")
            self.failed += 1
    
    def assert_in(self, substring: str, text: str, test_name: str):
        """ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð²Ñ…Ð¾Ð¶Ð´ÐµÐ½Ð¸Ñ"""
        if substring in text:
            print(f"  âœ… {test_name}")
            self.passed += 1
        else:
            print(f"  âŒ {test_name}")
            print(f"     Expected '{substring}' in text")
            self.failed += 1
    
    # ============================================================
    # INTENT CLASSIFICATION TESTS
    # ============================================================
    
    def test_clean_duplicates_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        result = self.controller.intent_classifier.classify(
            "Ð½Ð°Ð¹Ð´Ð¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ Ð² C:/Temp Ð¸ ÑƒÐ´Ð°Ð»Ð¸ ÑÑ‚Ð°Ñ€Ñ‹Ðµ"
        )
        self.assert_true(result is not None, "Intent detected")
        if result:
            intent, params = result
            self.assert_equal(intent, "CLEAN_DUPLICATES_KEEP_NEWEST", "Correct intent")
            self.assert_equal(params.get("path"), "C:/Temp", "Path extracted")
    
    def test_find_duplicates_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ Ð¿Ð¾Ð¸ÑÐºÐ° Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        result = self.controller.intent_classifier.classify(
            "Ð½Ð°Ð¹Ð´Ð¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ Ð² Downloads"
        )
        self.assert_true(result is not None, "Intent detected")
        if result:
            intent, params = result
            self.assert_equal(intent, "FIND_DUPLICATES_ONLY", "Correct intent")
    
    def test_followup_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ follow-up ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹"""
        # Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ð¼ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚
        self.controller.state.session.pending_intent = "CLEAN_DUPLICATES_AVAILABLE"
        self.controller.state.session.last_duplicates_path = "C:/Downloads"
        
        result = self.controller.intent_classifier.classify("ÑƒÐ´Ð°Ð»Ð¸ ÑÑ‚Ð°Ñ€Ñ‹Ðµ")
        self.assert_true(result is not None, "Follow-up intent detected")
        if result:
            intent, params = result
            self.assert_equal(intent, "DELETE_OLD_DUPLICATES_FOLLOWUP", "Correct intent")
            self.assert_equal(params.get("path"), "C:/Downloads", "Path from state")
    
    def test_organize_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ Ð¾Ñ€Ð³Ð°Ð½Ð¸Ð·Ð°Ñ†Ð¸Ð¸"""
        result = self.controller.intent_classifier.classify(
            "Ð¾Ñ€Ð³Ð°Ð½Ð¸Ð·ÑƒÐ¹ Ñ„Ð°Ð¹Ð»Ñ‹ Ð² Documents"
        )
        self.assert_true(result is not None, "Intent detected")
        if result:
            intent, _ = result
            self.assert_equal(intent, "ORGANIZE_FOLDER_BY_TYPE", "Correct intent")
    
    def test_disk_usage_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ Ð°Ð½Ð°Ð»Ð¸Ð·Ð° Ð´Ð¸ÑÐºÐ°"""
        result = self.controller.intent_classifier.classify(
            "ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð¼ÐµÑÑ‚Ð° Ð·Ð°Ð½ÑÑ‚Ð¾ Ð½Ð° Ð´Ð¸ÑÐºÐµ C:/"
        )
        self.assert_true(result is not None, "Intent detected")
        if result:
            intent, _ = result
            self.assert_equal(intent, "DISK_USAGE_REPORT", "Correct intent")
    
    def test_browse_intent(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ Ð±Ñ€Ð°ÑƒÐ·Ð¸Ð½Ð³Ð°"""
        result = self.controller.intent_classifier.classify(
            "Ð¾Ñ‚ÐºÑ€Ð¾Ð¹ https://gmail.com"
        )
        self.assert_true(result is not None, "Intent detected")
        if result:
            intent, params = result
            self.assert_equal(intent, "BROWSE_WITH_LOGIN", "Correct intent")
            self.assert_equal(params.get("url"), "https://gmail.com", "URL extracted")
    
    def test_no_intent(self):
        """Ð¢ÐµÑÑ‚: Ð½ÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð¾Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ðµ"""
        result = self.controller.intent_classifier.classify(
            "Ñ€Ð°ÑÑÐºÐ°Ð¶Ð¸ Ð¼Ð½Ðµ Ð°Ð½ÐµÐºÐ´Ð¾Ñ‚ Ð¿Ñ€Ð¾ Ð¿Ñ€Ð¾Ð³Ñ€Ð°Ð¼Ð¼Ð¸ÑÑ‚Ð¾Ð²"
        )
        self.assert_true(result is None, "No intent for unknown request")
    
    # ============================================================
    # WORKFLOW PLANNING TESTS
    # ============================================================
    
    def test_workflow_duplicates_cleanup(self):
        """Ð¢ÐµÑÑ‚: Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ workflow Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¸"""
        workflow = self.controller.planner.plan(
            "CLEAN_DUPLICATES_KEEP_NEWEST",
            {"path": "C:/Temp"}
        )
        self.assert_equal(len(workflow), 1, "Single-step workflow")
        if workflow:
            step = workflow[0]
            self.assert_equal(step.tool, "clean_duplicates", "Correct tool")
            self.assert_equal(step.args["path"], "C:/Temp", "Path passed")
    
    def test_workflow_duplicates_scan(self):
        """Ð¢ÐµÑÑ‚: Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ workflow ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ"""
        workflow = self.controller.planner.plan(
            "FIND_DUPLICATES_ONLY",
            {"path": "C:/Downloads"}
        )
        self.assert_equal(len(workflow), 1, "Single-step workflow")
        if workflow:
            self.assert_equal(workflow[0].tool, "find_duplicates", "Correct tool")
    
    # ============================================================
    # POLICY ENGINE TESTS
    # ============================================================
    
    def test_policy_safe_operation(self):
        """Ð¢ÐµÑÑ‚: Ñ€Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ð°Ñ Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸Ñ"""
        self.controller.policy.set_requested_folder("C:/Temp")
        allowed, reason = self.controller.policy.check_operation(
            "clean_duplicates",
            {"path": "C:/Temp"}
        )
        self.assert_true(allowed, "Safe operation allowed")
        self.assert_equal(reason, None, "No error reason")
    
    def test_policy_forbidden_path(self):
        """Ð¢ÐµÑÑ‚: Ð·Ð°Ð¿Ñ€ÐµÑ‰Ñ‘Ð½Ð½Ñ‹Ð¹ Ð¿ÑƒÑ‚ÑŒ"""
        allowed, reason = self.controller.policy.check_operation(
            "clean_duplicates",
            {"path": "C:/Windows/System32"}
        )
        self.assert_true(not allowed, "Forbidden path blocked")
        self.assert_true(reason is not None, "Error reason provided")
    
    def test_policy_nonexistent_file(self):
        """Ð¢ÐµÑÑ‚: Ð½ÐµÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ð¹ Ñ„Ð°Ð¹Ð»"""
        self.controller.policy.set_requested_folder("/nonexistent")
        allowed, reason = self.controller.policy.check_operation(
            "delete_files",
            {"paths": ["/nonexistent/file.txt"]}
        )
        self.assert_true(not allowed, "Nonexistent file blocked")
        self.assert_in("Ð½Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‚", reason, "Correct error message")
    
    def test_policy_delete_outside_allowed_folder(self):
        """Тест: удаление вне allowed folder"""
        self.controller.policy.set_requested_folder("C:/Allowed")
        allowed, reason = self.controller.policy.check_operation(
            "clean_duplicates",
            {"path": "C:/Other"}
        )
        self.assert_true(not allowed, "Outside-folder deletion blocked")
        self.assert_in("allowed folder", reason, "Allowed-folder rule enforced")
    # ============================================================
    # STATE MANAGER TESTS
    # ============================================================
    
    def test_state_save_load(self):
        """Ð¢ÐµÑÑ‚: ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ Ð¸ Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ñ"""
        # Save
        self.controller.state.session.last_duplicates_path = "C:/Test"
        self.controller.state.save()
        
        # Load (create new state manager)
        from controller import StateManager
        new_state = StateManager(self.memory_dir)
        
        self.assert_equal(
            new_state.session.last_duplicates_path,
            "C:/Test",
            "State persisted"
        )
    
    def test_state_duplicates_context(self):
        """Ð¢ÐµÑÑ‚: ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        duplicates_map = {"file.txt": ["path1", "path2"]}
        self.controller.state.update_duplicates_scan("C:/Test", duplicates_map)
        
        context = self.controller.state.get_duplicates_context()
        self.assert_true(context is not None, "Context available")
        if context:
            self.assert_equal(context["path"], "C:/Test", "Path saved")
            self.assert_equal(context["count"], 1, "Count saved")
    
    # ============================================================
    # INTEGRATION TESTS
    # ============================================================
    
    def test_full_workflow_clean_duplicates(self):
        """Ð˜Ð½Ñ‚ÐµÐ³Ñ€Ð°Ñ†Ð¸Ð¾Ð½Ð½Ñ‹Ð¹ Ñ‚ÐµÑÑ‚: Ð¿Ð¾Ð»Ð½Ñ‹Ð¹ workflow Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¸"""
        result = self.controller.handle_request(
            "Ð½Ð°Ð¹Ð´Ð¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ Ð² C:/Temp Ð¸ ÑƒÐ´Ð°Ð»Ð¸ ÑÑ‚Ð°Ñ€Ñ‹Ðµ"
        )
        
        self.assert_true(result.get("handled"), "Request handled")
        self.assert_equal(result.get("tool_name"), "clean_duplicates", "Correct tool")
        self.assert_in("Cleaned", result.get("response", ""), "Success message")
        self.assert_equal(len(result.get("steps", [])), 1, "Single step executed")
    
    def test_full_workflow_followup(self):
        """Ð˜Ð½Ñ‚ÐµÐ³Ñ€Ð°Ñ†Ð¸Ð¾Ð½Ð½Ñ‹Ð¹ Ñ‚ÐµÑÑ‚: follow-up workflow"""
        # Step 1: Find duplicates
        result1 = self.controller.handle_request("Ð½Ð°Ð¹Ð´Ð¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ Ð² C:/Test")
        self.assert_true(result1.get("handled"), "Find request handled")
        
        # Step 2: Delete (follow-up)
        result2 = self.controller.handle_request("ÑƒÐ´Ð°Ð»Ð¸ ÑÑ‚Ð°Ñ€Ñ‹Ðµ")
        self.assert_true(result2.get("handled"), "Follow-up handled")
        self.assert_equal(result2.get("tool_name"), "clean_duplicates", "Used cleanup")
        
        # State should be cleared
        self.assert_equal(
            self.controller.state.session.pending_intent,
            None,
            "State cleared after cleanup"
        )


def main():
    """Ð—Ð°Ð¿ÑƒÑÐº Ñ‚ÐµÑÑ‚Ð¾Ð²"""
    tests = ControllerTests()
    success = tests.run_all()
    
    if success:
        print()
        print("ðŸŽ‰ ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print()
        print("âŒ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
