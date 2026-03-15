"""
scraper/storage.py — Сохранение результатов и управление состоянием

Отвечает за:
- Сохранение событий в CSV (с дедупликацией по _dedup_key)
- Загрузку/сохранение state.json (last_run_at, seen_post_urls по группе)
- Вывод итоговой сводки по сессии
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import OUTPUT_FILE, STATE_FILE
from .normalize import dedup_key

log = logging.getLogger(__name__)

# ── CSV колонки (порядок важен для читаемости) ───────────────────────────────
CSV_FIELDNAMES = [
    "title",
    "event_type",
    "date_raw",
    "date_normalized",
    "location",
    "description",
    "contact",
    "confidence",
    "source",            # 'text' или 'vision'
    "group_name",
    "group_url",
    "post_author",
    "post_date",
    "post_url",
    "image_urls",        # ; separated
    "source_hash",       # SHA-256 content key (используется как UNIQUE KEY в Supabase)
    "scraped_at",
]

# Максимум хранимых seen_post_urls на группу (экономим память)
_MAX_SEEN_URLS = 500


# ════════════════════════════════════════════════════════════════════
#  CSV
# ════════════════════════════════════════════════════════════════════

def load_existing_dedup_keys(filepath: str = OUTPUT_FILE) -> set[str]:
    """Загружает все dedup-ключи из существующего CSV."""
    path = Path(filepath)
    if not path.exists():
        return set()
    keys: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                # Восстанавливаем ключ из сохранённых данных
                fake = {
                    "post_url":  row.get("post_url", ""),
                    "group_url": row.get("group_url", ""),
                    "title":     row.get("title", ""),
                    "date_raw":  row.get("date_raw", ""),
                    "location":  row.get("location", ""),
                }
                keys.add(dedup_key(fake))
    except Exception as e:
        log.warning(f"⚠️  Не удалось прочитать {filepath}: {e}")
    return keys


def save_events_to_csv(
    events: list[dict],
    filepath: str = OUTPUT_FILE,
    existing_keys: Optional[set[str]] = None,
) -> int:
    """
    Сохраняет мероприятия в CSV.
    Пропускает дубли по _dedup_key.
    Возвращает количество реально сохранённых новых записей.
    """
    if not events:
        log.warning("⚠️  Нет мероприятий для сохранения.")
        return 0

    if existing_keys is None:
        existing_keys = load_existing_dedup_keys(filepath)

    path = Path(filepath)
    write_header = not path.exists() or path.stat().st_size == 0

    new_events: list[dict] = []
    for ev in events:
        key = ev.get("_dedup_key") or dedup_key(ev)
        if key not in existing_keys:
            existing_keys.add(key)
            new_events.append(ev)

    if not new_events:
        log.info("ℹ️  Все найденные события уже есть в CSV.")
        return 0

    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDNAMES,
            extrasaction="ignore",
        )
        if write_header:
            writer.writeheader()
        writer.writerows(new_events)

    log.info(f"💾 Сохранено {len(new_events)} новых событий → '{filepath}'")
    return len(new_events)


def save_events_to_json(
    events: list[dict],
    filepath: str = "events.json",
    existing_keys: Optional[set[str]] = None,
) -> int:
    """
    Сохраняет мероприятия в JSON (дополняет к существующему файлу).
    Пропускает дубли по _dedup_key.
    Возвращает количество реально сохранённых новых записей.
    """
    if not events:
        return 0

    if existing_keys is None:
        existing_keys = load_existing_dedup_keys(filepath.replace(".json", ".csv"))

    path = Path(filepath)
    existing: list[dict] = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing_json_keys = {e.get("source_hash", "") for e in existing if e.get("source_hash")}

    new_events: list[dict] = []
    for ev in events:
        key = ev.get("_dedup_key") or dedup_key(ev)
        sh = ev.get("source_hash", "")
        if key not in existing_keys and sh not in existing_json_keys:
            existing_keys.add(key)
            if sh:
                existing_json_keys.add(sh)
            # Exclude internal dedup key from JSON output
            clean = {k: v for k, v in ev.items() if k != "_dedup_key"}
            new_events.append(clean)

    if not new_events:
        log.info("ℹ️  Все события уже есть в JSON.")
        return 0

    all_events = existing + new_events
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    log.info(f"💾 Сохранено {len(new_events)} новых событий → '{filepath}'")
    return len(new_events)


# ════════════════════════════════════════════════════════════════════
#  State management
# ════════════════════════════════════════════════════════════════════

def load_state(filepath: str = STATE_FILE) -> dict:
    """
    Загружает state.json.

    Структура:
    {
      "groups": {
        "<group_url>": {
          "last_run_at": "ISO datetime",
          "seen_post_urls": ["url1", "url2", ...]
        }
      }
    }
    """
    path = Path(filepath)
    if not path.exists():
        return {"groups": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"⚠️  Не удалось загрузить state: {e}. Начинаю с чистого листа.")
        return {"groups": {}}


def save_state(state: dict, filepath: str = STATE_FILE) -> None:
    """Сохраняет state.json."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log.debug(f"💾 State сохранён: {filepath}")
    except Exception as e:
        log.warning(f"⚠️  Не удалось сохранить state: {e}")


def get_seen_urls_for_group(state: dict, group_url: str) -> list[str]:
    """Возвращает список уже виденных post_url для группы."""
    return state.get("groups", {}).get(group_url, {}).get("seen_post_urls", [])


def update_state_for_group(
    state: dict,
    group_url: str,
    new_post_urls: list[str],
) -> dict:
    """
    Обновляет state для группы:
    - Обновляет last_run_at
    - Добавляет новые post_url в seen_post_urls
    - Обрезает список до _MAX_SEEN_URLS (FIFO)
    """
    if "groups" not in state:
        state["groups"] = {}

    group_state = state["groups"].get(group_url, {})
    existing = group_state.get("seen_post_urls", [])

    # Дедупликация + добавление новых
    all_urls = list(dict.fromkeys(existing + new_post_urls))
    # Ограничиваем размер: храним последние N
    if len(all_urls) > _MAX_SEEN_URLS:
        all_urls = all_urls[-_MAX_SEEN_URLS:]

    state["groups"][group_url] = {
        "last_run_at":     datetime.now().isoformat(),
        "seen_post_urls":  all_urls,
    }
    return state


# ════════════════════════════════════════════════════════════════════
#  Метрики сессии
# ════════════════════════════════════════════════════════════════════

class GroupStats:
    """Детальная статистика по одной группе."""

    def __init__(self, group_url: str):
        self.group_url: str = group_url
        self.group_name: str = group_url.rstrip("/").split("/")[-1]
        self.posts_collected: int = 0
        self.vision_candidates: int = 0
        self.events_from_text: int = 0
        self.events_from_vision: int = 0
        self.errors: list[str] = []          # список строк с описанием ошибок
        self.skipped: bool = False           # True если группа пропущена (auth/timeout)
        self.early_stopped: bool = False     # True если сработал ранний выход по state

    @property
    def total_events(self) -> int:
        return self.events_from_text + self.events_from_vision

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        log.error(f"   ⚠️  [{self.group_name}] Ошибка: {msg}")

    def log_summary(self) -> None:
        """Выводит строку статистики по группе в лог."""
        status = "⛔ ПРОПУЩЕНА" if self.skipped else "✅"
        early  = " [ранний выход]" if self.early_stopped else ""
        errs   = f" | ошибок: {len(self.errors)}" if self.errors else ""
        log.info(
            f"   {status} {self.group_name}{early} — "
            f"постов: {self.posts_collected} | "
            f"💬 текст: {self.events_from_text} | "
            f"🖼  vision: {self.events_from_vision} | "
            f"итого: {self.total_events}{errs}"
        )


class SessionMetrics:
    """Счётчики и детальная статистика по всей сессии."""

    def __init__(self):
        self.groups_processed: int = 0
        self.groups_failed: int = 0
        self.posts_collected: int = 0
        self.events_from_text: int = 0
        self.events_from_vision: int = 0
        self.events_saved: int = 0
        self.supabase_upserted: int = 0    # строк upserted в Supabase (0 = отключён)
        self.early_stops: int = 0
        # Детализированные счётчики ошибок
        self.errors_navigation: int = 0    # ошибки навигации / HTTP / авторизация
        self.errors_scraping: int = 0      # ошибки collect_posts
        self.errors_llm_text: int = 0      # ошибки LLM text-анализа
        self.errors_llm_vision: int = 0    # ошибки vision-анализа
        self.errors_other: int = 0         # прочие неожиданные ошибки
        self.per_group: list[GroupStats] = []   # статистика по каждой группе

    @property
    def total_errors(self) -> int:
        return (
            self.errors_navigation + self.errors_scraping +
            self.errors_llm_text + self.errors_llm_vision + self.errors_other
        )

    def add_group(self, gs: GroupStats) -> None:
        """Регистрирует статистику группы и суммирует в общие счётчики."""
        self.per_group.append(gs)
        self.posts_collected    += gs.posts_collected
        self.events_from_text   += gs.events_from_text
        self.events_from_vision += gs.events_from_vision
        if gs.skipped:
            self.groups_failed += 1
        else:
            self.groups_processed += 1
        if gs.early_stopped:
            self.early_stops += 1
        # Распределяем ошибки по типам
        for err in gs.errors:
            el = err.lower()
            if any(k in el for k in ("navigate", "navigation", "авторизац", "http", "timeout")):
                self.errors_navigation += 1
            elif "collect_posts" in el:
                self.errors_scraping += 1
            elif "llm text" in el:
                self.errors_llm_text += 1
            elif "vision" in el:
                self.errors_llm_vision += 1
            else:
                self.errors_other += 1

    def print_summary(self) -> None:
        """Выводит полную итоговую сводку: сначала по каждой группе, потом итог."""
        total_events = self.events_from_text + self.events_from_vision
        tot_errors   = self.total_errors

        print("\n" + "═" * 65)
        print("  📊  СТАТИСТИКА СЕССИИ")
        print("═" * 65)

        # ── Детали по группам ─────────────────────────────────────
        if self.per_group:
            print("\n  По группам:")
            print("  " + "─" * 63)
            for gs in self.per_group:
                status = "⛔" if gs.skipped else "✅"
                early  = " ⏹" if gs.early_stopped else "  "
                errs   = f"  ⚠️  {len(gs.errors)} ош." if gs.errors else ""
                print(
                    f"  {status}{early} {gs.group_name:<25} "
                    f"постов:{gs.posts_collected:>3} | "
                    f"💬{gs.events_from_text:>2} | "
                    f"🖼 {gs.events_from_vision:>2} | "
                    f"итого:{gs.total_events:>3}"
                    f"{errs}"
                )
                # Выводим каждую ошибку под строкой группы
                for err in gs.errors:
                    print(f"        ⚠️  {err}")
            print("  " + "─" * 63)

        # ── Итоги ─────────────────────────────────────────────────
        print(f"\n  Групп обработано:       {self.groups_processed}")
        if self.groups_failed:
            print(f"  Групп с ошибкой:        {self.groups_failed}")
        if self.early_stops:
            print(f"  Ранних выходов:         {self.early_stops}  (знакомые посты, state.json)")
        print(f"  Постов собрано:         {self.posts_collected}")
        print()
        print(f"  💬 Событий из текста:    {self.events_from_text}")
        print(f"  🖼  Событий из vision:    {self.events_from_vision}")
        print(f"  ─────────────────────────────────────────")
        print(f"  Итого найдено:           {total_events}")
        print(f"  Новых сохранено в CSV:   {self.events_saved}")
        if self.supabase_upserted:
            print(f"  ☁️  Supabase upserted:    {self.supabase_upserted}")
        elif self.events_saved > 0:
            print(f"  ☁️  Supabase:             не настроен (только CSV)")

        # ── Детализация ошибок ────────────────────────────────────
        if tot_errors:
            print()
            print(f"  ── Ошибки ({tot_errors} всего) ──────────────────────────────")
            if self.errors_navigation:
                print(f"     🔗 Навигация / HTTP / авторизация: {self.errors_navigation}")
            if self.errors_scraping:
                print(f"     📜 Сбор постов:                    {self.errors_scraping}")
            if self.errors_llm_text:
                print(f"     🤖 LLM text-анализ:                {self.errors_llm_text}")
            if self.errors_llm_vision:
                print(f"     🖼️  Vision-анализ:                  {self.errors_llm_vision}")
            if self.errors_other:
                print(f"     ⚡ Прочие:                          {self.errors_other}")

        print("═" * 65 + "\n")


def print_events_table(events: list[dict]) -> None:
    """Красивый вывод найденных мероприятий в консоль."""
    if not events:
        return
    print("\n" + "═" * 65)
    print(f"  📅  НАЙДЕННЫЕ МЕРОПРИЯТИЯ ({len(events)} шт.)")
    print("═" * 65)
    for i, ev in enumerate(events, 1):
        title    = ev.get("title", "—")
        date_raw = ev.get("date_raw") or ev.get("date_normalized") or "дата не указана"
        location = ev.get("location") or "место не указано"
        etype    = ev.get("event_type", "другое")
        conf     = ev.get("confidence", 0)
        source   = ev.get("source", "?")
        group    = ev.get("group_name") or ev.get("group_url", "")
        descr    = ev.get("description", "")
        imgs     = ev.get("image_urls", "")

        src_icon = "🖼️" if source == "vision" else "💬"
        print(f"\n  [{i}] {title}  {src_icon}")
        print(f"       Тип:      {etype}")
        print(f"       Дата:     {date_raw}")
        print(f"       Место:    {location}")
        print(f"       Группа:   {group}")
        if descr:
            print(f"       Описание: {descr[:110]}")
        if imgs:
            first_img = imgs.split(";")[0][:70]
            print(f"       Фото:     {first_img}...")
        print(f"       Источник: {source} | Уверенность: {conf:.0%}")
    print("\n" + "═" * 65 + "\n")
