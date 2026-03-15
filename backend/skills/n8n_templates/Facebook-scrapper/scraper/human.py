"""
scraper/human.py — Человекоподобное поведение

Все функции имитации живого пользователя:
- Случайные паузы (human_delay, micro_delay)
- Плавный скроллинг с откатами
- Случайные движения мышью
"""

import asyncio
import logging
import random

from playwright.async_api import Page

log = logging.getLogger(__name__)


async def human_delay(min_s: float = 3.0, max_s: float = 7.0) -> None:
    """
    Рандомная пауза — имитирует «задумчивость» живого пользователя.
    Диапазон по умолчанию: 3–7 секунд.
    """
    delay = random.uniform(min_s, max_s)
    log.debug(f"⏳ Пауза {delay:.2f} с")
    await asyncio.sleep(delay)


async def micro_delay(min_s: float = 0.3, max_s: float = 1.2) -> None:
    """Короткая пауза между мелкими действиями."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def smooth_scroll(page: Page, iterations: int = 6) -> None:
    """
    Плавный человекоподобный скроллинг страницы вниз.

    Поведение:
    - Каждая итерация: случайный шаг 150–450 px вниз
    - Пауза между шагами: 0.5–2.5 сек
    - 15% вероятность небольшого отката вверх (имитация «перечитывания»)
    - «Читательская пауза» каждые 3 шага (2–5 сек)
    """
    log.info(f"🖱️  Скроллинг ({iterations} итераций)...")

    for i in range(1, iterations + 1):
        # Иногда слегка скроллим вверх — живой человек так делает
        if random.random() < 0.15 and i > 1:
            back = random.randint(30, 100)
            await page.mouse.wheel(0, -back)
            await asyncio.sleep(random.uniform(0.3, 0.8))

        step = random.randint(150, 450)
        await page.mouse.wheel(0, step)
        await asyncio.sleep(random.uniform(0.5, 2.5))

        if i % 3 == 0:
            rest = random.uniform(2.0, 4.5)
            log.debug(f"   😴 Читательская пауза {rest:.1f}с")
            await asyncio.sleep(rest)

    log.info("✅ Скроллинг завершён.")


async def move_mouse_randomly(page: Page) -> None:
    """
    Случайные движения мышью по экрану.
    Живой пользователь не держит курсор неподвижно.
    """
    if not page.viewport_size:
        return
    w = page.viewport_size["width"]
    h = page.viewport_size["height"]
    for _ in range(random.randint(3, 6)):
        await page.mouse.move(
            random.randint(80, w - 80),
            random.randint(80, h - 80),
        )
        await asyncio.sleep(random.uniform(0.1, 0.35))
