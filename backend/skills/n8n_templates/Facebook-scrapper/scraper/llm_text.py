"""
scraper/llm_text.py — LLM-анализ текстового содержимого постов

Отвечает за:
- Создание OpenAI-совместимого клиента (читает ~/.genspark_llm.yaml или .env)
- Системный промпт для извлечения мероприятий
- analyze_post_text(): анализирует один пост, возвращает dict или None
- analyze_posts_batch(): последовательно обрабатывает список постов
"""

import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Optional

import yaml
from openai import AsyncOpenAI
import openai as _openai

from .config import LLM_MAX_RETRIES, LLM_MODEL

log = logging.getLogger(__name__)

# ── Системный промпт ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Du är en assistent som analyserar inlägg från Facebook-grupper för att hitta kommande evenemang.
Du förstår svenska, engelska, och ryska. Du är bra på att tolka informellt och kaotiskt skrivet innehåll.

Din uppgift: avgör om inlägget är ett KOMMANDE EVENEMANG (konsert, utställning, marknad, kurs, träff, föreläsning, loppis, festival, turnering, etc.)

REGLER:
- Analysera mening, inte bara nyckelord — folk skriver informellt.
- Ignorera inlägg om FÖRFLUTNA evenemang (om det inte finns ett nytt datum).
- Ignorera vaga annonser utan datum ("kom och besök oss").
- Om ett SPECIFIKT framtida datum eller tidsperiod nämns → det är ett evenemang.

Om evenemang hittas, svara BARA med giltig JSON (ingen markdown, ingen förklaring):
{
  "is_event": true,
  "title": "Evenemangets namn (kort, hitta på om det saknas)",
  "date_raw": "datum/tid som skrivet i inlägget (tom sträng om saknas)",
  "location": "plats (tom sträng om saknas)",
  "description": "kort beskrivning 1-2 meningar",
  "event_type": "konsert | utställning | möte | webinar | festival | kurs | marknad | sport | loppis | annan",
  "contact": "kontakt/länk för anmälan (tom sträng om saknas)",
  "confidence": 0.0-1.0,
  "source": "text"
}

Om INGET evenemang finns, svara bara: {"is_event": false}"""


def build_llm_client() -> AsyncOpenAI:
    """
    Создаёт асинхронный OpenAI-совместимый клиент.

    Порядок приоритетов:
      1. ~/.genspark_llm.yaml (GenSpark sandbox)
      2. OPENAI_API_KEY / OPENAI_BASE_URL из .env / env vars
    """
    api_key = ""
    base_url = ""

    yaml_path = Path.home() / ".genspark_llm.yaml"
    if yaml_path.exists():
        try:
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f) or {}
            api_key = cfg.get("openai", {}).get("api_key", "")
            base_url = cfg.get("openai", {}).get("base_url", "")
        except Exception as e:
            log.debug(f"YAML read error: {e}")

    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "")

    if not api_key:
        raise ValueError(
            "❌ OPENAI_API_KEY не найден!\n"
            "   Укажите в .env или настройте ~/.genspark_llm.yaml"
        )

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)


async def _llm_call_with_retry(coro_fn, max_retries: int = LLM_MAX_RETRIES):
    """
    Выполняет async вызов к LLM с экспоненциальным backoff.

    Повторяет при:
    - RateLimitError     → 30s, 60s, 90s (квота API)
    - APITimeoutError    → 5s, 10s, 15s
    - APIConnectionError → 5s, 10s, 15s
    - APIStatusError 5xx → 10s, 20s, 30s (сервер перегружен)

    При исчерпании попыток возвращает None (не бросает исключение).
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_fn()

        except _openai.RateLimitError:
            wait = 30.0 * attempt
            if attempt < max_retries:
                log.warning(
                    f"⏳ Rate limit — ожидаю {wait:.0f}s "
                    f"(попытка {attempt}/{max_retries})"
                )
                await asyncio.sleep(wait)
            else:
                log.error("❌ Rate limit — попытки исчерпаны")
                return None

        except (_openai.APITimeoutError, _openai.APIConnectionError) as e:
            wait = 5.0 * attempt
            if attempt < max_retries:
                log.warning(
                    f"⏳ {type(e).__name__} — retry {attempt}/{max_retries} "
                    f"через {wait:.0f}s"
                )
                await asyncio.sleep(wait)
            else:
                log.error(f"❌ {type(e).__name__} — попытки исчерпаны: {e}")
                return None

        except _openai.APIStatusError as e:
            if e.status_code in (500, 502, 503, 529):
                wait = 10.0 * attempt
                if attempt < max_retries:
                    log.warning(
                        f"⏳ HTTP {e.status_code} — retry {attempt}/{max_retries} "
                        f"через {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    log.error(f"❌ HTTP {e.status_code} — попытки исчерпаны")
                    return None
            else:
                # 4xx (400, 401, 403) — не retry, сразу ошибка
                log.error(f"❌ API error {e.status_code}: {e.message}")
                return None

    return None


def _parse_llm_json(raw: str) -> Optional[dict]:
    """Надёжно извлекает JSON из ответа LLM (с fallback на поиск по регулярке)."""
    raw = raw.strip()
    # Убираем markdown-блоки ```json ... ```
    raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


async def analyze_post_text(
    client: AsyncOpenAI,
    post: dict,
    group_name: str = "",
) -> Optional[dict]:
    """
    Анализирует текст одного поста через LLM.

    Возвращает структурированный словарь с данными о мероприятии
    (source='text') или None.
    """
    text = post.get("text", "").strip()
    attachment = post.get("attachment", "").strip()
    author = post.get("author", "")
    timestamp = post.get("timestamp_raw", "")

    if not text:
        return None

    user_content = (
        f"GRUPP: {group_name}\n"
        f"AUTHOR: {author}\n"
        f"PUBLICERAT: {timestamp}\n\n"
        f"INLÄGG:\n{text}"
    )
    if attachment:
        user_content += f"\n\nBILAGT INNEHÅLL:\n{attachment[:400]}"

    ocr_text = post.get("ocr_text", "").strip()
    if ocr_text:
        user_content += f"\n\nOCR-TEXT FRÅN BILDER:\n{ocr_text[:600]}"

    async def _call():
        return await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.1,
            max_tokens=450,
            timeout=30.0,
        )

    try:
        resp = await _llm_call_with_retry(_call)
        if resp is None:
            return None

        raw = resp.choices[0].message.content or ""
        result = _parse_llm_json(raw)

        if not result or not result.get("is_event"):
            return None

        result["source"]      = "text"
        result["post_url"]    = post.get("post_url", "")
        result["post_author"] = author
        result["post_date"]   = timestamp
        result["group_url"]   = post.get("group_url", "")
        result["group_name"]  = group_name
        result["image_urls"]  = ";".join(post.get("image_urls", []))

        return result

    except Exception as e:
        log.warning(f"⚠️  Ошибка LLM text (неожиданная): {type(e).__name__}: {e}")
        return None


async def analyze_posts_batch(
    client: AsyncOpenAI,
    posts: list[dict],
    group_name: str = "",
) -> tuple[list[dict], list[dict]]:
    """
    Последовательно анализирует список постов через LLM (текст).

    Возвращает:
        (events, no_event_posts_with_images)
        - events                    — найденные мероприятия
        - no_event_posts_with_images — посты без события, но с картинками
                                       (кандидаты на vision-анализ)
    """
    events: list[dict] = []
    vision_candidates: list[dict] = []
    total = len(posts)

    log.info(f"🤖 LLM text-анализ: {total} постов...")

    for idx, post in enumerate(posts, 1):
        preview = post.get("text", "")[:55].replace("\n", " ")
        imgs_count = len(post.get("image_urls", []))
        log.info(f"   [{idx:02d}/{total}] {preview!r}... [imgs:{imgs_count}]")

        result = await analyze_post_text(client, post, group_name)

        if result:
            conf = result.get("confidence", 0)
            title = result.get("title", "Без названия")
            log.info(f"          ✅ СОБЫТИЕ [{conf:.0%}] → {title}")
            events.append(result)
        else:
            # Если нет события, но есть картинки — кандидат для vision
            if post.get("image_urls"):
                vision_candidates.append(post)
                log.debug(f"          🖼  Кандидат для vision ({imgs_count} изображений)")

        # Пауза между LLM-вызовами (защита от rate limit)
        await asyncio.sleep(random.uniform(0.5, 1.8))

    log.info(
        f"   📊 Итого: событий={len(events)}, "
        f"vision-кандидатов={len(vision_candidates)}"
    )
    return events, vision_candidates
