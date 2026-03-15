import json
import os
import shutil
import tempfile
import unittest

from controller import create_controller


class N8NWorkflowBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="jane_n8n_builder_")
        self.memory_dir = os.path.join(self.temp_root, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_recipe_selection_ru_en_sv(self):
        controller = create_controller(self.memory_dir, {})
        ru = controller.intent_classifier.classify("сделай контент-завод в n8n")
        en = controller.intent_classifier.classify("make an n8n automation that parses web pages and sends telegram")
        sv = controller.intent_classifier.classify("bygg ett n8n-workflow som skrapar kommun kontaktdata")
        self.assertIsNotNone(ru)
        self.assertIsNotNone(en)
        self.assertIsNotNone(sv)
        self.assertEqual(ru[0], "N8N_BUILD_WORKFLOW")
        self.assertEqual(en[0], "N8N_BUILD_WORKFLOW")
        self.assertEqual(sv[0], "N8N_BUILD_WORKFLOW")

    def test_missing_params_prompt_and_stop(self):
        controller = create_controller(self.memory_dir, {})
        result = controller.handle_request("создай workflow в n8n: контент-завод")
        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "chat")
        self.assertIn("Google Sheet ID", result.get("response", ""))
        self.assertEqual(controller.state.session.pending_intent, "N8N_BUILD_WORKFLOW_MISSING_PARAMS")

    def test_build_json_validation_and_create_called(self):
        calls = {"validate": 0, "create": 0}

        def n8n_validate_workflow(args):
            calls["validate"] += 1
            return json.dumps({"valid": True, "errors": []})

        def n8n_list_workflows(args):
            return json.dumps({"data": []})

        def n8n_create_workflow(args):
            calls["create"] += 1
            wf = args.get("workflow_json", {})
            return json.dumps({"id": "wf-build-1", "name": wf.get("name", "")})

        def n8n_run_workflow(args):
            return json.dumps({"execution_id": "exec-1"})

        def n8n_get_execution(args):
            return json.dumps({"id": args.get("execution_id"), "status": "success", "data": {"resultData": {}}})

        controller = create_controller(
            self.memory_dir,
            {
                "n8n_validate_workflow": n8n_validate_workflow,
                "n8n_list_workflows": n8n_list_workflows,
                "n8n_create_workflow": n8n_create_workflow,
                "n8n_run_workflow": n8n_run_workflow,
                "n8n_get_execution": n8n_get_execution,
            },
        )

        result = controller._handle_n8n_build_workflow(
            {
                "recipe_key": "content_factory",
                "workflow_name": "Content Factory",
                "params": {
                    "sheet_id": "sheet_12345678",
                    "sheet_range": "A:A",
                    "google_sheets_credential": "gs_cred",
                    "notion_db_id": "notion_12345678",
                    "notion_credential": "notion_cred",
                    "telegram_credential": "telegram_cred",
                },
                "raw_user_message": "create",
            }
        )

        self.assertTrue(result.get("handled"))
        self.assertGreaterEqual(calls["validate"], 1)
        self.assertEqual(calls["create"], 1)
        self.assertIn("final status: SUCCESS", result.get("response", ""))

    def test_build_error_triggers_debug_loop_then_success(self):
        state = {"latest_execution": "exec-1", "created": False, "updates": 0, "run_calls": 0}
        workflow_store = {
            "id": "wf-debug-1",
            "name": "Content Factory",
            "active": False,
            "nodes": [
                {
                    "id": "node-1",
                    "name": "Webhook Trigger",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"httpMethod": "POSTTT", "path": "bad"},
                }
            ],
            "connections": {},
        }
        executions = {
            "exec-1": {
                "id": "exec-1",
                "status": "error",
                "data": {"resultData": {"lastNodeExecuted": "Webhook Trigger", "error": {"message": "Invalid value for httpMethod"}}},
            },
            "exec-2": {"id": "exec-2", "status": "success", "data": {"resultData": {}}},
        }

        def n8n_validate_workflow(args):
            return json.dumps({"valid": True, "errors": []})

        def n8n_list_workflows(args):
            if state["created"]:
                return json.dumps({"data": [{"id": "wf-debug-1", "name": "Content Factory", "active": False}]})
            return json.dumps({"data": []})

        def n8n_create_workflow(args):
            state["created"] = True
            return json.dumps({"id": "wf-debug-1", "name": "Content Factory"})

        def n8n_get_workflow(args):
            return json.dumps(workflow_store)

        def n8n_run_workflow(args):
            state["run_calls"] += 1
            if state["run_calls"] == 1:
                return json.dumps({"execution_id": "exec-1"})
            state["latest_execution"] = "exec-2"
            return json.dumps({"execution_id": "exec-2"})

        def n8n_get_execution(args):
            return json.dumps(executions[args["execution_id"]])

        def n8n_get_executions(args):
            eid = state["latest_execution"]
            return json.dumps({"data": [{"id": eid, "status": executions[eid]["status"], "startedAt": "2026-02-12T10:00:00Z"}]})

        def n8n_update_workflow(args):
            state["updates"] += 1
            return json.dumps({"id": "wf-debug-1", "updated": True})

        controller = create_controller(
            self.memory_dir,
            {
                "n8n_validate_workflow": n8n_validate_workflow,
                "n8n_list_workflows": n8n_list_workflows,
                "n8n_create_workflow": n8n_create_workflow,
                "n8n_get_workflow": n8n_get_workflow,
                "n8n_run_workflow": n8n_run_workflow,
                "n8n_get_execution": n8n_get_execution,
                "n8n_get_executions": n8n_get_executions,
                "n8n_update_workflow": n8n_update_workflow,
            },
        )

        result = controller._handle_n8n_build_workflow(
            {
                "recipe_key": "content_factory",
                "workflow_name": "Content Factory",
                "params": {
                    "sheet_id": "sheet_12345678",
                    "sheet_range": "A:A",
                    "google_sheets_credential": "gs_cred",
                    "notion_db_id": "notion_12345678",
                    "notion_credential": "notion_cred",
                    "telegram_credential": "telegram_cred",
                },
                "raw_user_message": "create and run CONFIRM",
            }
        )

        self.assertTrue(result.get("handled"))
        self.assertIn("final status: SUCCESS", result.get("response", ""))
        self.assertGreaterEqual(state["updates"], 1)

    def test_update_creates_backup(self):
        state = {"updated": 0}
        existing = {
            "id": "wf-22",
            "name": "Content Factory",
            "active": False,
            "nodes": [{"id": "node-1", "name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "parameters": {}}],
            "connections": {},
        }

        def n8n_validate_workflow(args):
            return json.dumps({"valid": True, "errors": []})

        def n8n_list_workflows(args):
            return json.dumps({"data": [{"id": "wf-22", "name": "Content Factory", "active": False}]})

        def n8n_get_workflow(args):
            return json.dumps(existing)

        def n8n_update_workflow(args):
            state["updated"] += 1
            return json.dumps({"id": "wf-22", "updated": True})

        def n8n_run_workflow(args):
            return json.dumps({"execution_id": "exec-ok"})

        def n8n_get_execution(args):
            return json.dumps({"id": "exec-ok", "status": "success", "data": {"resultData": {}}})

        controller = create_controller(
            self.memory_dir,
            {
                "n8n_validate_workflow": n8n_validate_workflow,
                "n8n_list_workflows": n8n_list_workflows,
                "n8n_get_workflow": n8n_get_workflow,
                "n8n_update_workflow": n8n_update_workflow,
                "n8n_run_workflow": n8n_run_workflow,
                "n8n_get_execution": n8n_get_execution,
            },
        )

        result = controller._handle_n8n_build_workflow(
            {
                "recipe_key": "content_factory",
                "workflow_name": "Content Factory",
                "params": {
                    "sheet_id": "sheet_12345678",
                    "sheet_range": "A:A",
                    "google_sheets_credential": "gs_cred",
                    "notion_db_id": "notion_12345678",
                    "notion_credential": "notion_cred",
                    "telegram_credential": "telegram_cred",
                },
                "raw_user_message": "update",
            }
        )

        self.assertTrue(result.get("handled"))
        self.assertGreaterEqual(state["updated"], 1)
        backup_dir = os.path.join(self.memory_dir, "n8n_backups")
        self.assertTrue(os.path.isdir(backup_dir))
        self.assertTrue(os.listdir(backup_dir))
        self.assertIn("backup:", result.get("response", ""))


if __name__ == "__main__":
    unittest.main()
