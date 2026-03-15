-- ============================================================
--  sql/create_fb_events.sql — Таблица для постов из Facebook-групп
--
--  Отдельная от основной events-таблицы.
--  Запуск: Supabase Dashboard → SQL Editor → выполнить
-- ============================================================

CREATE TABLE IF NOT EXISTS fb_events (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Основные поля события
    title            TEXT        NOT NULL,
    date             DATE,                   -- NULL если не удалось распарсить
    time             TEXT,                   -- "19:00", "15:00–17:00" и т.д.
    location         TEXT,
    description      TEXT,
    registration_url TEXT,

    -- Источник
    source_url       TEXT        UNIQUE,     -- URL поста Facebook (для дедупликации)
    group_url        TEXT,
    group_name       TEXT,
    post_author      TEXT,
    image_url        TEXT,                   -- первое изображение поста

    -- Метаданные
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индекс для быстрого поиска по дате
CREATE INDEX IF NOT EXISTS idx_fb_events_date
    ON fb_events (date)
    WHERE date IS NOT NULL;

-- Индекс для поиска по группе
CREATE INDEX IF NOT EXISTS idx_fb_events_group_url
    ON fb_events (group_url);

-- Индекс для поиска по дате создания
CREATE INDEX IF NOT EXISTS idx_fb_events_scraped_at
    ON fb_events (scraped_at DESC);

-- Комментарий к таблице
COMMENT ON TABLE fb_events IS
    'Мероприятия, извлечённые из Facebook-групп через fb-scraper + Ollama OCR';
COMMENT ON COLUMN fb_events.source_url IS
    'URL поста Facebook — уникальный ключ для дедупликации';
