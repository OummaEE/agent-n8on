"""
scraper/ollama_filter.py — Локальная LLM-фильтрация через Ollama

Использует Ollama (gemma2:2b по умолчанию) для:
1. Классификации: является ли пост анонсом мероприятия?
2. Извлечения структурированных данных если да:
   - title, date, time, location, description, registration_url

Работает полностью локально, без внешних API.

Конфигурация (.env):
    OLLAMA_URL=http://localhost:11434   (по умолчанию)
    OLLAMA_MODEL=gemma2:2b             (по умолчанию)
    OLLAMA_TIMEOUT=30                  (секунды)
"""

import asyncio
import json
import logging
import re
from typing import Optional

import httpx

from .config import OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_URL

log = logging.getLogger(__name__)

# ── Промпт классификатора ─────────────────────────────────────────────────────
_CLASSIFY_SYSTEM = """You analyze Facebook group posts to find event announcements.
An event must have: a specific future date OR time, AND a place OR registration info.

Respond ONLY with valid JSON, no explanations:
{
  "is_event": true or false,
  "title": "event name (short, 5-10 words)",
  "date": "date as written in post (empty string if missing)",
  "time": "time as written (e.g. 19:00, empty if missing)",
  "location": "venue or address (empty if missing)",
  "description": "1-2 sentence summary",
  "registration_url": "registration/ticket link (empty if missing)"
}

If NOT an event, respond only: {"is_event": false}

Rules:
- Past events → is_event: false
- Vague posts without date → is_event: false
- Concerts, workshops, meetups, exhibitions, courses, seminars = events
- Job posts, lost/found, sales, general questions → NOT events"""


def _build_user_message(post: dict) -> str:
    """Формирует текст запроса для Ollama из данных поста."""
    parts = []
    if post.get("author"):
        parts.append(f"Author: {post['author']}")
    if post.get("timestamp_raw"):
        parts.append(f"Posted: {post['timestamp_raw']}")
    if post.get("text"):
        parts.append(f"Post text:\n{post['text'][:1500]}")
    if post.get("attachment"):
        parts.append(f"Attached: {post['attachment'][:400]}")
    if post.get("ocr_text"):
        parts.append(f"Text from images (OCR):\n{post['ocr_text'][:600]}")
    return "\n".join(parts)


def _parse_ollama_json(raw: str) -> Optional[dict]:
    """Извлекает JSON из ответа модели (устойчиво к markdown-оберткам)."""
    raw = raw.strip()
    # Убираем markdown-блоки ```json ... ```
    raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
    # Ищем первый JSON-объект
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        # Пробуем починить типичную ошибку — trailing comma
        cleaned = re.sub(r",\s*}", "}", match.group())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _call_ollama_sync(user_message: str) -> Optional[dict]:
    """
    Синхронный вызов Ollama API.
    Запускается через executor чтобы не блокировать event loop.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 400,
        },
    }

    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            resp = client.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("message", {}).get("content", "")
            return _parse_ollama_json(raw)

    except httpx.TimeoutException:
        log.warning(f"   Ollama timeout после {OLLAMA_TIMEOUT}s — пропускаю пост")
        return None
    except httpx.HTTPStatusError as e:
        log.warning(f"   Ollama HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        log.debug(f"   Ollama ошибка: {type(e).__name__}: {e}")
        return None


async def classify_post(post: dict) -> Optional[dict]:
    """
    Классифицирует один пост через Ollama.

    Возвращает:
        dict с полями is_event, title, date, time, location,
             description, registration_url — если мероприятие найдено
        None — если не мероприятие или ошибка Ollama
    """
    user_msg = _build_user_message(post)
    if not user_msg.strip():
        return None

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _call_ollama_sync, user_msg)

    if result is None:
        return None

    if not result.get("is_event"):
        return None

    # Добавляем метаданные поста к результату
    result["post_url"]    = post.get("post_url", "")
    result["post_author"] = post.get("author", "")
    result["post_date"]   = post.get("timestamp_raw", "")
    result["group_url"]   = post.get("group_url", "")
    result["image_urls"]  = post.get("image_urls", [])
    result["source"]      = "ollama"

    return result


async def filter_posts_batch(
    posts: list[dict],
    group_name: str = "",
) -> list[dict]:
    """
    Фильтрует список постов через Ollama: оставляет только анонсы мероприятий.

    Параметры:
        posts      — список постов из collect_posts (с ocr_text если был OCR)
        group_name — название группы (для метаданных)

    Возвращает:
        Список структурированных событий с полями:
        is_event, title, date, time, location, description,
        registration_url, post_url, post_author, post_date,
        group_url, image_urls, source="ollama"
    """
    if not posts:
        return []

    events: list[dict] = []
    total = len(posts)
    log.info(f"🤖 Ollama ({OLLAMA_MODEL}): классифицирую {total} постов...")

    for idx, post in enumerate(posts, 1):
        preview = (post.get("text") or "")[:60].replace("\n", " ")
        imgs = len(post.get("image_urls", []))
        log.info(f"   [{idx:02d}/{total}] {preview!r}... [imgs:{imgs}]")

        result = await classify_post(post)

        if result:
            result["group_name"] = group_name
            conf_label = "✅ СОБЫТИЕ"
            title = result.get("title", "—")
            date  = result.get("date", "—")
            log.info(f"          {conf_label} → {title!r} | {date}")
            events.append(result)
        else:
            log.debug(f"          — не мероприятие")

        # Небольшая пауза между запросами (Ollama работает локально, но нагружает CPU)
        await asyncio.sleep(0.2)

    log.info(f"   📊 Ollama нашёл: {len(events)}/{total} постов — мероприятия")
    return events


def is_ollama_available() -> bool:
    """Проверяет доступность Ollama (быстрый HEAD-запрос)."""
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
