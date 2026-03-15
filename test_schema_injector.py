"""
test_schema_injector.py

Unit tests for schema_injector.py — extract_field_paths, inject_schema_to_prompt,
and fetch_api_schema (with mocked HTTP responses).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from schema_injector import (
    MAX_FIELDS,
    extract_field_paths,
    fetch_api_schema,
    inject_schema_to_prompt,
)


# ---------------------------------------------------------------------------
# extract_field_paths
# ---------------------------------------------------------------------------

class ExtractFieldPathsTests(unittest.TestCase):

    def test_flat_dict(self):
        data = {"email": "a@b.com", "id": 1, "name": "Alice"}
        paths = extract_field_paths(data)
        self.assertIn("email", paths)
        self.assertIn("id", paths)
        self.assertIn("name", paths)

    def test_nested_dict(self):
        data = {"profile": {"email": "a@b.com", "age": 30}}
        paths = extract_field_paths(data)
        self.assertIn("profile", paths)
        self.assertIn("profile.email", paths)
        self.assertIn("profile.age", paths)

    def test_list_uses_first_element(self):
        data = {"items": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]}
        paths = extract_field_paths(data)
        self.assertIn("items", paths)
        self.assertIn("items[0]", paths)
        self.assertIn("items[0].id", paths)
        self.assertIn("items[0].title", paths)
        # Second element should NOT create extra paths
        self.assertNotIn("items[1]", paths)

    def test_empty_dict_returns_empty(self):
        self.assertEqual(extract_field_paths({}), [])

    def test_empty_list_no_index_paths(self):
        data = {"items": []}
        paths = extract_field_paths(data)
        self.assertIn("items", paths)
        self.assertNotIn("items[0]", paths)

    def test_deeply_nested_stops_at_max_depth(self):
        # Build a dict nested 10 levels deep
        deep: dict = {}
        current = deep
        for i in range(10):
            current["child"] = {}
            current = current["child"]
        current["leaf"] = "value"

        paths = extract_field_paths(deep, max_depth=3)
        # Should stop before depth 10
        long_path = ".".join(["child"] * 5)
        self.assertNotIn(long_path, paths)

    def test_mixed_structure(self):
        data = {
            "user": {"id": 1, "roles": [{"name": "admin"}]},
            "count": 42,
        }
        paths = extract_field_paths(data)
        self.assertIn("user.id", paths)
        self.assertIn("user.roles", paths)
        self.assertIn("user.roles[0]", paths)
        self.assertIn("user.roles[0].name", paths)
        self.assertIn("count", paths)

    def test_scalar_value(self):
        # Single scalar — nothing to extract
        paths = extract_field_paths("hello")
        self.assertEqual(paths, [])

    def test_max_fields_cap(self):
        # Build a very wide dict to trigger the cap
        data = {f"field_{i}": i for i in range(MAX_FIELDS + 20)}
        paths = extract_field_paths(data)
        self.assertLessEqual(len(paths), MAX_FIELDS)

    def test_no_duplicates(self):
        data = {"a": 1, "b": 2}
        paths = extract_field_paths(data)
        self.assertEqual(len(paths), len(set(paths)))

    def test_prefix_parameter(self):
        """Custom prefix is prepended to all paths."""
        paths = extract_field_paths({"x": 1}, prefix="root")
        self.assertIn("root", paths)
        self.assertIn("root.x", paths)


# ---------------------------------------------------------------------------
# inject_schema_to_prompt
# ---------------------------------------------------------------------------

class InjectSchemaToPromptTests(unittest.TestCase):

    def test_non_empty_schema_contains_paths(self):
        schema = ["email", "profile.name", "items[0].id"]
        result = inject_schema_to_prompt(schema)
        for path in schema:
            self.assertIn(path, result)

    def test_non_empty_schema_has_header(self):
        result = inject_schema_to_prompt(["id"])
        self.assertIn("Доступные поля", result)

    def test_non_empty_schema_has_n8n_example(self):
        result = inject_schema_to_prompt(["id"])
        self.assertIn("$('", result)  # n8n expression hint

    def test_empty_schema_returns_fallback_message(self):
        result = inject_schema_to_prompt([])
        self.assertIn("недоступна", result.lower())

    def test_caps_at_max_fields(self):
        many = [f"field_{i}" for i in range(MAX_FIELDS + 10)]
        result = inject_schema_to_prompt(many)
        # Count bullet lines — should not exceed MAX_FIELDS
        bullet_count = result.count("  - ")
        self.assertLessEqual(bullet_count, MAX_FIELDS)


# ---------------------------------------------------------------------------
# fetch_api_schema
# ---------------------------------------------------------------------------

class FetchApiSchemaTests(unittest.TestCase):

    def _make_mock_response(self, body: bytes, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("schema_injector.urllib.request.urlopen")
    def test_successful_get_returns_paths(self, mock_urlopen):
        payload = {"email": "a@b.com", "id": 1}
        mock_urlopen.return_value = self._make_mock_response(
            json.dumps(payload).encode()
        )
        paths = fetch_api_schema("https://api.example.com/user")
        self.assertIn("email", paths)
        self.assertIn("id", paths)

    @patch("schema_injector.urllib.request.urlopen")
    def test_nested_response_returns_nested_paths(self, mock_urlopen):
        payload = {"profile": {"name": "Alice", "age": 30}}
        mock_urlopen.return_value = self._make_mock_response(
            json.dumps(payload).encode()
        )
        paths = fetch_api_schema("https://api.example.com/profile")
        self.assertIn("profile.name", paths)
        self.assertIn("profile.age", paths)

    @patch("schema_injector.urllib.request.urlopen")
    def test_invalid_json_raises_value_error(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response(b"not-json")
        with self.assertRaises(ValueError):
            fetch_api_schema("https://api.example.com/bad")

    @patch("schema_injector.urllib.request.urlopen")
    def test_custom_headers_passed(self, mock_urlopen):
        payload = {"ok": True}
        mock_urlopen.return_value = self._make_mock_response(
            json.dumps(payload).encode()
        )
        fetch_api_schema(
            "https://api.example.com/secure",
            headers={"Authorization": "Bearer token"},
        )
        # Verify urlopen was called (headers are set on the Request object)
        mock_urlopen.assert_called_once()

    @patch("schema_injector.urllib.request.urlopen")
    def test_post_method_used(self, mock_urlopen):
        payload = {"result": "ok"}
        mock_urlopen.return_value = self._make_mock_response(
            json.dumps(payload).encode()
        )
        fetch_api_schema("https://api.example.com/create", method="POST")
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        self.assertEqual(request_obj.get_method(), "POST")

    @patch("schema_injector.urllib.request.urlopen")
    def test_empty_json_object_returns_empty_list(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response(b"{}")
        paths = fetch_api_schema("https://api.example.com/empty")
        self.assertEqual(paths, [])


if __name__ == "__main__":
    unittest.main()
