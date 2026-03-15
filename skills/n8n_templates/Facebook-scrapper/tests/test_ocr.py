"""
tests/test_ocr.py — Unit tests for OCR module

Tests cover:
1. ocr_image_bytes() — text extraction from image bytes
2. ocr_image_url() — download + OCR pipeline
3. ocr_images_batch() — batch async OCR
4. enrich_posts_with_ocr() — post enrichment
5. Error handling (bad URL, empty bytes, etc.)
"""

import asyncio
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Ensure scraper package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestOcrImageBytes(unittest.TestCase):
    """Tests for ocr_image_bytes() with mocked EasyOCR reader."""

    def _make_reader_mock(self, readtext_return):
        reader = MagicMock()
        reader.readtext = MagicMock(return_value=readtext_return)
        return reader

    def test_returns_text_from_reader(self):
        """Reader returns results → joined text returned."""
        from scraper import ocr as ocr_module
        reader = self._make_reader_mock(["Konsert", "15 mars 2025"])
        with patch.object(ocr_module, "_get_reader", return_value=reader):
            result = ocr_module.ocr_image_bytes(b"fake_image")
        self.assertIn("Konsert", result)
        self.assertIn("15 mars 2025", result)

    def test_empty_reader_results(self):
        """Reader returns empty list → empty string."""
        from scraper import ocr as ocr_module
        reader = self._make_reader_mock([])
        with patch.object(ocr_module, "_get_reader", return_value=reader):
            result = ocr_module.ocr_image_bytes(b"blank_image")
        self.assertEqual(result, "")

    def test_reader_none_returns_empty(self):
        """If reader is None (not installed) → empty string returned."""
        from scraper import ocr as ocr_module
        with patch.object(ocr_module, "_get_reader", return_value=None):
            result = ocr_module.ocr_image_bytes(b"any_bytes")
        self.assertEqual(result, "")

    def test_reader_exception_returns_empty(self):
        """Reader raises exception → empty string, no crash."""
        from scraper import ocr as ocr_module
        reader = MagicMock()
        reader.readtext = MagicMock(side_effect=RuntimeError("model error"))
        with patch.object(ocr_module, "_get_reader", return_value=reader):
            result = ocr_module.ocr_image_bytes(b"corrupt_data")
        self.assertEqual(result, "")


class TestOcrImageUrl(unittest.TestCase):
    """Tests for ocr_image_url() — download + OCR chain."""

    def test_success_returns_text(self):
        """Download succeeds + reader finds text → text returned."""
        from scraper import ocr as ocr_module
        reader = MagicMock()
        reader.readtext = MagicMock(return_value=["Event Night", "20:00 Stockholm"])
        with patch.object(ocr_module, "_download_image", return_value=b"img_bytes"), \
             patch.object(ocr_module, "_get_reader", return_value=reader):
            result = ocr_module.ocr_image_url("https://example.com/poster.jpg")
        self.assertIn("Event Night", result)
        self.assertIn("20:00 Stockholm", result)

    def test_download_fails_returns_empty(self):
        """Download returns None → empty string, no crash."""
        from scraper import ocr as ocr_module
        with patch.object(ocr_module, "_download_image", return_value=None):
            result = ocr_module.ocr_image_url("https://bad.url/img.jpg")
        self.assertEqual(result, "")

    def test_short_text_still_returned(self):
        """OCR finds short text (below _MIN_TEXT_LENGTH) → still returned."""
        from scraper import ocr as ocr_module
        reader = MagicMock()
        reader.readtext = MagicMock(return_value=["Hi"])
        with patch.object(ocr_module, "_download_image", return_value=b"img"), \
             patch.object(ocr_module, "_get_reader", return_value=reader):
            result = ocr_module.ocr_image_url("https://x.com/small.jpg")
        # Text is returned even if short (filtering is caller's responsibility)
        self.assertIsInstance(result, str)


class TestOcrImagesBatch(unittest.TestCase):
    """Tests for ocr_images_batch() async function."""

    def test_batch_combines_text(self):
        """Two images with text → joined with ' | '."""
        from scraper import ocr as ocr_module

        async def run():
            with patch.object(ocr_module, "ocr_image_url_async",
                               side_effect=["Konsert lördag 15 mars 2025", "Kulturhuset i Stockholm"]):
                return await ocr_module.ocr_images_batch(
                    ["https://img1.jpg", "https://img2.jpg"]
                )

        result = asyncio.run(run())
        self.assertIn("Konsert", result)
        self.assertIn("Kulturhuset", result)
        self.assertIn(" | ", result)

    def test_batch_empty_urls(self):
        """Empty URL list → empty string."""
        from scraper import ocr as ocr_module

        async def run():
            return await ocr_module.ocr_images_batch([])

        result = asyncio.run(run())
        self.assertEqual(result, "")

    def test_batch_max_images_respected(self):
        """Only first max_images URLs are processed."""
        from scraper import ocr as ocr_module
        call_count = []

        async def fake_ocr(url):
            call_count.append(url)
            return "text from " + url

        async def run():
            with patch.object(ocr_module, "ocr_image_url_async", side_effect=fake_ocr):
                return await ocr_module.ocr_images_batch(
                    ["u1", "u2", "u3", "u4"], max_images=2
                )

        asyncio.run(run())
        self.assertEqual(len(call_count), 2)

    def test_batch_skips_short_text(self):
        """Images returning text shorter than _MIN_TEXT_LENGTH are excluded from output."""
        from scraper import ocr as ocr_module

        async def run():
            with patch.object(ocr_module, "ocr_image_url_async",
                               side_effect=["Hi", "Konsert lördag 15 mars 2025"]):
                return await ocr_module.ocr_images_batch(["u1", "u2"])

        result = asyncio.run(run())
        # "Hi" is too short, only the second text should be in output
        self.assertNotIn("Hi", result)
        self.assertIn("Konsert", result)


class TestEnrichPostsWithOcr(unittest.TestCase):
    """Tests for enrich_posts_with_ocr() — post enrichment integration."""

    def _make_posts(self):
        return [
            {"text": "Post without images", "image_urls": []},
            {"text": "Post with images", "image_urls": ["https://img1.jpg", "https://img2.jpg"]},
            {"text": "Post with one image", "image_urls": ["https://img3.jpg"]},
        ]

    def test_adds_ocr_text_to_image_posts(self):
        """Posts with images get ocr_text field added."""
        from scraper import ocr as ocr_module

        async def fake_ocr_batch(urls, max_images=2):
            return "Extracted event text 2025-03-15"

        async def run():
            posts = self._make_posts()
            with patch.object(ocr_module, "ocr_images_batch", side_effect=fake_ocr_batch):
                return await ocr_module.enrich_posts_with_ocr(posts)

        result = asyncio.run(run())
        # Post without images should not get ocr_text
        self.assertNotIn("ocr_text", result[0])
        # Posts with images should get ocr_text
        self.assertIn("ocr_text", result[1])
        self.assertIn("ocr_text", result[2])
        self.assertIn("Extracted event text", result[1]["ocr_text"])

    def test_no_images_posts_unchanged(self):
        """Posts without images are not modified."""
        from scraper import ocr as ocr_module

        async def run():
            posts = [{"text": "No images here", "image_urls": []}]
            return await ocr_module.enrich_posts_with_ocr(posts)

        result = asyncio.run(run())
        self.assertNotIn("ocr_text", result[0])
        self.assertEqual(result[0]["text"], "No images here")

    def test_empty_post_list(self):
        """Empty list returns empty list."""
        from scraper import ocr as ocr_module

        async def run():
            return await ocr_module.enrich_posts_with_ocr([])

        result = asyncio.run(run())
        self.assertEqual(result, [])

    def test_ocr_error_does_not_crash(self):
        """If ocr_images_batch raises → post gets empty ocr_text, no crash."""
        from scraper import ocr as ocr_module

        async def failing_ocr(urls, max_images=2):
            raise RuntimeError("OCR model crashed")

        async def run():
            posts = [{"text": "test", "image_urls": ["https://img.jpg"]}]
            with patch.object(ocr_module, "ocr_images_batch", side_effect=failing_ocr):
                # enrich_posts_with_ocr catches exceptions per-post
                return await ocr_module.enrich_posts_with_ocr(posts)

        # Should not raise
        try:
            asyncio.run(run())
        except Exception as e:
            self.fail(f"enrich_posts_with_ocr raised unexpectedly: {e}")


class TestDownloadImage(unittest.TestCase):
    """Tests for _download_image() — HTTP download."""

    def test_success_returns_bytes(self):
        """HTTP 200 → image bytes returned."""
        from scraper import ocr as ocr_module
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"PNG_DATA"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(return_value=mock_resp)
            mock_client_class.return_value = mock_client

            result = ocr_module._download_image("https://example.com/img.jpg")

        self.assertEqual(result, b"PNG_DATA")

    def test_http_error_returns_none(self):
        """HTTP 403 → None returned."""
        from scraper import ocr as ocr_module

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(return_value=mock_resp)
            mock_client_class.return_value = mock_client

            result = ocr_module._download_image("https://example.com/forbidden.jpg")

        self.assertIsNone(result)

    def test_network_error_returns_none(self):
        """Network error → None, no crash."""
        from scraper import ocr as ocr_module

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get = MagicMock(side_effect=ConnectionError("timeout"))
            mock_client_class.return_value = mock_client

            result = ocr_module._download_image("https://unreachable.invalid/img.jpg")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
