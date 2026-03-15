"""
scraper/ocr.py — Локальный OCR для изображений постов Facebook

Использует EasyOCR для извлечения текста из изображений (афиши, флаеры).
Работает полностью локально без обращения к внешним API.

Поддерживаемые языки: шведский, английский, русский.

Использование:
    from scraper.ocr import ocr_images_batch, ocr_image_url

    # Синхронно (для тестов):
    text = ocr_image_url("https://...")

    # В async-контексте:
    texts = await ocr_images_batch(["https://...", "https://..."])
"""

import asyncio
import io
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Языки для OCR: шведский + английский + русский
_OCR_LANGUAGES = ["sv", "en", "ru"]

# Минимальная длина текста, чтобы считать его значимым
_MIN_TEXT_LENGTH = 20

# Таймаут загрузки изображения (сек)
_DOWNLOAD_TIMEOUT = 15


@lru_cache(maxsize=1)
def _get_reader():
    """
    Возвращает (и кеширует) экземпляр EasyOCR Reader.

    Первый вызов занимает ~3–10 секунд (загрузка модели).
    Последующие — мгновенны (lru_cache).
    """
    try:
        import easyocr
        log.info("🔍 Инициализация EasyOCR (первый запуск — загрузка модели)...")
        reader = easyocr.Reader(_OCR_LANGUAGES, gpu=False, verbose=False)
        log.info("✅ EasyOCR готов")
        return reader
    except ImportError:
        log.error("❌ EasyOCR не установлен: pip install easyocr")
        return None
    except Exception as e:
        log.error(f"❌ Ошибка инициализации EasyOCR: {e}")
        return None


def _download_image(url: str) -> Optional[bytes]:
    """Скачивает изображение по URL, возвращает байты или None."""
    try:
        import httpx
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.facebook.com/",
            }
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.content
            log.debug(f"   OCR: HTTP {resp.status_code} для {url[:60]}...")
            return None
    except Exception as e:
        log.debug(f"   OCR: ошибка загрузки изображения: {type(e).__name__}: {e}")
        return None


def ocr_image_bytes(image_bytes: bytes) -> str:
    """
    Извлекает текст из изображения (bytes) с помощью EasyOCR.

    Возвращает строку с извлечённым текстом или пустую строку.
    """
    reader = _get_reader()
    if reader is None:
        return ""

    try:
        # EasyOCR принимает numpy array, PIL Image, путь к файлу или bytes
        results = reader.readtext(image_bytes, detail=0, paragraph=True)
        text = " ".join(str(r).strip() for r in results if str(r).strip())
        return text
    except Exception as e:
        log.debug(f"   OCR: ошибка readtext: {type(e).__name__}: {e}")
        return ""


def ocr_image_url(url: str) -> str:
    """
    Скачивает изображение по URL и извлекает текст.

    Синхронная функция (использовать из async-кода через run_in_executor).
    Возвращает извлечённый текст или пустую строку.
    """
    image_bytes = _download_image(url)
    if not image_bytes:
        return ""

    text = ocr_image_bytes(image_bytes)
    if len(text) >= _MIN_TEXT_LENGTH:
        log.debug(f"   OCR: извлечён текст ({len(text)} симв.) из {url[:60]}...")
    return text


async def ocr_image_url_async(url: str) -> str:
    """
    Асинхронная обёртка над ocr_image_url.
    Запускает синхронный OCR в threadpool executor.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ocr_image_url, url)


async def ocr_images_batch(
    image_urls: list[str],
    max_images: int = 2,
) -> str:
    """
    Запускает OCR для нескольких изображений и возвращает объединённый текст.

    Параметры:
        image_urls — список URL изображений
        max_images — максимум изображений для обработки (по умолчанию 2)

    Возвращает:
        Объединённый текст из всех изображений (разделитель: " | ")
        или пустую строку если текст не найден.
    """
    if not image_urls:
        return ""

    urls_to_process = image_urls[:max_images]
    texts: list[str] = []

    for url in urls_to_process:
        text = await ocr_image_url_async(url)
        if text and len(text) >= _MIN_TEXT_LENGTH:
            texts.append(text.strip())

    combined = " | ".join(texts) if texts else ""
    if combined:
        log.debug(f"   OCR batch: {len(texts)}/{len(urls_to_process)} изображений с текстом")
    return combined


async def enrich_posts_with_ocr(posts: list[dict]) -> list[dict]:
    """
    Добавляет поле 'ocr_text' в каждый пост с изображениями.

    Вызывается после collect_posts() и до analyze_posts_batch().
    Модифицирует посты in-place и возвращает список.

    Пример поля post['ocr_text']:
        "Konsert 15 mars 2025 | Kulturhuset, Stockholm 19:00"
    """
    posts_with_images = [p for p in posts if p.get("image_urls")]
    if not posts_with_images:
        return posts

    log.info(f"🔍 OCR: обрабатываю {len(posts_with_images)} постов с изображениями...")
    ocr_count = 0

    for post in posts_with_images:
        image_urls = post.get("image_urls", [])
        try:
            ocr_text = await ocr_images_batch(image_urls, max_images=2)
        except Exception as e:
            log.debug(f"   OCR: ошибка для поста, пропускаю: {type(e).__name__}: {e}")
            ocr_text = ""
        post["ocr_text"] = ocr_text
        if ocr_text:
            ocr_count += 1
            preview = ocr_text[:80].replace("\n", " ")
            log.info(f"   ✅ OCR нашёл текст: {preview!r}...")

    log.info(f"   OCR завершён: {ocr_count}/{len(posts_with_images)} изображений содержат текст")
    return posts
