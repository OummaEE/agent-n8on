# CHANGELOG

## [4.0.0] — 2026-02-26

### Production Hardening

- **CLI entrypoint** (`main.py`):
  - Full `argparse` interface: `--groups`, `--force`, `--no-supabase`, `--output`, `--headless`, `--log-level`, `--log-file`
  - CLI args patched into `os.environ` **before** scraper module imports (config.py reads env at import time)
  - Configurable log level + log file via flags
  - Silenced noisy external loggers: `playwright`, `asyncio`, `httpx`, `httpcore`
  - n8n-ready: `python "C:\path\to\main.py" --headless --force`

- **Supabase integration** (`scraper/supabase_client.py` — new file):
  - Lazy-init Supabase client (skipped entirely if `SUPABASE_URL`/`SUPABASE_KEY` not set)
  - Batch **upsert** with `ON CONFLICT (source_hash)` — idempotent, safe to re-run
  - Runs sync SDK in `asyncio.to_thread()` — no event-loop blocking
  - `is_configured()` guard: if not set → only CSV, no error

- **`source_hash` deduplication** (`scraper/normalize.py`):
  - New `source_hash(event)` function: SHA-256 of `post_url` (primary) or content fingerprint (fallback)
  - Added to `enrich_event()` alongside existing `_dedup_key`
  - Used as `UNIQUE KEY` in Supabase `raw_posts` table

- **Supabase DDL** (`sql/init.sql` — new file):
  - `raw_posts` table with `source_hash TEXT NOT NULL UNIQUE`
  - Indexes on `group_url`, `date_normalized`, `event_type`, `scraped_at`
  - `updated_at` trigger for automatic timestamp updates
  - RLS notes included in comments

- **LLM retry with exponential backoff** (`scraper/llm_text.py`, `scraper/llm_vision.py`):
  - `_llm_call_with_retry()` — handles: `RateLimitError` (30s×N), `APITimeoutError`/`APIConnectionError` (5s×N), `APIStatusError` 5xx (10s×N)
  - `_vision_call_with_retry()` — longer delays: rate limit 45s×N, timeout 8s×N, 5xx 15s×N
  - 4xx errors (auth/bad request) → immediate fail, no retry
  - Configured via `LLM_MAX_RETRIES` (default 3)

- **`source_hash` in CSV** (`scraper/storage.py`):
  - Added `"source_hash"` to `CSV_FIELDNAMES`
  - `SessionMetrics` now tracks `supabase_upserted` count
  - `print_summary()` reports Supabase upsert status

### Config Changes
- Added: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_TABLE` (default `raw_posts`)
- Added: `LLM_MAX_RETRIES` (default `3`)

### New Files
- `scraper/supabase_client.py` — Supabase lazy client + batch upsert
- `sql/init.sql` — PostgreSQL DDL for `raw_posts` table

---

## [3.1.0] — 2026-02-26

### Fixes & Improvements

- **POSTS_PER_GROUP** (`config.py`):
  - Enforced range **15–20** (`max(15, min(value, 20))`). Previously only capped at 20.

- **CDN filter** (`fb_collect.py`):
  - Switched `_EXTRACT_POSTS_JS` string to raw string (`r"""..."""`) to eliminate Python `SyntaxWarning` about JS regex escape sequences.
  - Strict blocklist already in place: excludes avatars (`p40x40`), emoji, spinners, rsrc.php.

- **Vision analysis** (`llm_vision.py`):
  - Now analyses up to **`MAX_VISION_IMAGES_PER_POST=2`** images per candidate post (was: always only 1st image).
  - Stops checking further images once a confident result is found.
  - Logs each image attempt with `img 1/2`, `img 2/2` notation.
  - Imported `MAX_VISION_IMAGES_PER_POST` from `config.py` — single source of truth.

- **Run guard** (`config.py` + `run.py`):
  - Added `FORCE_RUN` env variable (default `false`) to bypass the 22h daily limit during debugging.
  - When `FORCE_RUN=true` a clear warning is emitted in the log.

- **Statistics logging** (`storage.py`):
  - `GroupStats.add_error()` now immediately logs the error (no silent accumulation).
  - `SessionMetrics` gained **per-type error counters**:
    - `errors_navigation` — HTTP errors, auth wall, timeouts
    - `errors_scraping`   — `collect_posts` failures
    - `errors_llm_text`   — LLM text-analysis failures
    - `errors_llm_vision` — vision-analysis failures
    - `errors_other`      — unexpected exceptions
  - `print_summary()` now outputs a **detailed error breakdown** section.
  - Added `total_errors` property to `SessionMetrics`.

### Config Changes
- Added: `MAX_VISION_IMAGES_PER_POST = 2` (replaces implicit hard-code)
- Added: `FORCE_RUN` (bool, default `false`)
- Changed: `POSTS_PER_GROUP` now enforced in `[15, 20]` range

---

## [3.0.0] — 2026-02-26

### Architecture
- Split monolithic `main.py` into `scraper/` package:
  - `config.py`      — all settings from .env, typed constants
  - `browser.py`     — Persistent Context + full stealth patches
  - `human.py`       — smooth_scroll, mouse moves, delays
  - `fb_collect.py`  — navigation + post collection + image extraction
  - `llm_text.py`    — OpenAI text analysis, batch processing
  - `llm_vision.py`  — qwen2.5vl vision analysis for image candidates
  - `normalize.py`   — date normalization (sv-SE), dedup key, enrichment
  - `storage.py`     — CSV (16 cols), state.json, session metrics
  - `run.py`         — full pipeline orchestrator

### Features Added
- **image_urls extraction** (fb_collect.py):
  - `img[src]` with scontent/fbcdn/fbsbx filter
  - `background-image` CSS computed style scan
  - Dedup + limit to 2 per post (strict CDN blocklist)
  - Stored as `;`-separated string in CSV

- **Vision pipeline** (llm_vision.py):
  - Triggers ONLY when: text LLM → is_event=false AND post has images
  - Model: `qwen2.5vl` (configurable via VISION_MODEL)
  - Confidence threshold: `VISION_CONFIDENCE_THRESHOLD=0.6`
  - Source field: `"vision"` vs `"text"` in CSV

- **Deduplication overhaul** (normalize.py + storage.py):
  - Primary key: `post_url`
  - Fallback: `md5(group_url + title_norm + date_raw + location_norm)`

- **state.json** (storage.py):
  - Per-group: `last_run_at`, `seen_post_urls` (max 500, FIFO)
  - Early stop signal in JS: stops scrolling on first known post_url
  - Saved after every group (crash-safe)

- **Locale → Sweden**: `sv-SE` / `Europe/Stockholm`

- **Session metrics**: GroupStats + SessionMetrics with per-group breakdown

- **CSV 16 columns**: `date_normalized`, `source`, `image_urls`

### Config Changes
- Added: `VISION_MODEL`, `VISION_CONFIDENCE_THRESHOLD`
- Added: `LOCALE`, `TIMEZONE`, `ACCEPT_LANGUAGE`, `STATE_FILE`
- Changed: locale default → `sv-SE`, TZ → `Europe/Stockholm`

---

## [2.0.0] — 2026-02-26
- Multi-group scraping via `GROUP_URLS`
- LLM text analysis (gpt-5-mini)
- 13-column CSV output
- Added openai, PyYAML dependencies

## [1.0.0] — 2026-02-26
- Initial: single URL event scraper
- Playwright + playwright-stealth + Persistent Context
- 4-column CSV (title, date, location, url)

