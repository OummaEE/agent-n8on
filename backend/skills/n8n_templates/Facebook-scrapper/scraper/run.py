"""
scraper/run.py — Главный оркестратор

Объединяет все модули в единый pipeline:
  browser → fb_collect → OCR → ollama_filter → normalize → storage + Supabase(events_parsed)

Логика на группу:
  1. Загрузить seen_post_urls из state.json
  2. Открыть группу в браузере
  3. Собрать последние N постов (с ранним выходом по знакомым URL)
  3.5. OCR: извлечь текст из изображений
  4. Ollama: классифицировать посты + извлечь структурированные данные
     (только анонсы мероприятий проходят дальше)
  4.5. Fallback (если Ollama недоступен): cloud LLM text + vision
  5. Нормализовать и обогатить события
  6. Сохранить в CSV + JSON
  7. Upsert в Supabase events_parsed (если настроен)
  8. Обновить state.json
  9. Пауза перед следующей группой
"""

import asyncio
import logging
import random
import sys
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from .browser import apply_stealth_patches, build_stealth_context
from .config import (
    FORCE_RUN, GROUP_URLS, MIN_RUN_INTERVAL_HOURS, OUTPUT_FILE,
    POSTS_PER_GROUP, SUPABASE_KEY, SUPABASE_URL, VISION_CONFIDENCE_THRESHOLD,
)
from .fb_collect import collect_posts, navigate_to_group
from .human import human_delay
from .llm_text import analyze_posts_batch, build_llm_client
from .ocr import enrich_posts_with_ocr
from .llm_vision import analyze_vision_candidates
from .normalize import enrich_event
from .ollama_filter import filter_posts_batch, is_ollama_available
from .supabase_client import is_configured as supabase_is_configured, upsert_events
from .supabase_fb_events import upsert_fb_events, is_configured as fb_events_configured
from .storage import (
    GroupStats,
    SessionMetrics,
    get_seen_urls_for_group,
    load_existing_dedup_keys,
    load_state,
    print_events_table,
    save_events_to_csv,
    save_events_to_json,
    save_state,
    update_state_for_group,
)

log = logging.getLogger(__name__)


def _check_daily_limit(state: dict) -> bool:
    """
    Проверяет: не запускались ли мы уже сегодня (в рамках MIN_RUN_INTERVAL_HOURS).
    Возвращает True если запуск разрешён, False — если нужно подождать.

    Хранит last_session_at в state["meta"].
    Можно обойти установив FORCE_RUN=true в .env (только для отладки!).
    """
    if FORCE_RUN:
        log.warning("⚠️  FORCE_RUN=true — пропуск проверки суточного лимита!")
        return True

    meta = state.get("meta", {})
    last_run_str = meta.get("last_session_at", "")

    if last_run_str:
        try:
            last_run = datetime.fromisoformat(last_run_str)
            elapsed = datetime.now() - last_run
            min_interval = timedelta(hours=MIN_RUN_INTERVAL_HOURS)
            if elapsed < min_interval:
                remaining = min_interval - elapsed
                hours   = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                log.warning(
                    f"⏰ Слишком рано для нового запуска!"
                )
                log.warning(
                    f"   Последний запуск: {last_run.strftime('%Y-%m-%d %H:%M')}"
                )
                log.warning(
                    f"   Следующий разрешён через: {hours}ч {minutes}мин"
                    f" (MIN_RUN_INTERVAL_HOURS={MIN_RUN_INTERVAL_HOURS})"
                )
                return False
        except ValueError:
            pass  # Если дата не парсится — разрешаем запуск

    return True


def _mark_session_started(state: dict) -> dict:
    """Записывает время старта сессии в state[\"meta\"]."""
    if "meta" not in state:
        state["meta"] = {}
    state["meta"]["last_session_at"] = datetime.now().isoformat()
    return state


async def process_group(
    page: Page,
    llm_client,
    group_url: str,
    group_index: int,
    total_groups: int,
    state: dict,
    dedup_keys: set[str],
) -> tuple[list[dict], GroupStats]:
    """
    Полный pipeline обработки одной группы Facebook.

    Возвращает (события, статистика_группы).
    """
    gs = GroupStats(group_url)
    log.info(f"\n{'─' * 60}")
    log.info(f"📦 [{group_index}/{total_groups}] {group_url}")
    log.info(f"{'─' * 60}")

    group_name = gs.group_name

    # ── Шаг 1: seen_post_urls для раннего выхода ──────────────────
    seen_urls = get_seen_urls_for_group(state, group_url)
    log.info(f"   📚 Уже видели: {len(seen_urls)} URL из этой группы")

    # ── Шаг 2: Навигация ──────────────────────────────────────────
    ok = await navigate_to_group(page, group_url)
    if not ok:
        log.error(f"⛔ Пропускаю группу: {group_url}")
        gs.skipped = True
        gs.add_error("Не удалось открыть группу (авторизация или HTTP-ошибка)")
        return [], gs

    # ── Шаг 3: Сбор постов ────────────────────────────────────────
    try:
        posts, early_stopped = await collect_posts(
            page,
            group_url=group_url,
            max_posts=POSTS_PER_GROUP,
            seen_post_urls=seen_urls,
        )
    except Exception as e:
        gs.add_error(f"collect_posts: {type(e).__name__}: {e}")
        log.error(f"❌ Ошибка сбора постов: {e}")
        return [], gs

    gs.posts_collected = len(posts)
    gs.early_stopped   = early_stopped

    if not posts:
        log.warning(f"⚠️  Посты не найдены: {group_url}")
        gs.add_error("Посты не найдены (группа пуста или структура изменилась)")
        return [], gs

    # ── Шаг 3.5: OCR для изображений ──────────────────────────────
    try:
        posts = await enrich_posts_with_ocr(posts)
    except Exception as e:
        log.warning(f"⚠️  OCR пропущен: {type(e).__name__}: {e}")

    # ── Шаг 4: Классификация через Ollama (primary) ───────────────
    all_events: list[dict] = []
    use_ollama = is_ollama_available()

    if use_ollama:
        try:
            ollama_events = await filter_posts_batch(posts, group_name=group_name)
            gs.events_from_text = len(ollama_events)
            all_events = ollama_events
            log.info(f"   🤖 Ollama: {len(ollama_events)} событий из {len(posts)} постов")
        except Exception as e:
            gs.add_error(f"Ollama: {type(e).__name__}: {e}")
            log.error(f"❌ Ошибка Ollama: {e}")
            use_ollama = False  # Упадём на fallback

    # ── Шаг 4.5: Fallback — cloud LLM (если Ollama недоступен) ────
    if not use_ollama:
        log.warning("⚠️  Ollama недоступен — использую cloud LLM как fallback")
        try:
            text_events, vision_candidates = await analyze_posts_batch(
                llm_client, posts, group_name=group_name
            )
        except Exception as e:
            gs.add_error(f"LLM text: {type(e).__name__}: {e}")
            log.error(f"❌ Ошибка LLM text-анализа: {e}")
            text_events, vision_candidates = [], []

        gs.events_from_text  = len(text_events)
        gs.vision_candidates = len(vision_candidates)

        try:
            vision_events = await analyze_vision_candidates(
                llm_client,
                vision_candidates,
                group_name=group_name,
                confidence_threshold=VISION_CONFIDENCE_THRESHOLD,
            )
        except Exception as e:
            gs.add_error(f"Vision: {type(e).__name__}: {e}")
            log.error(f"❌ Ошибка vision-анализа: {e}")
            vision_events = []

        gs.events_from_vision = len(vision_events)
        all_events = text_events + vision_events

    # ── Шаг 5: Нормализация ───────────────────────────────────────
    all_events = [enrich_event(ev, group_name=group_name) for ev in all_events]

    # ── Шаг 7: Обновляем state ────────────────────────────────────
    new_post_urls = [p.get("post_url", "") for p in posts if p.get("post_url", "")]
    state.update(update_state_for_group(state, group_url, new_post_urls))

    # ── Лог по группе ─────────────────────────────────────────────
    gs.log_summary()

    return all_events, gs


async def run() -> None:
    """Главная точка входа. Запускает полный pipeline."""

    # ── Валидация конфига ──────────────────────────────────────────
    from .config import CHROME_USER_DATA_DIR
    errors = []
    if not GROUP_URLS:
        errors.append(
            "GROUP_URLS не задан в .env!\n"
            "  Пример: GROUP_URLS=https://www.facebook.com/groups/g1,https://www.facebook.com/groups/g2"
        )
    if not CHROME_USER_DATA_DIR:
        errors.append(
            "CHROME_USER_DATA_DIR не задан в .env!\n"
            r"  Пример (Windows): C:\Users\Name\AppData\Local\Google\Chrome\User Data"
        )
    if errors:
        for err in errors:
            log.error(f"❌ {err}")
        sys.exit(1)

    # ── LLM клиент ─────────────────────────────────────────────────
    try:
        llm_client = build_llm_client()
        log.info("🤖 LLM клиент инициализирован")
    except ValueError as e:
        log.error(str(e))
        sys.exit(1)

    # ── Состояние и дедуп-ключи ────────────────────────────────────
    state = load_state()
    dedup_keys = load_existing_dedup_keys(OUTPUT_FILE)
    metrics = SessionMetrics()

    # ── Проверка лимита: 1 раз в сутки ────────────────────────────
    if not _check_daily_limit(state):
        log.warning("🚫 Запуск отменён — соблюдайте интервал между сессиями.")
        sys.exit(0)

    # Фиксируем время старта
    state = _mark_session_started(state)
    save_state(state)

    # ── Шапка ──────────────────────────────────────────────────────
    from .config import (
        HEADLESS, LLM_MODEL, LOCALE, OUTPUT_FILE as OUT,
        SCROLL_ITERATIONS, TIMEZONE, VISION_MODEL,
    )
    log.info("=" * 65)
    log.info("🚀 Facebook Group Events Scraper v4.0 запущен")
    log.info(f"   Групп:               {len(GROUP_URLS)}")
    log.info(f"   Постов на группу:    {POSTS_PER_GROUP} (макс. 20)")
    log.info(f"   LLM model:           {LLM_MODEL}")
    log.info(f"   Vision model:        {VISION_MODEL}")
    log.info(f"   Vision threshold:    {VISION_CONFIDENCE_THRESHOLD:.0%}")
    log.info(f"   Интервал запусков:   {MIN_RUN_INTERVAL_HOURS}ч (1 раз в сутки)")
    log.info(f"   Locale/TZ:           {LOCALE} / {TIMEZONE}")
    log.info(f"   Headless:            {HEADLESS}")
    log.info(f"   Выход:               {OUT}")
    log.info(f"   Supabase:            {'✅ настроен' if supabase_is_configured() else '⬜ не настроен (только CSV)'}")
    log.info(f"   events_parsed:       {'✅ настроен' if fb_events_configured() else '⬜ не настроен'}")
    log.info("=" * 65)

    all_session_events: list[dict] = []

    async with async_playwright() as playwright:
        context: Optional[BrowserContext] = None

        try:
            log.info("🌍 Запускаю браузер...")
            context = await build_stealth_context(playwright)
            page: Page = context.pages[0] if context.pages else await context.new_page()
            await apply_stealth_patches(page)

            for idx, group_url in enumerate(GROUP_URLS, 1):
                try:
                    events, gs = await process_group(
                        page=page,
                        llm_client=llm_client,
                        group_url=group_url,
                        group_index=idx,
                        total_groups=len(GROUP_URLS),
                        state=state,
                        dedup_keys=dedup_keys,
                    )
                    all_session_events.extend(events)
                    metrics.add_group(gs)

                    # Сохраняем state после каждой группы (crash-safe)
                    save_state(state)

                except PlaywrightTimeoutError as e:
                    log.error(f"❌ Timeout в группе {group_url}")
                    gs_err = GroupStats(group_url)
                    gs_err.skipped = True
                    gs_err.add_error(f"PlaywrightTimeoutError: {e}")
                    metrics.add_group(gs_err)

                except Exception as e:
                    log.error(f"❌ Неожиданная ошибка в группе {group_url}: {type(e).__name__}: {e}")
                    import traceback
                    log.debug(traceback.format_exc())
                    gs_err = GroupStats(group_url)
                    gs_err.skipped = True
                    gs_err.add_error(f"{type(e).__name__}: {e}")
                    metrics.add_group(gs_err)

                finally:
                    if idx < len(GROUP_URLS):
                        pause = random.uniform(15.0, 35.0)
                        log.info(f"😴 Пауза между группами: {pause:.0f} сек...")
                        await asyncio.sleep(pause)

        except KeyboardInterrupt:
            log.info("⚠️  Остановлено пользователем (Ctrl+C)")

        except Exception as e:
            log.error(f"❌ Критическая ошибка: {type(e).__name__}: {e}")
            import traceback
            log.debug(traceback.format_exc())

        finally:
            if context:
                log.info("🔒 Закрываю браузер...")
                await human_delay(1.5, 3.0)
                await context.close()
                log.info("✅ Браузер закрыт.")

    # ── Финальное сохранение ───────────────────────────────────────
    if all_session_events:
        print_events_table(all_session_events)
        saved = save_events_to_csv(all_session_events, OUTPUT_FILE, dedup_keys)
        # Также сохраняем в JSON
        json_file = OUTPUT_FILE.replace(".csv", ".json") if OUTPUT_FILE.endswith(".csv") else OUTPUT_FILE + ".json"
        save_events_to_json(all_session_events, json_file)
        metrics.events_saved = saved

        # ── Supabase events_parsed upsert (основной) ─────────────
        if fb_events_configured():
            try:
                fb_count = await upsert_fb_events(all_session_events)
                metrics.supabase_upserted = fb_count
                if fb_count > 0:
                    log.info(f"☁️  events_parsed: {fb_count} событий сохранено")
            except Exception as e:
                err = str(e)
                if "PGRST205" in err or "not found" in err.lower():
                    log.error(
                        "❌ Таблица events_parsed не найдена! "
                        "Запустите: python setup_supabase.py"
                    )
                else:
                    log.warning(f"⚠️  events_parsed upsert ошибка: {e}")

        # ── Supabase raw_posts upsert (legacy, если настроен) ─────
        if supabase_is_configured():
            try:
                sb_count = await upsert_events(all_session_events)
                if not fb_events_configured():
                    metrics.supabase_upserted = sb_count
            except Exception as e:
                log.warning(f"⚠️  Supabase upsert завершился с ошибкой: {e}")
        else:
            log.debug("ℹ️  Supabase не настроен — upsert пропущен")
    else:
        log.warning("⚠️  Мероприятия не найдены за эту сессию.")
        log.warning("   Проверьте: авторизация в FB, корректность GROUP_URLS, наличие постов с анонсами.")

    # ── Итоговая статистика ────────────────────────────────────────
    metrics.print_summary()

    # ── Защитная пауза ────────────────────────────────────────────
    await asyncio.sleep(random.uniform(5.0, 12.0))
    log.info(f"👋 Следующий запуск — не раньше чем через {MIN_RUN_INTERVAL_HOURS:.0f} часов!")
