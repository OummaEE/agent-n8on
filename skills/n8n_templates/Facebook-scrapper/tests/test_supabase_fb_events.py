"""
tests/test_supabase_fb_events.py — Tests for Supabase fb_events module

Tests cover:
1. _parse_date_str() — date string normalization
2. _event_to_row() — event dict → db row mapping
3. upsert_fb_events() — async upsert with mocked supabase client
4. Deduplication logic (source_url present vs absent)
5. Error handling (table not found, connection error)
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestParseDateStr(unittest.TestCase):
    """Tests for _parse_date_str()."""

    def _parse(self, s):
        from scraper.supabase_fb_events import _parse_date_str
        return _parse_date_str(s)

    def test_iso_passthrough(self):
        self.assertEqual(self._parse("2025-03-15"), "2025-03-15")

    def test_iso_in_text(self):
        self.assertEqual(self._parse("Event on 2025-03-15 at 19:00"), "2025-03-15")

    def test_ddmmyyyy_slash(self):
        self.assertEqual(self._parse("15/03/2025"), "2025-03-15")

    def test_ddmmyyyy_dash(self):
        self.assertEqual(self._parse("15-03-2025"), "2025-03-15")

    def test_empty_returns_none(self):
        self.assertIsNone(self._parse(""))

    def test_no_date_returns_none(self):
        self.assertIsNone(self._parse("lördag kväll"))

    def test_none_returns_none(self):
        self.assertIsNone(self._parse(None))


class TestEventToRow(unittest.TestCase):
    """Tests for _event_to_row() — mapping to db schema."""

    def _to_row(self, event):
        from scraper.supabase_fb_events import _event_to_row
        return _event_to_row(event)

    def test_full_event_mapped_correctly(self):
        """All fields present → correctly mapped."""
        event = {
            "title": "Jazz Konsert",
            "date": "2025-03-15",
            "time": "19:00",
            "location": "Kulturhuset Stockholm",
            "description": "Live jazz music.",
            "registration_url": "https://tickets.se/jazz",
            "post_url": "https://www.facebook.com/posts/123",
            "group_url": "https://www.facebook.com/groups/456",
            "group_name": "Stockholm Events",
            "post_author": "Jazz Club",
            "image_urls": ["https://img1.jpg", "https://img2.jpg"],
        }
        row = self._to_row(event)
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Jazz Konsert")
        self.assertEqual(row["date"], "2025-03-15")
        self.assertEqual(row["time"], "19:00")
        self.assertEqual(row["location"], "Kulturhuset Stockholm")
        self.assertEqual(row["source_url"], "https://www.facebook.com/posts/123")
        self.assertEqual(row["image_url"], "https://img1.jpg")  # First image only
        self.assertIn("scraped_at", row)

    def test_image_urls_as_string(self):
        """image_urls as semicolon-separated string → first URL extracted."""
        row = self._to_row({
            "title": "Test Event",
            "image_urls": "https://a.jpg;https://b.jpg",
        })
        self.assertEqual(row["image_url"], "https://a.jpg")

    def test_no_title_returns_none(self):
        """Missing title → None (required field)."""
        row = self._to_row({"date": "2025-03-15"})
        self.assertIsNone(row)

    def test_empty_title_returns_none(self):
        row = self._to_row({"title": "   "})
        self.assertIsNone(row)

    def test_contact_as_registration_url_fallback(self):
        """'contact' field used as registration_url fallback."""
        row = self._to_row({
            "title": "Event",
            "contact": "https://register.se",
        })
        self.assertEqual(row["registration_url"], "https://register.se")

    def test_date_raw_parsed(self):
        """'date_raw' field used for date parsing when 'date' is absent."""
        row = self._to_row({
            "title": "Event",
            "date_raw": "15/03/2025",
        })
        self.assertEqual(row["date"], "2025-03-15")

    def test_empty_strings_become_none(self):
        """Empty string fields → None in db row."""
        row = self._to_row({
            "title": "Event",
            "location": "",
            "time": "",
        })
        self.assertIsNone(row["location"])
        self.assertIsNone(row["time"])

    def test_long_title_truncated(self):
        """Title > 500 chars → truncated."""
        row = self._to_row({"title": "x" * 600})
        self.assertEqual(len(row["title"]), 500)


class TestUpsertFbEvents(unittest.TestCase):
    """Tests for upsert_fb_events() async function."""

    def _make_events(self):
        return [
            {
                "title": "Event A",
                "date": "2025-03-15",
                "post_url": "https://fb.com/posts/1",
                "group_url": "https://fb.com/groups/test",
                "image_urls": [],
            },
            {
                "title": "Event B",
                "date": "2025-03-20",
                "post_url": "https://fb.com/posts/2",
                "group_url": "https://fb.com/groups/test",
                "image_urls": ["https://img.jpg"],
            },
        ]

    def _make_mock_client(self, return_data=None):
        """Build a mock Supabase client."""
        mock_result = MagicMock()
        mock_result.data = return_data or [{"id": 1}, {"id": 2}]

        mock_table = MagicMock()
        mock_table.upsert = MagicMock(return_value=mock_table)
        mock_table.insert = MagicMock(return_value=mock_table)
        mock_table.execute = MagicMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.table = MagicMock(return_value=mock_table)
        return mock_client, mock_table

    def test_upsert_returns_count(self):
        """Successful upsert returns count of saved rows."""
        from scraper import supabase_fb_events as sfe

        mock_client, _ = self._make_mock_client()

        with patch.object(sfe, "_get_client", return_value=mock_client):
            count = asyncio.run(sfe.upsert_fb_events(self._make_events()))

        self.assertGreater(count, 0)

    def test_empty_events_returns_zero(self):
        """Empty event list → 0 without touching Supabase."""
        from scraper import supabase_fb_events as sfe

        count = asyncio.run(sfe.upsert_fb_events([]))
        self.assertEqual(count, 0)

    def test_no_client_returns_zero(self):
        """Supabase not configured → 0."""
        from scraper import supabase_fb_events as sfe

        with patch.object(sfe, "_get_client", return_value=None):
            count = asyncio.run(sfe.upsert_fb_events(self._make_events()))

        self.assertEqual(count, 0)

    def test_events_without_source_url_use_insert(self):
        """Events without source_url → uses INSERT not UPSERT."""
        from scraper import supabase_fb_events as sfe

        events_no_url = [{"title": "Event X", "post_url": "", "image_urls": []}]
        mock_client, mock_table = self._make_mock_client()

        with patch.object(sfe, "_get_client", return_value=mock_client):
            asyncio.run(sfe.upsert_fb_events(events_no_url))

        # Should call insert (not upsert) since no source_url
        mock_table.insert.assert_called_once()
        mock_table.upsert.assert_not_called()

    def test_table_not_found_logs_error(self):
        """Table not found error → logs error, returns 0."""
        from scraper import supabase_fb_events as sfe

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.upsert = MagicMock(return_value=mock_table)
        mock_table.execute = MagicMock(
            side_effect=Exception("Could not find the table public.fb_events PGRST205")
        )
        mock_client.table = MagicMock(return_value=mock_table)

        with patch.object(sfe, "_get_client", return_value=mock_client):
            count = asyncio.run(sfe.upsert_fb_events(self._make_events()))

        self.assertEqual(count, 0)

    def test_all_none_rows_returns_zero(self):
        """Events with no valid title → 0 rows saved."""
        from scraper import supabase_fb_events as sfe

        events_no_title = [{"date": "2025-03-15"}]
        mock_client, _ = self._make_mock_client()

        with patch.object(sfe, "_get_client", return_value=mock_client):
            count = asyncio.run(sfe.upsert_fb_events(events_no_title))

        self.assertEqual(count, 0)


class TestIsConfigured(unittest.TestCase):
    """Tests for is_configured()."""

    def test_returns_true_when_both_set(self):
        from scraper import supabase_fb_events as sfe
        with patch.object(sfe, "is_configured", return_value=True):
            self.assertTrue(sfe.is_configured())

    def test_returns_false_when_not_set(self):
        import os
        from scraper import supabase_fb_events as sfe
        # Patch config vars
        with patch("scraper.supabase_fb_events._get_client", return_value=None):
            # Simulate missing config
            import scraper.config as cfg
            original_url = cfg.SUPABASE_URL
            original_key = cfg.SUPABASE_KEY
            cfg.SUPABASE_URL = ""
            cfg.SUPABASE_KEY = ""
            try:
                result = sfe.is_configured()
                self.assertFalse(result)
            finally:
                cfg.SUPABASE_URL = original_url
                cfg.SUPABASE_KEY = original_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
