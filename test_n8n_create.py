import json
import os
import shutil
import tempfile
import unittest

from controller import create_controller


class N8NCreateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="jane_n8n_create_")
        self.memory_dir = os.path.join(self.temp_root, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_create_calls_n8n_create_with_valid_workflow_json(self):
        calls = {"create": []}

        def n8n_list_workflows(args):
            return json.dumps({"data": []})

        def n8n_create_workflow(args):
            calls["create"].append(args)
            wf = args.get("workflow_json", {})
            return json.dumps({"id": "wf-100", "name": wf.get("name", "")})

        def n8n_get_workflow(args):
            return json.dumps({"id": args.get("id"), "name": "Test Workflow"})

        tools = {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_get_workflow": n8n_get_workflow,
        }
        controller = create_controller(self.memory_dir, tools)

        msg = "создай новый workflow в n8n под названием Test Workflow с одним manual trigger и node set который выводит hello"
        result = controller.handle_request(msg)

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "n8n_create_workflow")
        self.assertEqual(len(calls["create"]), 1)

        payload = calls["create"][0].get("workflow_json", {})
        self.assertEqual(payload.get("name"), "Test Workflow")
        self.assertNotIn("active", payload)
        self.assertIn("nodes", payload)
        self.assertIn("connections", payload)
        self.assertGreaterEqual(len(payload.get("nodes", [])), 2)

        trigger = payload["nodes"][0]
        self.assertEqual(trigger.get("type"), "n8n-nodes-base.manualTrigger")
        set_nodes = [n for n in payload["nodes"] if n.get("type") == "n8n-nodes-base.set"]
        self.assertTrue(set_nodes)

        assignments = set_nodes[0].get("parameters", {}).get("assignments", {}).get("assignments", [])
        message_values = [a.get("value") for a in assignments if a.get("name") == "message"]
        self.assertIn("hello", message_values)

    def test_create_response_has_no_manual_ui_steps(self):
        def n8n_list_workflows(args):
            return json.dumps({"data": []})

        def n8n_create_workflow(args):
            return json.dumps({"id": "wf-101", "name": args.get("workflow_json", {}).get("name")})

        def n8n_get_workflow(args):
            return json.dumps({"id": args.get("id"), "name": "A"})

        controller = create_controller(self.memory_dir, {
            "n8n_list_workflows": n8n_list_workflows,
            "n8n_create_workflow": n8n_create_workflow,
            "n8n_get_workflow": n8n_get_workflow,
        })

        result = controller.handle_request('make an n8n workflow named "A"')
        text = (result.get("response") or "").lower()

        self.assertNotIn("open n8n", text)
        self.assertNotIn("click", text)
        self.assertIn("workflow", text)

    def test_name_extraction_ru_en(self):
        controller = create_controller(self.memory_dir, {})

        ru = controller.intent_classifier.classify("создай новый workflow в n8n под названием Мой Тест")
        en = controller.intent_classifier.classify("make an n8n workflow named Test Flow")

        self.assertIsNotNone(ru)
        self.assertIsNotNone(en)
        self.assertEqual(ru[0], "N8N_CREATE_WORKFLOW")
        self.assertEqual(en[0], "N8N_CREATE_WORKFLOW")
        self.assertEqual(ru[1].get("workflow_name"), "Мой Тест")
        self.assertEqual(en[1].get("workflow_name"), "Test Flow")

    def test_name_extraction_ru_multiline_pod_nazvaniem(self):
        controller = create_controller(self.memory_dir, {})
        msg = "создай новый workflow в n8n\nпод названием \"Test Workflow\"\nс одним manual trigger"
        parsed = controller.intent_classifier.classify(msg)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0], "N8N_CREATE_WORKFLOW")
        self.assertEqual(parsed[1].get("workflow_name"), "Test Workflow")


if __name__ == "__main__":
    unittest.main()
