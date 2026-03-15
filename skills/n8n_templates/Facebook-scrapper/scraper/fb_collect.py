"""
scraper/fb_collect.py — Сбор постов из групп Facebook

Отвечает за:
- Навигацию к группе
- Сбор текстов постов
- Извлечение image_urls (img[src] + background-image CSS)
- Ранний выход если встретили уже виденные посты (state-aware)
"""

import asyncio
import logging
import random
import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .config import POSTS_PER_GROUP, SCROLL_ITERATIONS
from .human import human_delay, micro_delay, move_mouse_randomly, smooth_scroll

log = logging.getLogger(__name__)

# JavaScript для извлечения постов из DOM.
# Вынесен как константа — легко обновить при изменении разметки Facebook.
_EXTRACT_POSTS_JS = r"""
(args) => {
    const { maxPosts, seenUrls } = args;
    const results = [];
    const textSeen = new Set();

    // ── 1. Ищем контейнеры постов (несколько стратегий) ─────────
    const ARTICLE_SELECTORS = [
        'div[role="article"]',
        'div[data-pagelet^="FeedUnit"]',
        'div[data-testid="fbfeed_story"]',
        'div[data-ad-comet-preview="story"]',
    ];
    let articles = [];
    for (const sel of ARTICLE_SELECTORS) {
        const found = Array.from(document.querySelectorAll(sel));
        if (found.length > articles.length) articles = found;
    }

    for (const article of articles) {

        // ── 2. Текст поста ───────────────────────────────────────
        const TEXT_SELECTORS = [
            'div[data-ad-comet-preview="message"] span',
            'div[data-ad-preview="message"] span',
            'div[class*="xdj266r"] span[dir="auto"]',
            'div[class*="x1iorvi4"] span',
            'span[dir="auto"]',
        ];
        let fullText = '';
        for (const sel of TEXT_SELECTORS) {
            for (const el of article.querySelectorAll(sel)) {
                const t = el.innerText?.trim();
                if (t && t.length > 20 && !fullText.includes(t)) {
                    fullText += t + ' ';
                }
            }
        }
        fullText = fullText.trim();
        if (fullText.length < 30) continue;

        // Дедупликация внутри одного прохода
        const dedupKey = fullText.substring(0, 100);
        if (textSeen.has(dedupKey)) continue;
        textSeen.add(dedupKey);

        // ── 3. Автор ─────────────────────────────────────────────
        let author = '';
        const authorEl = article.querySelector(
            'a[role="link"] strong, span[class*="xt0psk2"], h2 a, h3 a'
        );
        if (authorEl) author = authorEl.innerText?.trim() || '';

        // ── 4. Дата публикации ───────────────────────────────────
        let timestampRaw = '';
        const timeEl = article.querySelector(
            'abbr[data-utime], a[role="link"] abbr'
        );
        if (timeEl) {
            timestampRaw = timeEl.getAttribute('data-utime') ||
                           timeEl.getAttribute('title') ||
                           timeEl.innerText?.trim() || '';
        }
        if (!timestampRaw) {
            for (const sp of article.querySelectorAll('span')) {
                const t = sp.innerText?.trim();
                if (t && t.match(/\\d{1,2}\\s*(tim|min|dag|vec|h|m|d|w|Yesterday|Igår)/i)) {
                    timestampRaw = t;
                    break;
                }
            }
        }

        // ── 5. URL поста ─────────────────────────────────────────
        let postUrl = '';
        const postLinkSelectors = [
            'a[href*="/posts/"]',
            'a[href*="?story_fbid="]',
            'a[href*="/permalink/"]',
            'a[href*="story_fbid"]',
        ];
        for (const sel of postLinkSelectors) {
            const lk = article.querySelector(sel);
            if (lk) {
                const href = lk.getAttribute('href') || '';
                if (href) {
                    postUrl = href.startsWith('http')
                        ? href.split('?')[0]
                        : 'https://www.facebook.com' + href.split('?')[0];
                    break;
                }
            }
        }

        // ── Ранний выход: этот пост уже видели ───────────────────
        if (postUrl && seenUrls.includes(postUrl)) {
            // Возвращаем специальный маркер — сигнал Python-коду остановиться
            results.push({ __stop_signal: true, post_url: postUrl });
            break;
        }

        // ── 6. Изображения поста — строгий CDN-фильтр ────────────
        // Берём только реальные фото-CDN URL Facebook.
        // Исключаем: аватары (p[0-9]+x[0-9]+), иконки, спиннеры,
        //            emoji-картинки, рекламные пиксели (<100 символов).
        const IMG_MIN_LEN = 80;
        const CDN_HOSTS = ['scontent.', 'scontent-', 'fbcdn.net', 'fbsbx.com'];
        const IMG_BLOCKLIST = [
            /\/cp\//, /\/emoji\.php/, /\/rsrc\.php/,
            /\/[a-z]{1,3}\d+x\d+/, // аватары вида p40x40
            /blank\.gif/, /spinner/, /placeholder/,
        ];

        let imageUrls = [];

        // img[src]
        for (const img of article.querySelectorAll('img')) {
            const src = img.getAttribute('src') || '';
            if (
                src.startsWith('https://') &&
                src.length >= IMG_MIN_LEN &&
                CDN_HOSTS.some(h => src.includes(h)) &&
                !IMG_BLOCKLIST.some(rx => rx.test(src))
            ) {
                imageUrls.push(src);
            }
        }

        // background-image (Facebook иногда кладёт сюда фото)
        for (const el of article.querySelectorAll('div[style], span[style]')) {
            const style = window.getComputedStyle(el);
            const bg = style.backgroundImage || '';
            if (bg && bg !== 'none' && bg.includes('url(')) {
                const match = bg.match(/url\\(["']?(.+?)["']?\\)/);
                if (match) {
                    const bgUrl = match[1];
                    if (
                        bgUrl.startsWith('https://') &&
                        bgUrl.length >= IMG_MIN_LEN &&
                        CDN_HOSTS.some(h => bgUrl.includes(h)) &&
                        !IMG_BLOCKLIST.some(rx => rx.test(bgUrl))
                    ) {
                        imageUrls.push(bgUrl);
                    }
                }
            }
        }

        // Дедупликация + жёсткий лимит 2 изображения на пост
        imageUrls = Array.from(new Set(imageUrls)).slice(0, 2);

        // ── 7. Прикреплённый контент (ссылки/анонсы) ─────────────
        let attachmentText = '';
        const attachEl = article.querySelector(
            'div[data-testid="share_body"], div[class*="x1yrsyyn"]'
        );
        if (attachEl) {
            const at = attachEl.innerText?.trim();
            if (at && at.length > 10) attachmentText = at.substring(0, 300);
        }

        results.push({
            text:           fullText.substring(0, 2000),
            attachment:     attachmentText,
            author:         author,
            timestamp_raw:  timestampRaw,
            post_url:       postUrl,
            image_urls:     imageUrls,
        });

        if (results.length >= maxPosts * 2) break;
    }

    return results;
}
"""


def _normalize_group_url(url: str) -> str:
    """Убирает лишние суффиксы из URL группы (/about, /members и т.д.)."""
    url = url.rstrip("/")
    url = re.sub(r"/(about|members|media|events|files|search|videos|photos).*$", "", url)
    return url


async def navigate_to_group(page: Page, group_url: str) -> bool:
    """
    Переходит на страницу группы.
    Проверяет стену авторизации.
    Возвращает True если загружено успешно.
    """
    url = _normalize_group_url(group_url)
    log.info(f"🔗 Перехожу: {url}")

    await human_delay(2.0, 4.5)

    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if resp and resp.status >= 400:
            log.error(f"❌ HTTP {resp.status} — {url}")
            return False
    except PlaywrightTimeoutError:
        log.error(f"❌ Timeout — {url}")
        return False

    await human_delay(3.0, 6.0)
    await move_mouse_randomly(page)

    # Проверяем стену авторизации
    try:
        body_text = await page.inner_text("body")
    except Exception:
        body_text = ""

    auth_phrases = [
        "log in", "sign in", "войдите", "create account",
        "you must log in", "необходимо войти",
        "logga in", "skapa konto",   # шведские
    ]
    if any(p in body_text.lower() for p in auth_phrases):
        log.error(
            "❌ Facebook требует авторизации!\n"
            "   Откройте Chrome, войдите в Facebook, закройте Chrome, затем запустите скрипт."
        )
        return False

    log.info(f"✅ Группа загружена: {url}")
    return True


async def collect_posts(
    page: Page,
    group_url: str,
    max_posts: int = POSTS_PER_GROUP,
    seen_post_urls: list[str] | None = None,
) -> tuple[list[dict], bool]:
    """
    Собирает последние N постов из ленты группы.

    Параметры:
        page           — Playwright Page
        group_url      — URL группы (для метаданных)
        max_posts      — максимальное количество постов
        seen_post_urls — список уже виденных URL (для раннего выхода)

    Возвращает:
        (posts, early_stopped)
        - posts         — список словарей с данными поста
        - early_stopped — True если остановились досрочно (нашли знакомый пост)

    Структура поста:
        text, attachment, author, timestamp_raw,
        post_url, image_urls, group_url
    """
    log.info(f"📜 Сбор постов (цель: {max_posts})...")

    seen_urls: list[str] = seen_post_urls or []
    collected: dict[str, dict] = {}
    early_stopped = False
    scroll_rounds = 0
    max_scroll_rounds = SCROLL_ITERATIONS + 5

    while len(collected) < max_posts and scroll_rounds < max_scroll_rounds:
        raw = await page.evaluate(
            _EXTRACT_POSTS_JS,
            {"maxPosts": max_posts, "seenUrls": seen_urls},
        )

        new_count = 0
        for item in raw:
            # Сигнал раннего выхода
            if item.get("__stop_signal"):
                log.info(f"   🛑 Ранний выход: пост уже видели ранее ({item.get('post_url', '')})")
                early_stopped = True
                break

            key = item["text"][:80]
            if key not in collected:
                item["group_url"] = group_url
                collected[key] = item
                new_count += 1

        log.info(f"   Раунд {scroll_rounds + 1}: +{new_count} | всего: {len(collected)}")

        if early_stopped or len(collected) >= max_posts:
            break

        # Скроллим дальше
        await page.mouse.wheel(0, random.randint(400, 700))
        await asyncio.sleep(random.uniform(1.5, 3.5))
        scroll_rounds += 1

        if scroll_rounds % 3 == 0:
            log.debug("   😴 Читательская пауза...")
            await asyncio.sleep(random.uniform(3.0, 6.0))

    posts = list(collected.values())[:max_posts]
    log.info(f"📋 Собрано постов: {len(posts)}{' (ранний выход)' if early_stopped else ''}")
    return posts, early_stopped
