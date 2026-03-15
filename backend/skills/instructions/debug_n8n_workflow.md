# Инструкция: Отладка n8n Workflow

## 1. Получить execution_id

```
GET /executions?workflowId={id}&limit=5
```
Последний execution — первый в списке. Поле `id` — это `execution_id`.

Альтернативно: пользователь может сообщить execution_id напрямую.
Паттерны в тексте: `execution 12345`, `execution_id=abc`, `run_id=xyz`, `выполнение exec-123`.

## 2. Найти упавший узел через n8n API

```
GET /executions/{execution_id}
```

Ответ содержит:
- `data.status` — "success" | "error" | "crashed" | "waiting"
- `data.stoppedAt` — когда остановился
- `data.data.resultData.runData` — объект с результатами каждого узла

Упавший узел имеет `error` поле вместо `data`:
```json
{
  "NodeName": [{
    "error": {
      "message": "...",
      "description": "...",
      "httpCode": "404"
    }
  }]
}
```

## 3. Читать и интерпретировать ошибку

| Тип ошибки | Признак | Причина |
|---|---|---|
| HTTP 4xx | `httpCode` в error | Неправильный URL, auth, параметры |
| Expression error | `message` содержит "Cannot read" / "undefined" | Ссылка на несуществующее поле |
| Timeout | `message` содержит "timeout" | Медленный API, нет retry |
| Auth error | httpCode 401/403 | Неверный API key / токен |
| JSON parse error | `message` содержит "JSON" | API вернул не-JSON ответ |

## 4. Применить фикс к конкретному узлу

```
PUT /workflows/{workflowId}
```

Payload: полный workflow JSON с изменёнными `parameters` нужного узла.

**Правила безопасного патча:**
- Менять только `parameters` нужного узла, не трогать остальные
- Сохранять `typeVersion`, `id`, `position` без изменений
- Не добавлять поля, которых нет в исходном шаблоне

## 5. Перезапустить workflow и проверить результат

```
POST /workflows/{workflowId}/run
```

Дождаться completion:
```
GET /executions/{new_execution_id}
```

Проверять `data.status == "success"` и что все узлы в `runData` имеют данные без `error`.

**Максимум попыток:** 3 (MAX_RETRIES). После третьей неудачи — сообщить пользователю и предложить ручное исправление.
