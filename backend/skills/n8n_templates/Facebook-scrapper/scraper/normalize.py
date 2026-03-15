"""
scraper/normalize.py — Нормализация и форматирование данных событий

Отвечает за:
- Нормализацию дат (шведские/английские форматы)
- Очистку строк (title, location)
- Генерацию ключа дедупликации по post_url или hash  (_dedup_key → CSV)
- Генерацию source_hash (SHA-256 raw-контента → Supabase UNIQUE KEY)
- Добавление поля scraped_at
"""

import hashlib
import re
from datetime import datetime
from typing import Optional


# Шведские названия месяцев → номер
_SV_MONTHS = {
    "januari": 1,  "jan": 1,
    "februari": 2, "feb": 2,
    "mars": 3,     "mar": 3,
    "april": 4,    "apr": 4,
    "maj": 5,
    "juni": 6,     "jun": 6,
    "juli": 7,     "jul": 7,
    "augusti": 8,  "aug": 8,
    "september": 9,"sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "oct": 10,
    "november": 11,"nov": 11,
    "december": 12,"dec": 12,
}


def normalize_title(title: str) -> str:
    """Очищает и нормализует название мероприятия."""
    if not title:
        return "Без названия"
    title = re.sub(r"\s+", " ", title).strip()
    # Убираем эмодзи-мусор в начале
    title = re.sub(r"^[\U00010000-\U0010FFFF\U00002702-\U000027B0\U0001F000-\U0001F9FF\s]+", "", title)
    return title.strip()[:200] or "Без названия"


def normalize_location(loc: str) -> str:
    """Очищает строку с местоположением."""
    if not loc:
        return ""
    return re.sub(r"\s+", " ", loc).strip()[:300]


def _try_parse_date(date_raw: str) -> Optional[str]:
    """
    Пытается распознать дату из строки в шведском/английском формате.
    Возвращает ISO-дату 'YYYY-MM-DD' если успешно, иначе None.
    """
    if not date_raw:
        return None

    date_raw_lower = date_raw.lower().strip()

    # Шаблоны: "15 mars 2025", "mars 15", "15/03/2025" и т.д.
    patterns = [
        # DD Month YYYY  (шведский/английский)
        (r"(\d{1,2})\s+([a-zåäö]+)\s+(\d{4})", lambda m: _sv_to_iso(m)),
        # Month DD, YYYY
        (r"([a-zåäö]+)\s+(\d{1,2}),?\s+(\d{4})", lambda m: _sv_month_day_year(m)),
        # DD/MM/YYYY или DD-MM-YYYY
        (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
        # YYYY-MM-DD (уже ISO)
        (r"(\d{4})-(\d{2})-(\d{2})", lambda m: m.group(0)),
    ]

    for pattern, handler in patterns:
        match = re.search(pattern, date_raw_lower)
        if match:
            try:
                result = handler(match)
                if result:
                    # Валидируем
                    datetime.strptime(result, "%Y-%m-%d")
                    return result
            except (ValueError, AttributeError):
                continue

    return None


def _sv_to_iso(m: re.Match) -> Optional[str]:
    """Конвертирует 'DD Month YYYY' → 'YYYY-MM-DD'."""
    day = int(m.group(1))
    month_str = m.group(2).lower()
    year = int(m.group(3))
    month = _SV_MONTHS.get(month_str)
    if month and 1 <= day <= 31 and 2024 <= year <= 2030:
        return f"{year}-{month:02d}-{day:02d}"
    return None


def _sv_month_day_year(m: re.Match) -> Optional[str]:
    """Конвертирует 'Month DD YYYY' → 'YYYY-MM-DD'."""
    month_str = m.group(1).lower()
    day = int(m.group(2))
    year = int(m.group(3))
    month = _SV_MONTHS.get(month_str)
    if month and 1 <= day <= 31 and 2024 <= year <= 2030:
        return f"{year}-{month:02d}-{day:02d}"
    return None


def source_hash(post_or_event: dict) -> str:
    """
    SHA-256 хеш содержимого поста для content-based дедупликации.

    Используется как UNIQUE KEY в Supabase raw_posts (ON CONFLICT source_hash).
    Устойчив к повторным запускам и незначительным изменениям LLM-вывода.

    Стратегия:
    1. Если есть post_url → sha256("url:<post_url>")  — стабильно и быстро.
    2. Иначе → sha256(group_url + "|" + text[:500] + "|" + sorted_image_urls)
    """
    post_url = (post_or_event.get("post_url") or "").strip()
    if post_url and len(post_url) > 20:
        return hashlib.sha256(f"url:{post_url}".encode("utf-8")).hexdigest()

    # Fallback: content hash из сырых полей поста
    text = (
        post_or_event.get("text")
        or post_or_event.get("description")
        or ""
    ).strip()
    img_raw = post_or_event.get("image_urls") or ""
    if isinstance(img_raw, list):
        imgs_sorted = ";".join(sorted(img_raw))
    else:
        imgs_sorted = ";".join(sorted(img_raw.split(";")))

    parts = [
        post_or_event.get("group_url", ""),
        text[:500],
        imgs_sorted,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def dedup_key(event: dict) -> str:
    """
    Генерирует ключ дедупликации для события.

    Стратегия (по приоритету):
    1. post_url — лучший уникальный идентификатор
    2. hash(group_url + date_normalized + location_normalized + title_normalized)

    Это решает проблемы с:
    - Одинаковыми 'Loppis' и 'Öppet hus' в разных группах
    - Одним постом с двух сессий скрейпинга
    """
    post_url = (event.get("post_url") or "").strip()
    if post_url and len(post_url) > 20:
        return f"url:{post_url}"

    # Fallback: hash из ключевых полей
    parts = [
        event.get("group_url", ""),
        normalize_title(event.get("title", "")).lower(),
        (event.get("date_raw") or "").strip().lower()[:30],
        normalize_location(event.get("location", "")).lower()[:50],
    ]
    raw = "|".join(parts)
    return f"hash:{hashlib.md5(raw.encode()).hexdigest()}"


def enrich_event(event: dict, group_name: str = "") -> dict:
    """
    Нормализует и обогащает словарь события:
    - Нормализует title и location
    - Добавляет date_normalized (ISO если удалось распознать)
    - Добавляет scraped_at
    - Добавляет _dedup_key (для CSV дедупликации)
    - Добавляет source_hash (SHA-256, UNIQUE KEY для Supabase)
    - Устанавливает group_name если не задан
    """
    event = dict(event)  # копируем

    event["title"]    = normalize_title(event.get("title", ""))
    event["location"] = normalize_location(event.get("location", ""))

    # Пробуем нормализовать дату
    date_raw = event.get("date_raw", "")
    event["date_normalized"] = _try_parse_date(date_raw) or ""

    event["scraped_at"] = datetime.now().isoformat()
    event["group_name"] = event.get("group_name") or group_name
    event["_dedup_key"] = dedup_key(event)
    event["source_hash"] = source_hash(event)

    return event
