"""
scraper/supabase_client.py — Supabase integration

Отвечает за:
- Lazy-инициализацию Supabase клиента (только если SUPABASE_URL + SUPABASE_KEY заданы)
- Batch upsert событий в таблицу raw_posts (ON CONFLICT source_hash DO UPDATE)
- Graceful degradation: если Supabase не настроен — молча пропускает, CSV остаётся основным хранилищем

Используемая таблица: см. sql/init.sql
"""

import asyncio
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Кэш клиента — создаётся один раз
_sb_client = None


def _get_client():
    """Lazy-инициализация Supabase клиента. Возвращает None если не настроен."""
    global _sb_client
    if _sb_client is not None:
        return _sb_client

    from .config import SUPABASE_KEY, SUPABASE_URL

    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        from supabase import create_client  # type: ignore[import]
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("✅ Supabase клиент инициализирован")
    except ImportError:
        log.warning(
            "⚠️  Supabase SDK не установлен. "
            "Установите: pip install supabase"
        )
    except Exception as e:
        log.warning(f"⚠️  Не удалось инициализировать Supabase: {e}")

    return _sb_client


def _event_to_row(event: dict) -> dict:
    """Преобразует словарь события в строку для Supabase raw_posts."""
    # Убираем внутренние служебные поля перед сохранением в raw_json
    clean = {k: v for k, v in event.items() if not k.startswith("_")}

    return {
        "source_hash":     event.get("source_hash") or "",
        "post_url":        event.get("post_url") or None,
        "group_url":       event.get("group_url") or None,
        "group_name":      event.get("group_name") or None,
        "title":           event.get("title") or None,
        "event_type":      event.get("event_type") or None,
        "date_raw":        event.get("date_raw") or None,
        "date_normalized": event.get("date_normalized") or None,
        "location":        event.get("location") or None,
        "description":     event.get("description") or None,
        "contact":         event.get("contact") or None,
        "confidence":      event.get("confidence"),
        "source":          event.get("source") or "text",
        "post_author":     event.get("post_author") or None,
        "post_date":       event.get("post_date") or None,
        "image_urls":      event.get("image_urls") or None,
        "scraped_at":      event.get("scraped_at") or None,
        "raw_json":        json.dumps(clean, ensure_ascii=False),
    }


def _upsert_batch_sync(
    events: list[dict],
    table: str,
) -> tuple[int, str]:
    """
    Синхронный batch upsert в Supabase.
    Возвращает (кол-во строк, сообщение об ошибке или "").
    Вызывается через asyncio.to_thread — не блокирует event loop.
    """
    client = _get_client()
    if client is None:
        return 0, "Supabase не настроен (SUPABASE_URL/SUPABASE_KEY пусты)"

    rows = [_event_to_row(ev) for ev in events]

    # Отфильтровываем строки без source_hash (не должно быть, но на всякий случай)
    rows = [r for r in rows if r.get("source_hash")]

    if not rows:
        return 0, "Нет строк с source_hash для upsert"

    try:
        result = (
            client.table(table)
            .upsert(rows, on_conflict="source_hash")
            .execute()
        )
        count = len(result.data) if result.data else len(rows)
        return count, ""
    except Exception as e:
        return 0, str(e)


async def upsert_events(
    events: list[dict],
    table: Optional[str] = None,
) -> int:
    """
    Async wrapper для batch upsert событий в Supabase.

    ON CONFLICT source_hash DO UPDATE — повторные запуски безопасны.
    Если Supabase не настроен — логирует и возвращает 0 (не ошибка).

    Возвращает количество upserted строк.
    """
    if not events:
        return 0

    from .config import SUPABASE_TABLE
    tbl = table or SUPABASE_TABLE

    count, err = await asyncio.to_thread(_upsert_batch_sync, events, tbl)

    if err:
        if "не настроен" in err:
            log.debug(f"ℹ️  Supabase пропущен: {err}")
        else:
            log.warning(f"⚠️  Supabase upsert ошибка: {err}")
        return 0

    log.info(f"☁️  Supabase: upserted {count} строк → таблица '{tbl}'")
    return count


def is_configured() -> bool:
    """Проверяет, настроен ли Supabase (быстрая проверка без создания клиента)."""
    from .config import SUPABASE_KEY, SUPABASE_URL
    return bool(SUPABASE_URL and SUPABASE_KEY)
