"""
scraper/llm_vision.py — Vision-анализ изображений постов (qwen2.5vl)

Логика:
    Вызывается ТОЛЬКО для постов, где:
    1. LLM-текст не нашёл событие (is_event=false)
    2. Пост содержит хотя бы одно изображение

    Это экономит compute и деньги:
    vision вызывается только там, где нужен — на афишах/флаерах без текста.

    На каждый пост анализируем максимум MAX_VISION_IMAGES_PER_POST (2) изображений
    и возвращаем первый уверенный результат.

Используемая модель:
    qwen2.5vl — мультимодальная, хорошо читает афиши с текстом
    (шведским, английским, кириллицей)
"""

import asyncio
import json
import logging
import random
import re
from typing import Optional

import openai as _openai
from openai import AsyncOpenAI

from .config import LLM_MAX_RETRIES, MAX_VISION_IMAGES_PER_POST, VISION_MODEL

log = logging.getLogger(__name__)

# ── Vision-промпт ────────────────────────────────────────────────────────────
VISION_SYSTEM_PROMPT = """You are an assistant analyzing images from Facebook group posts.
Your task: determine if the image is an announcement/flyer for an UPCOMING EVENT.

Look for: dates, times, venue names, event titles, ticket info, registration links.
The image may contain text in Swedish, English, Russian, or other languages.

If you find an event, respond ONLY with valid JSON (no markdown):
{
  "is_event": true,
  "title": "event title (extract from image or infer)",
  "date_raw": "date/time as written in image (empty string if not found)",
  "location": "venue/location (empty string if not found)",
  "description": "brief 1-2 sentence description",
  "event_type": "concert | exhibition | meeting | webinar | festival | course | market | sport | flea_market | other",
  "contact": "contact/link for registration (empty string if not found)",
  "confidence": 0.0-1.0,
  "source": "vision"
}

If NO event found, respond only: {"is_event": false}"""


async def _vision_call_with_retry(coro_fn, max_retries: int = LLM_MAX_RETRIES):
    """Экспоненциальный backoff для vision API вызовов (аналог llm_text._llm_call_with_retry)."""
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_fn()

        except _openai.RateLimitError:
            wait = 45.0 * attempt  # Vision дороже — ждём дольше
            if attempt < max_retries:
                log.warning(
                    f"⏳ Vision rate limit — ожидаю {wait:.0f}s "
                    f"(попытка {attempt}/{max_retries})"
                )
                await asyncio.sleep(wait)
            else:
                log.error("❌ Vision rate limit — попытки исчерпаны")
                return None

        except (_openai.APITimeoutError, _openai.APIConnectionError) as e:
            wait = 8.0 * attempt
            if attempt < max_retries:
                log.warning(f"⏳ Vision {type(e).__name__} — retry {attempt}/{max_retries} через {wait:.0f}s")
                await asyncio.sleep(wait)
            else:
                log.error(f"❌ Vision {type(e).__name__} — попытки исчерпаны")
                return None

        except _openai.APIStatusError as e:
            if e.status_code in (500, 502, 503, 529):
                wait = 15.0 * attempt
                if attempt < max_retries:
                    log.warning(f"⏳ Vision HTTP {e.status_code} — retry {attempt}/{max_retries} через {wait:.0f}s")
                    await asyncio.sleep(wait)
                else:
                    log.error(f"❌ Vision HTTP {e.status_code} — попытки исчерпаны")
                    return None
            else:
                log.error(f"❌ Vision API error {e.status_code}")
                return None

    return None


def _parse_vision_json(raw: str) -> Optional[dict]:
    """Надёжно извлекает JSON из ответа vision-модели."""
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


async def analyze_image(
    client: AsyncOpenAI,
    image_url: str,
    post: dict,
    group_name: str = "",
) -> Optional[dict]:
    """
    Анализирует одно изображение через vision-модель.

    Параметры:
        client    — AsyncOpenAI клиент
        image_url — URL изображения
        post      — оригинальный пост (для метаданных)
        group_name — название группы

    Возвращает:
        dict с данными о мероприятии (source='vision') или None
    """
    async def _call():
        return await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Group: {group_name}\n"
                                f"Post text (may be empty): {post.get('text', '')[:200]}\n\n"
                                "Analyze this image for event information:"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=45.0,
        )

    try:
        resp = await _vision_call_with_retry(_call)
        if resp is None:
            return None

        raw = resp.choices[0].message.content or ""
        result = _parse_vision_json(raw)

        if not result or not result.get("is_event"):
            return None

        result["source"]      = "vision"
        result["post_url"]    = post.get("post_url", "")
        result["post_author"] = post.get("author", "")
        result["post_date"]   = post.get("timestamp_raw", "")
        result["group_url"]   = post.get("group_url", "")
        result["group_name"]  = group_name
        result["image_urls"]  = ";".join(post.get("image_urls", []))

        return result

    except Exception as e:
        log.warning(f"   ⚠️  Vision ошибка ({image_url[:50]}...): {type(e).__name__}: {e}")
        return None


async def analyze_vision_candidates(
    client: AsyncOpenAI,
    candidates: list[dict],
    group_name: str = "",
    confidence_threshold: float = 0.6,
) -> list[dict]:
    """
    Запускает vision-анализ для постов-кандидатов.

    Кандидаты — это посты, где:
    - LLM-текст не нашёл событие
    - Есть хотя бы одно изображение

    Для каждого кандидата анализируем максимум MAX_VISION_IMAGES_PER_POST (2)
    изображений и возвращаем первый уверенный результат.
    Пауза между запросами 1–3 сек (vision-модели медленнее text).

    Параметры:
        candidates           — список постов из llm_text.analyze_posts_batch
        confidence_threshold — минимальная уверенность для включения в результат

    Возвращает:
        список найденных мероприятий с source='vision'
    """
    if not candidates:
        return []

    events: list[dict] = []
    total = len(candidates)
    log.info(f"🖼️  Vision-анализ: {total} кандидатов (макс. {MAX_VISION_IMAGES_PER_POST} изобр./пост)...")

    for idx, post in enumerate(candidates, 1):
        image_urls = post.get("image_urls", [])
        if not image_urls:
            continue

        # Анализируем максимум MAX_VISION_IMAGES_PER_POST изображений на пост
        images_to_check = image_urls[:MAX_VISION_IMAGES_PER_POST]
        found_event: Optional[dict] = None

        for img_idx, img_url in enumerate(images_to_check, 1):
            log.info(
                f"   [{idx:02d}/{total}] Vision img {img_idx}/{len(images_to_check)}: "
                f"{img_url[:60]}..."
            )

            result = await analyze_image(client, img_url, post, group_name)

            if result:
                conf = result.get("confidence", 0)
                title = result.get("title", "—")
                if conf >= confidence_threshold:
                    log.info(f"          ✅ VISION СОБЫТИЕ [{conf:.0%}] → {title}")
                    found_event = result
                    break  # Нашли уверенный результат — не смотрим другие картинки
                else:
                    log.info(
                        f"          ⚠️  Vision нашёл событие, но уверенность низкая "
                        f"[{conf:.0%} < {confidence_threshold:.0%}] → пробуем следующее фото"
                    )
            else:
                log.debug(f"          — Vision: не мероприятие")

            # Пауза между vision-запросами (они дороже и медленнее)
            if img_idx < len(images_to_check):
                await asyncio.sleep(random.uniform(1.0, 3.0))

        if found_event:
            events.append(found_event)

        # Пауза между постами
        await asyncio.sleep(random.uniform(1.0, 3.0))

    log.info(f"   🎯 Vision нашёл: {len(events)} событий из {total} кандидатов")
    return events

