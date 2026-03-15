"""
scraper/browser.py — Браузер с максимальным стелсом

Отвечает за:
- Создание Persistent Chrome Context (реальный профиль пользователя)
- Применение playwright-stealth + кастомных JS-патчей fingerprint
- Все антидетект-настройки
"""

import logging
import random
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async

from .config import (
    ACCEPT_LANGUAGE,
    CHROME_USER_DATA_DIR,
    HEADLESS,
    LOCALE,
    TIMEZONE,
)

log = logging.getLogger(__name__)

# Пул реальных User-Agent Chrome 2024–2025
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

# Реалистичные разрешения экранов
_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
]

_STEALTH_JS = """
// ── Убираем признак автоматизации ──────────────────────────────
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined, configurable: true
});

// ── Реальные плагины Chrome ─────────────────────────────────────
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const p = [
            {name:'Chrome PDF Plugin',   filename:'internal-pdf-viewer',    description:'Portable Document Format'},
            {name:'Chrome PDF Viewer',   filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
            {name:'Native Client',       filename:'internal-nacl-plugin',   description:''}
        ];
        p.length = 3;
        return p;
    }
});

// ── Языки ───────────────────────────────────────────────────────
Object.defineProperty(navigator, 'languages', {
    get: () => ['sv-SE', 'sv', 'en', 'en-US']
});

// ── Удаляем Playwright/CDP следы ───────────────────────────────
const _CDP_KEYS = [
    '__playwright', '__pw_manual', '__PW_inspect',
    'cdc_adoQpoasnfa76pfcZLmcfl_Array',
    'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
    'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
];
_CDP_KEYS.forEach(k => { try { delete window[k]; } catch(e){} });

// ── WebGL — реалистичный рендерер ───────────────────────────────
const _getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _getParam.apply(this, [p]);
};

// ── Canvas fingerprint noise ────────────────────────────────────
const _origToData = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    if (type === 'image/png' && this.width === 220 && this.height === 30) {
        const ctx = this.getContext('2d');
        if (ctx) {
            ctx.fillStyle = 'rgba(0,0,0,0.01)';
            ctx.fillRect(Math.random() * 5, Math.random() * 5, 1, 1);
        }
    }
    return _origToData.apply(this, arguments);
};

// ── Chrome runtime (проверяется некоторыми ботдетекторами) ──────
if (!window.chrome) {
    window.chrome = {
        runtime: {
            PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
            PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
            RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
            OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }
        }
    };
}
"""


async def build_stealth_context(playwright) -> BrowserContext:
    """
    Запускает Persistent Chrome Context с полным антидетект-стелсом.

    Использует реальный профиль Chrome пользователя:
    - Сохранённые куки и сессия Facebook
    - Случайный User-Agent из пула Chrome 128–131
    - Случайный Viewport (4 реалистичных размера)
    - Все аргументы против обнаружения автоматизации
    """
    if not CHROME_USER_DATA_DIR:
        raise ValueError(
            "❌ CHROME_USER_DATA_DIR не задан в .env!\n"
            "   Пример (Windows): "
            r"C:\Users\Name\AppData\Local\Google\Chrome\User Data"
        )

    profile_path = Path(CHROME_USER_DATA_DIR)
    if not profile_path.exists():
        log.warning(
            f"⚠️  Профиль не найден: {profile_path}\n"
            "   Playwright создаст новый. Для лучшей защиты используйте реальный профиль."
        )

    viewport = random.choice(_VIEWPORTS)
    user_agent = random.choice(_USER_AGENTS)

    log.info(f"🌐 Viewport: {viewport['width']}×{viewport['height']}")
    log.info(f"🔑 User-Agent: {user_agent[:72]}...")
    log.info(f"🌍 Locale: {LOCALE} / TZ: {TIMEZONE}")

    context: BrowserContext = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(CHROME_USER_DATA_DIR),
        headless=HEADLESS,
        viewport=viewport,
        user_agent=user_agent,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        geolocation=None,
        permissions=[],
        java_script_enabled=True,
        accept_downloads=False,
        ignore_https_errors=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-notifications",
            "--disable-popup-blocking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            f"--window-size={viewport['width']},{viewport['height']}",
        ],
    )
    return context


async def apply_stealth_patches(page: Page) -> None:
    """
    Применяет полный набор stealth-патчей на страницу.
    Вызывать ПОСЛЕ создания страницы, ДО первого goto().
    """
    await stealth_async(page)
    await page.add_init_script(_STEALTH_JS)
    await page.set_extra_http_headers({
        "Accept-Language": ACCEPT_LANGUAGE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    })
    log.debug("🥷 Stealth-патчи применены.")
