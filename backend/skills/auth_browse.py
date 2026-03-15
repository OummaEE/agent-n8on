"""
Skill: auth_browse
Description: Autonomous browser with saved logins, session cookies, click/navigate/type actions.
Runs its OWN Playwright Chromium — does NOT touch the user's Chrome.
Saves cookies/sessions to disk so you log in once, then it remembers.

Credentials stored in .env:
  SITE_CREDENTIALS={"tryholo.ai": {"email": "...", "password": "..."}, "another.com": {...}}

Or per-site:
  HOLO_EMAIL=jane@example.com
  HOLO_PASSWORD=secret123

Sessions saved to: memory/browser_sessions/ (cookies + localStorage)

Author: Jane's Agent Builder
"""

import os
import json
import time as _time
import re

SKILL_NAME = "auth_browse"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Smart browser: auto-login, click links, fill forms, navigate pages, save sessions"

SKILL_TOOLS = {
    "web_login": {
        "description": "Log into a website and save the session. After login, use web_action to navigate.",
        "args": {
            "url": "Login page URL (e.g. https://tryholo.ai/login)",
            "email": "Email/username (optional if stored in .env)",
            "password": "Password (optional if stored in .env)",
            "email_selector": "CSS selector for email field (default: auto-detect)",
            "password_selector": "CSS selector for password field (default: auto-detect)",
            "submit_selector": "CSS selector for submit button (default: auto-detect)"
        },
        "example": '{"tool": "web_login", "args": {"url": "https://tryholo.ai/login"}}'
    },
    "web_action": {
        "description": "Perform actions on a webpage: click links, extract text, fill forms, take screenshots. Uses saved session (no re-login needed).",
        "args": {
            "url": "URL to navigate to",
            "actions": "List of actions to perform in sequence. Each action is a string: click:selector, type:selector:text, screenshot, extract_text, extract:selector, scroll_down, scroll_up, wait:seconds, click_text:visible text, hover:selector, select:selector:value, press:key",
            "wait": "Wait seconds after page load (default 3)"
        },
        "example": '{"tool": "web_action", "args": {"url": "https://tryholo.ai/dashboard", "actions": ["wait:2", "extract_text", "screenshot"]}}'
    },
    "web_extract": {
        "description": "Quick extract: go to URL, grab all text content, return it. Uses saved session.",
        "args": {
            "url": "URL to extract text from",
            "selector": "Optional CSS selector to extract specific element"
        },
        "example": '{"tool": "web_extract", "args": {"url": "https://tryholo.ai/content-plan"}}'
    },
    "web_click_through": {
        "description": "Navigate through multiple pages: go to URL, find and click a link/button, extract the result page. Good for 'go to site, click Content Plan, show me what's there'.",
        "args": {
            "url": "Starting URL",
            "clicks": "List of things to click, in order. Can be CSS selectors or visible text. E.g. ['Content Plan', 'February 2026', '.export-btn']",
            "extract_after": "Extract text after all clicks (default true)"
        },
        "example": '{"tool": "web_click_through", "args": {"url": "https://tryholo.ai/dashboard", "clicks": ["Content Plan", "This Month"]}}'
    },
    "web_sessions": {
        "description": "Show saved browser sessions (which sites have stored cookies/logins)",
        "args": {},
        "example": '{"tool": "web_sessions", "args": {}}'
    }
}

# Paths
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS_DIR = os.path.join(AGENT_DIR, "memory", "browser_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def _get_domain(url: str) -> str:
    """Extract domain from URL"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split('/')[0]
    # Remove www. prefix
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def _session_path(domain: str) -> str:
    """Get session file path for a domain"""
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', domain)
    return os.path.join(SESSIONS_DIR, f"{safe_name}.json")


def _save_session(context, domain: str):
    """Save cookies from browser context"""
    try:
        cookies = context.cookies()
        path = _session_path(domain)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "domain": domain,
                "cookies": cookies,
                "saved_at": _time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  auth_browse: error saving session for {domain}: {e}")


def _load_session(context, domain: str) -> bool:
    """Load cookies into browser context"""
    path = _session_path(domain)
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)
            return True
    except Exception:
        pass
    return False


def _get_credentials(url: str) -> dict:
    """Get credentials for a URL from .env"""
    domain = _get_domain(url)
    env_path = os.path.join(AGENT_DIR, ".env")
    config = {}

    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    config[key.strip()] = val.strip().strip('"').strip("'")

    # Try JSON format: SITE_CREDENTIALS={"tryholo.ai": {"email": "...", "password": "..."}}
    creds_json = config.get("SITE_CREDENTIALS", "")
    if creds_json:
        try:
            all_creds = json.loads(creds_json)
            for site_domain, creds in all_creds.items():
                if site_domain in domain or domain in site_domain:
                    return creds
        except:
            pass

    # Try per-site format: HOLO_EMAIL, HOLO_PASSWORD
    domain_prefix = domain.split('.')[0].upper()
    email = config.get(f"{domain_prefix}_EMAIL", "")
    password = config.get(f"{domain_prefix}_PASSWORD", "")
    if email and password:
        return {"email": email, "password": password}

    return {}


def _create_context(pw):
    """Create a stealth browser context"""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='Europe/Stockholm',
        java_script_enabled=True
    )

    # Apply stealth if available
    try:
        from playwright_stealth import stealth_sync
        page = context.new_page()
        stealth_sync(page)
        return browser, context, page
    except ImportError:
        page = context.new_page()
        return browser, context, page


def _execute_action(page, action: str, domain: str) -> str:
    """Execute a single action on the page"""
    action = action.strip()
    result = ""

    try:
        if action == "extract_text":
            text = page.inner_text("body")
            result = text[:8000]

        elif action.startswith("extract:"):
            selector = action[8:].strip()
            elements = page.query_selector_all(selector)
            texts = [el.inner_text() for el in elements]
            result = "\n".join(texts)[:5000]

        elif action == "screenshot":
            desktop = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
            shot_name = f"browse_{domain}_{_time.strftime('%Y%m%d_%H%M%S')}.png"
            shot_path = os.path.join(desktop, shot_name)
            page.screenshot(path=shot_path, full_page=True)
            result = f"Screenshot saved: {shot_path}"

        elif action.startswith("click:"):
            selector = action[6:].strip()
            page.click(selector, timeout=10000)
            page.wait_for_timeout(2000)
            result = f"Clicked: {selector}"

        elif action.startswith("click_text:"):
            text = action[11:].strip()
            # Try multiple strategies to find clickable text
            clicked = False
            for sel in [
                f'a:has-text("{text}")',
                f'button:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'text="{text}"',
                f':has-text("{text}")'
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        el.click(timeout=5000)
                        clicked = True
                        break
                except:
                    continue
            if clicked:
                page.wait_for_timeout(2000)
                result = f"Clicked text: '{text}'"
            else:
                result = f"Could not find clickable element with text: '{text}'"

        elif action.startswith("type:"):
            parts = action[5:].split(":", 1)
            if len(parts) == 2:
                selector, text = parts[0].strip(), parts[1].strip()
                page.fill(selector, text, timeout=10000)
                result = f"Typed into {selector}"
            else:
                result = "Error: type format is type:selector:text"

        elif action.startswith("hover:"):
            selector = action[6:].strip()
            page.hover(selector, timeout=10000)
            page.wait_for_timeout(1000)
            result = f"Hovered: {selector}"

        elif action.startswith("select:"):
            parts = action[7:].split(":", 1)
            if len(parts) == 2:
                selector, value = parts[0].strip(), parts[1].strip()
                page.select_option(selector, value, timeout=10000)
                result = f"Selected {value} in {selector}"

        elif action.startswith("press:"):
            key = action[6:].strip()
            page.keyboard.press(key)
            page.wait_for_timeout(500)
            result = f"Pressed key: {key}"

        elif action == "scroll_down":
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(1000)
            result = "Scrolled down"

        elif action == "scroll_up":
            page.evaluate("window.scrollBy(0, -window.innerHeight)")
            page.wait_for_timeout(1000)
            result = "Scrolled up"

        elif action.startswith("wait:"):
            seconds = int(action[5:].strip())
            page.wait_for_timeout(seconds * 1000)
            result = f"Waited {seconds}s"

        else:
            result = f"Unknown action: {action}"

    except Exception as e:
        result = f"Action error ({action}): {str(e)[:200]}"

    return result


def web_login(url: str, email: str = "", password: str = "",
              email_selector: str = "", password_selector: str = "",
              submit_selector: str = "") -> str:
    """Log into a website and save the session"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: Playwright not installed. Run: pip install playwright && playwright install chromium"

    domain = _get_domain(url)

    # Get credentials
    if not email or not password:
        creds = _get_credentials(url)
        email = email or creds.get("email", "")
        password = password or creds.get("password", "")

    if not email or not password:
        return (f"No credentials for {domain}.\n\n"
                f"Option 1: Pass email and password directly:\n"
                f'  {{"tool": "web_login", "args": {{"url": "{url}", "email": "your@email", "password": "pass"}}}}\n\n'
                f"Option 2: Add to .env:\n"
                f"  {domain.split('.')[0].upper()}_EMAIL=your@email.com\n"
                f"  {domain.split('.')[0].upper()}_PASSWORD=your_password\n\n"
                f"Option 3: JSON format in .env:\n"
                f'  SITE_CREDENTIALS={{"' + domain + '": {{"email": "your@email", "password": "pass"}}}}')

    with sync_playwright() as pw:
        browser, context, page = _create_context(pw)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Auto-detect login fields if selectors not provided
            if not email_selector:
                for sel in [
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[name="username"]',
                    'input[name="login"]',
                    'input[type="text"][autocomplete="email"]',
                    'input[type="text"][autocomplete="username"]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="Email" i]',
                    'input[type="text"]'
                ]:
                    try:
                        if page.locator(sel).first.is_visible(timeout=1000):
                            email_selector = sel
                            break
                    except:
                        continue

            if not password_selector:
                for sel in [
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[placeholder*="password" i]'
                ]:
                    try:
                        if page.locator(sel).first.is_visible(timeout=1000):
                            password_selector = sel
                            break
                    except:
                        continue

            if not email_selector or not password_selector:
                # Get page content for debugging
                text = page.inner_text("body")[:2000]
                browser.close()
                return (f"Could not find login fields on {url}\n"
                        f"Email selector: {email_selector or 'NOT FOUND'}\n"
                        f"Password selector: {password_selector or 'NOT FOUND'}\n\n"
                        f"Page content:\n{text}\n\n"
                        f"Specify selectors manually:\n"
                        f'  "email_selector": "input[name=email]", "password_selector": "input[type=password]"')

            # Fill in credentials
            page.fill(email_selector, email, timeout=5000)
            page.wait_for_timeout(500)
            page.fill(password_selector, password, timeout=5000)
            page.wait_for_timeout(500)

            # Find and click submit
            if not submit_selector:
                for sel in [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Log in")',
                    'button:has-text("Sign in")',
                    'button:has-text("Login")',
                    'button:has-text("Войти")',
                    'button:has-text("Enter")',
                    'form button',
                    '.login-btn',
                    '#login-btn'
                ]:
                    try:
                        if page.locator(sel).first.is_visible(timeout=1000):
                            submit_selector = sel
                            break
                    except:
                        continue

            if submit_selector:
                page.click(submit_selector, timeout=5000)
            else:
                # Try pressing Enter
                page.keyboard.press("Enter")

            # Wait for navigation
            page.wait_for_timeout(5000)

            # Check if login succeeded
            current_url = page.url
            title = page.title()

            # Save session
            _save_session(context, domain)

            browser.close()
            return (f"Login to {domain}:\n"
                    f"  Page: {title}\n"
                    f"  URL: {current_url}\n"
                    f"  Session saved. Use web_action or web_extract to browse — no re-login needed.")

        except Exception as e:
            browser.close()
            return f"Login error: {str(e)[:500]}"


def web_action(url: str, actions: list = None, wait: int = 3) -> str:
    """Perform actions on a webpage using saved session"""
    if actions is None:
        actions = ["extract_text"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: Playwright not installed."

    domain = _get_domain(url)

    with sync_playwright() as pw:
        browser, context, page = _create_context(pw)

        # Load saved session
        session_loaded = _load_session(context, domain)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(wait * 1000)

            title = page.title()
            current_url = page.url

            results = [
                f"Page: {title}",
                f"URL: {current_url}",
                f"Session: {'restored' if session_loaded else 'new (not logged in)'}",
                ""
            ]

            for action in actions:
                if isinstance(action, str):
                    action_result = _execute_action(page, action, domain)
                    if action_result:
                        results.append(action_result)

            # Save updated session (new cookies etc.)
            _save_session(context, domain)

            browser.close()
            return "\n".join(results)

        except Exception as e:
            browser.close()
            return f"Error: {str(e)[:500]}"


def web_extract(url: str, selector: str = "") -> str:
    """Quick extract text from a page (uses saved session)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: Playwright not installed."

    domain = _get_domain(url)

    with sync_playwright() as pw:
        browser, context, page = _create_context(pw)
        _load_session(context, domain)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            title = page.title()

            if selector:
                elements = page.query_selector_all(selector)
                text = "\n\n".join([el.inner_text() for el in elements])
            else:
                text = page.inner_text("body")

            _save_session(context, domain)
            browser.close()

            text = text[:8000]
            return f"Title: {title}\nURL: {url}\n\n{text}"

        except Exception as e:
            browser.close()
            return f"Error: {str(e)[:500]}"


def web_click_through(url: str, clicks: list = None, extract_after: bool = True) -> str:
    """Navigate through pages by clicking links/buttons in sequence"""
    if not clicks:
        return "No clicks specified. Provide a list of link texts or CSS selectors."

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: Playwright not installed."

    domain = _get_domain(url)

    with sync_playwright() as pw:
        browser, context, page = _create_context(pw)
        _load_session(context, domain)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            results = [f"Starting at: {page.title()} ({page.url})"]

            for i, click_target in enumerate(clicks):
                click_target = click_target.strip()
                result = _execute_action(page, f"click_text:{click_target}", domain)

                # If click_text failed, try as CSS selector
                if "Could not find" in result:
                    result = _execute_action(page, f"click:{click_target}", domain)

                results.append(f"Step {i + 1}: {result}")
                results.append(f"  Now at: {page.title()} ({page.url})")

            # Extract final page
            if extract_after:
                text = page.inner_text("body")[:6000]
                results.append(f"\n=== Final page content ===\n{text}")

            _save_session(context, domain)
            browser.close()
            return "\n".join(results)

        except Exception as e:
            browser.close()
            return f"Error: {str(e)[:500]}"


def web_sessions() -> str:
    """Show saved browser sessions"""
    lines = ["=== Saved Browser Sessions ==="]

    if not os.path.exists(SESSIONS_DIR):
        lines.append("No sessions saved yet.")
        return "\n".join(lines)

    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.json')]

    if not sessions:
        lines.append("No sessions saved yet.")
        lines.append("Use web_login to log into a site — session will be saved automatically.")
        return "\n".join(lines)

    for sf in sorted(sessions):
        try:
            with open(os.path.join(SESSIONS_DIR, sf), 'r') as f:
                data = json.load(f)
            domain = data.get("domain", sf[:-5])
            cookies_count = len(data.get("cookies", []))
            saved_at = data.get("saved_at", "unknown")
            lines.append(f"  {domain}: {cookies_count} cookies (saved: {saved_at})")
        except:
            lines.append(f"  {sf}: error reading")

    lines.append(f"\nTotal: {len(sessions)} saved session(s)")
    lines.append("Sessions are used automatically when you browse the same domain.")
    return "\n".join(lines)


TOOLS = {
    "web_login": lambda args: web_login(
        args.get("url", ""),
        args.get("email", ""), args.get("password", ""),
        args.get("email_selector", ""), args.get("password_selector", ""),
        args.get("submit_selector", "")
    ),
    "web_action": lambda args: web_action(
        args.get("url", ""),
        args.get("actions", ["extract_text"]),
        args.get("wait", 3)
    ),
    "web_extract": lambda args: web_extract(
        args.get("url", ""), args.get("selector", "")
    ),
    "web_click_through": lambda args: web_click_through(
        args.get("url", ""),
        args.get("clicks", []),
        args.get("extract_after", True)
    ),
    "web_sessions": lambda args: web_sessions(),
}
