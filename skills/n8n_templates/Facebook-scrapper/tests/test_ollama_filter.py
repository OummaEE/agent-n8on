"""
tests/test_ollama_filter.py — Tests for Ollama event filter

Tests cover:
1. _parse_ollama_json() — JSON extraction from model responses
2. _build_user_message() — prompt construction from post data
3. classify_post() — single post classification
4. filter_posts_batch() — batch filtering
5. Error handling (timeout, bad JSON, Ollama unavailable)
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestParseOllamaJson(unittest.TestCase):
    """Tests for _parse_ollama_json() — JSON extraction."""

    def _parse(self, text):
        from scraper.ollama_filter import _parse_ollama_json
        return _parse_ollama_json(text)

    def test_clean_json(self):
        """Clean JSON object → parsed."""
        r = self._parse('{"is_event": true, "title": "Konsert"}')
        self.assertEqual(r["is_event"], True)
        self.assertEqual(r["title"], "Konsert")

    def test_json_wrapped_in_markdown(self):
        """Markdown code block → stripped and parsed."""
        r = self._parse('```json\n{"is_event": false}\n```')
        self.assertIsNotNone(r)
        self.assertEqual(r["is_event"], False)

    def test_not_event_minimal(self):
        """Minimal not-event response."""
        r = self._parse('{"is_event": false}')
        self.assertIsNotNone(r)
        self.assertFalse(r["is_event"])

    def test_full_event_response(self):
        """Full event response with all fields."""
        raw = """{
          "is_event": true,
          "title": "Jazz konsert",
          "date": "15 mars 2025",
          "time": "19:00",
          "location": "Kulturhuset",
          "description": "Livejazz med lokala musiker.",
          "registration_url": "https://tickets.se/jazz"
        }"""
        r = self._parse(raw)
        self.assertIsNotNone(r)
        self.assertTrue(r["is_event"])
        self.assertEqual(r["title"], "Jazz konsert")
        self.assertEqual(r["time"], "19:00")

    def test_no_json_returns_none(self):
        """No JSON object → None."""
        r = self._parse("Det är inget evenemang.")
        self.assertIsNone(r)

    def test_trailing_comma_fixed(self):
        """Trailing comma → auto-fixed."""
        r = self._parse('{"is_event": true, "title": "Event",}')
        self.assertIsNotNone(r)
        self.assertEqual(r["title"], "Event")

    def test_text_before_json(self):
        """Text before JSON → JSON still extracted."""
        r = self._parse('Here is the analysis: {"is_event": false}')
        self.assertIsNotNone(r)
        self.assertFalse(r["is_event"])


class TestBuildUserMessage(unittest.TestCase):
    """Tests for _build_user_message() — prompt construction."""

    def _build(self, post):
        from scraper.ollama_filter import _build_user_message
        return _build_user_message(post)

    def test_includes_text(self):
        msg = self._build({"text": "Välkommen till konsert 15 mars!"})
        self.assertIn("Välkommen till konsert", msg)

    def test_includes_author(self):
        msg = self._build({"text": "text", "author": "Kulturhuset"})
        self.assertIn("Kulturhuset", msg)

    def test_includes_ocr_text(self):
        msg = self._build({"text": "text", "ocr_text": "19:00 Jazz Night"})
        self.assertIn("19:00 Jazz Night", msg)
        self.assertIn("OCR", msg)

    def test_includes_attachment(self):
        msg = self._build({"text": "text", "attachment": "Registrera dig nu"})
        self.assertIn("Registrera dig nu", msg)

    def test_empty_post_returns_empty(self):
        msg = self._build({})
        self.assertEqual(msg.strip(), "")

    def test_text_truncated_to_1500(self):
        long_text = "x" * 2000
        msg = self._build({"text": long_text})
        # Text is sliced to 1500 chars — total "x" count should be < 2000
        self.assertLess(msg.count("x"), 2000)


class TestClassifyPost(unittest.TestCase):
    """Tests for classify_post() — single post classification."""

    def _make_ollama_response(self, content: str):
        """Build a mock httpx response."""
        import json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": content}
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_event_post_returns_dict(self):
        """Ollama says is_event=true → dict with metadata."""
        from scraper import ollama_filter as of

        ollama_json = '{"is_event": true, "title": "Konsert", "date": "15 mars", "time": "19:00", "location": "Stockholm", "description": "Jazz.", "registration_url": ""}'
        post = {
            "text": "Konsert 15 mars",
            "post_url": "https://fb.com/posts/123",
            "author": "Jazz Club",
            "timestamp_raw": "15 mars",
            "group_url": "https://fb.com/groups/456",
            "image_urls": ["https://img.jpg"],
        }

        mock_resp = self._make_ollama_response(ollama_json)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(of.classify_post(post))

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Konsert")
        self.assertEqual(result["post_url"], "https://fb.com/posts/123")
        self.assertEqual(result["source"], "ollama")

    def test_non_event_returns_none(self):
        """Ollama says is_event=false → None."""
        from scraper import ollama_filter as of

        post = {"text": "Selling used furniture, contact me", "post_url": "https://fb.com/1"}
        mock_resp = self._make_ollama_response('{"is_event": false}')

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(of.classify_post(post))

        self.assertIsNone(result)

    def test_ollama_timeout_returns_none(self):
        """Ollama times out → None, no exception."""
        from scraper import ollama_filter as of
        import httpx

        post = {"text": "Some post text here", "post_url": "https://fb.com/2"}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value = mock_client

            result = asyncio.run(of.classify_post(post))

        self.assertIsNone(result)

    def test_bad_json_response_returns_none(self):
        """Ollama returns non-JSON → None."""
        from scraper import ollama_filter as of

        post = {"text": "Some post text for testing", "post_url": "https://fb.com/3"}
        mock_resp = self._make_ollama_response("I cannot determine if this is an event.")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(of.classify_post(post))

        self.assertIsNone(result)

    def test_empty_post_returns_none(self):
        """Empty post (no text) → None without calling Ollama."""
        from scraper import ollama_filter as of

        result = asyncio.run(of.classify_post({}))
        self.assertIsNone(result)


class TestFilterPostsBatch(unittest.TestCase):
    """Tests for filter_posts_batch() — batch classification."""

    def _make_posts(self):
        return [
            {"text": "Konsert lördag 15 mars 2025 kl 19:00", "post_url": "https://fb.com/1", "image_urls": []},
            {"text": "Säljer soffa, bra skick, 500 kr", "post_url": "https://fb.com/2", "image_urls": []},
            {"text": "Workshop om programmering 22 mars", "post_url": "https://fb.com/3", "image_urls": []},
        ]

    def test_filters_to_events_only(self):
        """Only event posts pass through."""
        from scraper import ollama_filter as of

        event_json = '{"is_event": true, "title": "Event", "date": "15 mars", "time": "19:00", "location": "", "description": "Test", "registration_url": ""}'
        no_event_json = '{"is_event": false}'

        call_count = [0]
        def fake_ollama(user_msg):
            call_count[0] += 1
            # Alternating: event, not-event, event
            if call_count[0] % 2 == 1:
                return {"is_event": True, "title": f"Event {call_count[0]}", "date": "15 mars", "time": "19:00", "location": "", "description": "desc", "registration_url": ""}
            return None

        async def run():
            with patch.object(of, "_call_ollama_sync", side_effect=fake_ollama):
                return await of.filter_posts_batch(self._make_posts(), "TestGroup")

        results = asyncio.run(run())
        # 2 out of 3 posts are events (calls 1, 3)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["group_name"], "TestGroup")
            self.assertEqual(r["source"], "ollama")

    def test_empty_posts_returns_empty(self):
        """Empty list → empty list, no Ollama calls."""
        from scraper import ollama_filter as of

        result = asyncio.run(of.filter_posts_batch([], "TestGroup"))
        self.assertEqual(result, [])

    def test_all_filtered_out(self):
        """All posts are non-events → empty list."""
        from scraper import ollama_filter as of

        with patch.object(of, "_call_ollama_sync", return_value=None):
            results = asyncio.run(of.filter_posts_batch(self._make_posts(), "TestGroup"))

        self.assertEqual(results, [])


class TestIsOllamaAvailable(unittest.TestCase):
    """Tests for is_ollama_available() health check."""

    def test_returns_true_when_ollama_up(self):
        from scraper import ollama_filter as of
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = of.is_ollama_available()

        self.assertTrue(result)

    def test_returns_false_on_connection_error(self):
        from scraper import ollama_filter as of
        import httpx

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value = mock_client

            result = of.is_ollama_available()

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
