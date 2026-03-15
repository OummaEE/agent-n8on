-- ============================================================
--  sql/create_events_parsed.sql — Таблица для постов из Facebook-групп
--
--  Запускается автоматически через setup_supabase.py (psycopg2)
--  или вручную: Supabase Dashboard → SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS events_parsed (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Основные поля события
    title            TEXT        NOT NULL,
    date             DATE,                   -- NULL если не удалось распарсить
    time             TEXT,                   -- "19:00", "15:00–17:00" и т.д.
    location         TEXT,
    description      TEXT,
    registration_url TEXT,

    -- Источник (дедупликация по source_url)
    source_url       TEXT        UNIQUE,     -- URL поста Facebook
    group_url        TEXT,
    group_name       TEXT,
    post_author      TEXT,
    image_url        TEXT,                   -- первое изображение поста

    -- Метаданные
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индекс для быстрого поиска по дате
CREATE INDEX IF NOT EXISTS idx_events_parsed_date
    ON events_parsed (date)
    WHERE date IS NOT NULL;

-- Индекс для поиска по группе
CREATE INDEX IF NOT EXISTS idx_events_parsed_group_url
    ON events_parsed (group_url);

-- Индекс для поиска по дате создания
CREATE INDEX IF NOT EXISTS idx_events_parsed_scraped_at
    ON events_parsed (scraped_at DESC);

COMMENT ON TABLE events_parsed IS
    'Мероприятия, извлечённые из Facebook-групп через fb-scraper + Ollama';
COMMENT ON COLUMN events_parsed.source_url IS
    'URL поста Facebook — уникальный ключ для дедупликации';
