# ROADMAP.md

## Принцип приоритизации

Каждая фаза должна усиливать core loop:

```
запрос → n8n workflow → валидация → исполнение → repair → подтверждение
```

Если фича не делает этот цикл быстрее, точнее или надёжнее — она ждёт.

---

## Фаза 0: Завершение Windows-установки

**Статус:** в процессе тестирования

**Контекст:**
- Runtime собран, залит в GitHub Releases
- Installer пересобран после исправления бага с `\\?\` путями
- Финальная сборка готова к тестированию на Azure VM

**Что осталось:**
- [ ] Провести полный тест установки на чистой Windows VM
- [ ] Проверить: скачивание runtime, распаковка, запуск n8n, запуск backend
- [ ] Проверить корректность путей (без `\\?\` проблем)
- [ ] Подтвердить работоспособность end-to-end (UI → brain → n8n → результат)

**Блокирует:** все последующие фазы

---

## Фаза 1: Uninstaller — чистое удаление

**Связь с core loop:** installer reliability (приоритет #1 в CLAUDE.md)

### 1.1 Флаг `installed_by_agent`

При установке записывать в `%APPDATA%/Agent n8On/config.json`:

```json
{
  "installed_by_agent": {
    "ollama": true,
    "nodejs": true,
    "n8n": true
  }
}
```

Если компонент уже был установлен до агента — `false`.

### 1.2 Диалог при удалении

В NSIS uninstaller показать диалог:

```
Удалить также Ollama и скачанные AI-модели?
Это освободит примерно X ГБ.
[Да] [Нет, оставить]
```

### 1.3 Логика удаления

**Всегда удалять:**
- `%APPDATA%/Agent n8On/`
- `%LOCALAPPDATA%/Agent n8On/`

**По запросу пользователя (только если `installed_by_agent == true`):**
- Остановить процесс Ollama (`taskkill /F /IM ollama.exe`)
- Запустить Ollama silent uninstaller или удалить папку
- Удалить `~/.ollama/models/` (модели)
- Удалить Node.js (только если установлен агентом)
- `npm uninstall -g n8n`

**Никогда не удалять**, если компонент был до агента.

### 1.4 Задачи

- [ ] Добавить запись `installed_by_agent` в installer
- [ ] Добавить диалог в NSIS uninstaller
- [ ] Реализовать логику условного удаления
- [ ] Расчёт освобождаемого пространства для отображения в диалоге
- [ ] Тестирование на Windows VM

---

## Фаза 2: Error-Correction Memory ("Грабли")

**Связь с core loop:** repair loop quality (приоритет #4 в CLAUDE.md)

### Идея

При каждом успешном repair — логировать пару `ошибка → исправление`.
При следующем repair — сначала проверять "грабли" на совпадение.

### Реализация

1. Хранилище: SQLite или JSON-файл в `/memory/error_corrections.json`
2. Формат записи:
   ```json
   {
     "error_pattern": "Cannot read property 'json' of undefined",
     "node_type": "HttpRequest",
     "fix_applied": "Changed responseFormat from 'string' to 'json'",
     "success_count": 3,
     "last_used": "2026-03-15"
   }
   ```
3. Интеграция: в `brain/error_interpreter.py` добавить поиск по базе перед LLM-анализом
4. Порог доверия: применять автоматически, если `success_count >= 3`

### Задачи

- [ ] Определить схему хранения (JSON vs SQLite)
- [ ] Реализовать запись при успешном repair
- [ ] Реализовать поиск по базе в error_interpreter
- [ ] Добавить логирование применения известного решения
- [ ] Тестирование на реальных сценариях repair

---

## Фаза 3: Self-Growing Library (авто-шаблоны)

**Связь с core loop:** ускоряет генерацию, повышает точность

### Идея

При успешном завершении workflow (подтверждение пользователя) — сохранять очищенный шаблон для повторного использования.

### Реализация

1. **Триггер:** user confirmation → экспорт workflow JSON
2. **Key Stripping:**
   - Regex по полям `credentials`, `password`, `apiKey`, `token`, `secret`
   - Замена значений на `{{USER_KEY_REQUIRED}}`
   - Удаление `staticData` (содержит runtime-состояние)
3. **Хранение:** `/user_data/library/` с метаданными:
   ```json
   {
     "original_request": "Отправляй мне погоду в Telegram каждое утро",
     "nodes_used": ["Cron", "HttpRequest", "Telegram"],
     "created": "2026-03-15",
     "reuse_count": 0
   }
   ```
4. **Поиск:** при новом запросе — fuzzy match по `original_request` и `nodes_used`
5. **Приоритет:** найденный шаблон адаптируется, а не генерируется с нуля

### Задачи

- [ ] Реализовать Key Stripping (regex + поиск по credentials)
- [ ] Реализовать сохранение при user confirmation
- [ ] Реализовать поиск по библиотеке шаблонов
- [ ] Интегрировать в workflow_generator (шаблон как основа)
- [ ] Тестирование: создать workflow → подтвердить → повторить запрос → убедиться, что шаблон используется

---

## Фаза 4: Golden Templates (ручная курация)

**Связь с core loop:** уменьшает ошибки генерации для сложных нод

### Идея

Создать эталонные JSON-структуры для самых проблемных нод n8n.

### Целевые ноды (топ-20)

Сложные/часто ломающиеся:
1. Google Sheets (OAuth + scopes + range format)
2. Gmail (MIME, attachments, labels)
3. HTTP Request (auth types, pagination, binary)
4. Webhook (response modes, binary data)
5. Postgres/MySQL (parameterized queries, connection pooling)
6. Telegram Bot (keyboards, file uploads, callbacks)
7. Slack (blocks, threads, file sharing)
8. Code node (sandboxing, $input vs $json)
9. IF/Switch (expression syntax v1.0+)
10. Merge (modes: append, combine, multiplex)
11. Set (dot notation, type coercion)
12. Function (deprecated vs Code node migration)
13. Airtable (field types, linked records)
14. S3/MinIO (presigned URLs, multipart)
15. OpenAI/Claude (streaming, function calling)
16. Cron/Schedule (timezone handling)
17. RSS Feed (parsing edge cases)
18. XML (namespaces, attributes)
19. Wait (webhook resume vs timer)
20. Error Trigger (workflow error handling patterns)

### Формат шаблона

```json
{
  "node_type": "n8n-nodes-base.googleSheets",
  "display_name": "Google Sheets",
  "common_errors": ["Invalid range", "Permission denied"],
  "required_fields": ["operation", "sheetId", "range"],
  "template": { ... },
  "notes": "Range must be in A1 notation. OAuth2 scope must include spreadsheets."
}
```

### Хранение

`/skills/templates/golden/` — отдельные JSON-файлы по нодам.

### Задачи

- [ ] Проанализировать текущие recipes в `n8n_recipes.py` (21K строк) — что уже покрыто
- [ ] Создать golden templates для первых 10 нод
- [ ] Интегрировать в workflow_generator
- [ ] Создать golden templates для нод 11-20
- [ ] Документировать формат для будущих контрибьюторов

---

## Фаза 5: RAG по документации n8n (Context Injection)

**Связь с core loop:** точность генерации для редких нод

**Условие запуска:** только если фазы 2-4 не дают достаточной точности.

### Риски

- Новая зависимость (ChromaDB/FAISS) усложняет установку
- Нужно поддерживать актуальность индекса при обновлениях n8n
- Увеличивает размер дистрибутива

### Предварительный план

1. Выбор: FAISS (легче, без сервера) vs ChromaDB (удобнее API)
2. Индексация: официальная документация n8n по нодам
3. Запрос: пользователь упоминает ноду → подтягиваются релевантные фрагменты
4. Интеграция: фрагменты добавляются в промпт перед генерацией

### Альтернатива (проще)

Вместо полного RAG — статический JSON-индекс с ключевыми правилами для каждой ноды. По сути, расширенные golden templates. Это не требует векторной БД.

### Задачи

- [ ] Оценить, достаточно ли golden templates
- [ ] Если нет — выбрать между FAISS и статическим индексом
- [ ] Реализовать индексацию
- [ ] Интегрировать в brain layer
- [ ] Тестирование на редких нодах

---

## Фаза 6: Plugin Architecture (будущее)

**Условие запуска:** наличие пользовательской базы и запросов на расширение.

### Текущее состояние

`/skills/instructions/` уже работает как простая plugin-система:
- `debug_n8n_workflow.md`
- `create_complex_workflow.md`
- `handle_api_errors.md`
- `learned_lessons.md`

### Когда формализовать

- Когда появятся внешние контрибьюторы
- Когда текущей системы skills станет недостаточно
- Когда будет clear demand на специализированные плагины (Facebook Ads, SAP и т.д.)

### Предварительный план

1. Формализовать формат плагина (JSON-схема)
2. Добавить автозагрузку из `/plugins/`
3. Валидация плагинов при загрузке
4. Документация для контрибьюторов

---

## Не планируется в ближайшее время

| Фича | Причина отложения |
|-------|-------------------|
| Marketplace плагинов | Нет пользовательской базы |
| Облачный хостинг | Противоречит "one-click local setup" |
| Enterprise-плагины | Преждевременная монетизация |
| Мультимодельный роутинг | Текущая архитектура Ollama + API достаточна |

---

## Метрики успеха по фазам

| Фаза | Метрика |
|-------|---------|
| 0 | Установка на чистую Windows работает end-to-end |
| 1 | Чистое удаление, пользовательские компоненты не затронуты |
| 2 | Повторные ошибки исправляются быстрее (измерить: кол-во repair-итераций) |
| 3 | Повторные запросы генерируются быстрее и точнее |
| 4 | Уменьшение ошибок генерации для сложных нод |
| 5 | Точность генерации для редких нод > 80% |
| 6 | Внешние контрибьюторы могут добавлять плагины без изменения ядра |
