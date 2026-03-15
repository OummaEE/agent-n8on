"""
scraper/supabase_fb_events.py — Сохранение событий из Facebook в таблицу fb_events

Отдельная таблица fb_events, не связанная с основной events-таблицей.
Дедупликация по source_url (UNIQUE constraint).

Схема таблицы: sql/create_fb_events.sql
Инициализация: python setup_supabase.py

Поля fb_events:
    id, title, date, time, location, description,
    registration_url, source_url, group_url, group_name,
    post_author, image_url, scraped_at, created_at
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# Имя таблицы берётся из конфига (default: "events_parsed")
from .config import FB_EVENTS_TABLE as _FB_EVENTS_TABLE

# Кэш клиента
_client = None


def _get_client():
    """Lazy-инициализация Supabase клиента."""
    global _client
    if _client is not None:
        return _client

    from .config import SUPABASE_KEY, SUPABASE_URL
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("✅ Supabase (fb_events) клиент инициализирован")
    except ImportError:
        log.warning("⚠️  supabase SDK не установлен: pip install supabase")
    except Exception as e:
        log.warning(f"⚠️  Supabase init error: {e}")

    return _client


def _parse_date_str(date_raw: str) -> Optional[str]:
    """Пробует привести строку даты к ISO-формату YYYY-MM-DD."""
    if not date_raw:
        return None

    # Уже ISO
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_raw)
    if m:
        return m.group(0)

    # DD/MM/YYYY или DD-MM-YYYY
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    return None


def _event_to_row(event: dict) -> Optional[dict]:
    """
    Преобразует словарь события (из ollama_filter) в строку для fb_events.
    Возвращает None если нет обязательного поля title.
    """
    title = (event.get("title") or "").strip()
    if not title:
        return None

    # Дата
    date_raw = event.get("date") or event.get("date_raw") or ""
    date_normalized = _parse_date_str(date_raw)

    # URL изображения: первый из списка
    image_urls = event.get("image_urls", [])
    if isinstance(image_urls, list):
        image_url = image_urls[0] if image_urls else None
    else:
        # Строка, разделённая ';'
        parts = [u.strip() for u in str(image_urls).split(";") if u.strip()]
        image_url = parts[0] if parts else None

    source_url = (event.get("post_url") or event.get("source_url") or "").strip() or None

    return {
        "title":            title[:500],
        "date":             date_normalized,
        "time":             (event.get("time") or "").strip()[:20] or None,
        "location":         (event.get("location") or "").strip()[:500] or None,
        "description":      (event.get("description") or "").strip()[:2000] or None,
        "registration_url": (event.get("registration_url") or event.get("contact") or "").strip()[:500] or None,
        "source_url":       source_url,
        "group_url":        (event.get("group_url") or "").strip()[:500] or None,
        "group_name":       (event.get("group_name") or "").strip()[:200] or None,
        "post_author":      (event.get("post_author") or "").strip()[:200] or None,
        "image_url":        image_url,
        "scraped_at":       datetime.now().isoformat(),
    }


def _upsert_batch_sync(events: list[dict]) -> tuple[int, list[str]]:
    """
    Синхронный batch upsert в fb_events.
    Возвращает (кол-во upserted, список ошибок).
    """
    client = _get_client()
    if client is None:
        return 0, ["Supabase не настроен (SUPABASE_URL/SUPABASE_KEY пусты)"]

    rows = [_event_to_row(ev) for ev in events]
    rows = [r for r in rows if r is not None]

    if not rows:
        return 0, ["Нет валидных строк для upsert"]

    errors: list[str] = []
    upserted = 0

    # Разделяем: строки с source_url (можно upsert по UNIQUE) и без
    rows_with_url   = [r for r in rows if r.get("source_url")]
    rows_without_url = [r for r in rows if not r.get("source_url")]

    # Batch upsert для строк с source_url (ON CONFLICT source_url DO UPDATE)
    if rows_with_url:
        try:
            result = (
                client.table(_FB_EVENTS_TABLE)
                .upsert(rows_with_url, on_conflict="source_url")
                .execute()
            )
            upserted += len(result.data) if result.data else len(rows_with_url)
        except Exception as e:
            err = str(e)
            if "PGRST205" in err or "not found" in err.lower():
                errors.append(
                    "Таблица fb_events не найдена!\n"
                    "  Создайте её: https://supabase.com/dashboard/project/nhdyzznfitwlbcaaacwx/sql/new\n"
                    "  SQL: sql/create_fb_events.sql"
                )
            else:
                errors.append(f"Upsert error: {err[:200]}")

    # INSERT для строк без source_url (нет UNIQUE key — просто вставляем, игнорируем дубли)
    if rows_without_url:
        try:
            result = (
                client.table(_FB_EVENTS_TABLE)
                .insert(rows_without_url)
                .execute()
            )
            upserted += len(result.data) if result.data else len(rows_without_url)
        except Exception as e:
            errors.append(f"Insert (no-url) error: {str(e)[:200]}")

    return upserted, errors


async def upsert_fb_events(events: list[dict]) -> int:
    """
    Async wrapper: сохраняет события из Facebook в таблицу fb_events.

    Дедупликация:
    - Строки с source_url → ON CONFLICT source_url DO UPDATE
    - Строки без source_url → INSERT (риск дублей, но редкий кейс)

    Возвращает количество upserted строк.
    """
    if not events:
        return 0

    count, errors = await asyncio.to_thread(_upsert_batch_sync, events)

    for err in errors:
        if "не найдена" in err:
            log.error(f"❌ {err}")
        else:
            log.warning(f"⚠️  {err}")

    if count:
        log.info(f"☁️  fb_events: upserted {count} событий")

    return count


def is_configured() -> bool:
    """Возвращает True если Supabase настроен (URL + KEY заданы)."""
    from .config import SUPABASE_KEY, SUPABASE_URL
    return bool(SUPABASE_URL and SUPABASE_KEY)
