-- ============================================================
--  sql/init.sql — Supabase: схема таблицы raw_posts
--
--  Запуск: Supabase Dashboard → SQL Editor → вставить и выполнить
--
--  Ключевые решения:
--  • source_hash UNIQUE  — контентный ключ, upsert-safe
--  • raw_json JSONB      — полный слепок события для отладки
--  • updated_at trigger  — автоматически при UPDATE
-- ============================================================

-- ── Таблица сырых постов/событий ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_posts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Дедупликация (UNIQUE — гарантирует idempotent upsert)
    source_hash     TEXT        NOT NULL UNIQUE,

    -- Источник
    post_url        TEXT,
    group_url       TEXT,
    group_name      TEXT,

    -- Данные события (из LLM)
    title           TEXT,
    event_type      TEXT,
    date_raw        TEXT,
    date_normalized DATE,         -- NULL если не удалось распарсить
    location        TEXT,
    description     TEXT,
    contact         TEXT,
    confidence      FLOAT,
    source          TEXT,         -- 'text' | 'vision'

    -- Метаданные поста
    post_author     TEXT,
    post_date       TEXT,
    image_urls      TEXT,         -- ';'-separated CDN URLs

    -- Время скрейпинга
    scraped_at      TIMESTAMPTZ,

    -- Полный JSON события (для отладки и реprocessing)
    raw_json        JSONB,

    -- Системные
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Индексы ───────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_raw_posts_group_url
    ON raw_posts (group_url);

CREATE INDEX IF NOT EXISTS idx_raw_posts_date_normalized
    ON raw_posts (date_normalized)
    WHERE date_normalized IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raw_posts_event_type
    ON raw_posts (event_type);

CREATE INDEX IF NOT EXISTS idx_raw_posts_scraped_at
    ON raw_posts (scraped_at DESC);

-- ── Trigger: updated_at ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_raw_posts_updated_at ON raw_posts;

CREATE TRIGGER trg_raw_posts_updated_at
    BEFORE UPDATE ON raw_posts
    FOR EACH ROW
    EXECUTE FUNCTION _set_updated_at();

-- ── Row Level Security (рекомендуется для production) ─────────────────────
-- Включить RLS и разрешить только service_role:
--
-- ALTER TABLE raw_posts ENABLE ROW LEVEL SECURITY;
--
-- CREATE POLICY "service_role only" ON raw_posts
--   USING (auth.role() = 'service_role');
