"""
scraper/config.py — Централизованная конфигурация
Загружает все переменные из .env и предоставляет их как типизированные константы.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Браузер ─────────────────────────────────────────────────────
CHROME_USER_DATA_DIR: str = os.getenv("CHROME_USER_DATA_DIR", "")
HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"

# ── Скрейпинг ───────────────────────────────────────────────────
_raw_groups = os.getenv("GROUP_URLS", "")
GROUP_URLS: list[str] = [u.strip() for u in _raw_groups.split(",") if u.strip()]

# 15–20 постов: оптимальный баланс полноты и скорости/безопасности
# Принудительно зажимаем значение в диапазон [15, 20]
POSTS_PER_GROUP: int = max(15, min(int(os.getenv("POSTS_PER_GROUP", "20")), 20))
SCROLL_ITERATIONS: int = int(os.getenv("SCROLL_ITERATIONS", "6"))
# Максимум изображений на пост для vision-анализа (строгий лимит)
MAX_IMAGES_PER_POST: int = 2
# Максимум изображений для vision-анализа на один пост-кандидат
MAX_VISION_IMAGES_PER_POST: int = 2

# ── LLM ─────────────────────────────────────────────────────────
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-5-mini")
VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen2.5vl")
# Порог уверенности: ниже — запускаем vision
VISION_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("VISION_CONFIDENCE_THRESHOLD", "0.6")
)

# ── Вывод ───────────────────────────────────────────────────────
OUTPUT_FILE: str = os.getenv("OUTPUT_FILE", "events.csv")
STATE_FILE: str = os.getenv("STATE_FILE", "state.json")

# ── Локаль (Швеция) ─────────────────────────────────────────────
LOCALE: str = os.getenv("LOCALE", "sv-SE")
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Stockholm")
ACCEPT_LANGUAGE: str = os.getenv(
    "ACCEPT_LANGUAGE", "sv-SE,sv;q=0.9,en;q=0.8,en-US;q=0.7"
)

# ── Лимит запусков: не чаще 1 раза в сутки ─────────────────────
MIN_RUN_INTERVAL_HOURS: float = float(
    os.getenv("MIN_RUN_INTERVAL_HOURS", "22")
)
# Принудительный запуск, игнорируя лимит (для отладки)
FORCE_RUN: bool = os.getenv("FORCE_RUN", "false").lower() == "true"

# ── Supabase (опционально) ──────────────────────────────────────
# Если оба значения заданы — события upsert'ятся в raw_posts.
# Если пусты — Supabase пропускается, CSV остаётся единственным хранилищем.
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE: str = os.getenv("SUPABASE_TABLE", "raw_posts")
# Пароль базы данных PostgreSQL (не API-ключ!) — для автосоздания таблиц через psycopg2.
# Найти: Supabase Dashboard → Settings → Database → Database password
SUPABASE_DB_PASSWORD: str = os.getenv("SUPABASE_DB_PASSWORD", "")

# ── LLM Retry ───────────────────────────────────────────────────
# Кол-во попыток при RateLimitError / TimeoutError / 5xx
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

# ── Ollama (локальная LLM для фильтрации постов) ────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma2:2b")
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "30"))

# ── Supabase: events_parsed (отдельная таблица для FB-постов) ────
FB_EVENTS_TABLE: str = os.getenv("FB_EVENTS_TABLE", "events_parsed")

# ── Пути ────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parent.parent
