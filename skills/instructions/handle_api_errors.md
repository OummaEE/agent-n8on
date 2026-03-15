# Инструкция: Обработка ошибок API

## Типичные HTTP ошибки и что делать

| Код | Название | Причина | Действие |
|---|---|---|---|
| 400 | Bad Request | Неверные параметры запроса | Проверь тело запроса, типы полей, обязательные параметры |
| 401 | Unauthorized | Неверный или отсутствующий API key | Обнови токен, проверь заголовок Authorization |
| 403 | Forbidden | Нет прав на ресурс | Проверь scope/permissions токена, IP whitelist |
| 404 | Not Found | Ресурс не существует | Проверь URL, убедись что ID корректный |
| 409 | Conflict | Ресурс уже существует | Используй PUT вместо POST, или проверь на существование перед созданием |
| 422 | Unprocessable Entity | Ошибка валидации данных | Прочитай `errors` в ответе, исправь конкретные поля |
| 429 | Too Many Requests | Rate limit превышен | Реализуй exponential backoff (см. ниже) |
| 500 | Internal Server Error | Ошибка на стороне API | Повтори с задержкой, логируй, уведоми при persisting |
| 502/503 | Bad Gateway / Unavailable | API временно недоступен | Повтори с задержкой, circuit breaker |

## Rate Limiting — как определить и обработать

**Признаки rate limiting:**
- HTTP 429
- Заголовок `Retry-After: 60` (секунды до следующего запроса)
- Заголовок `X-RateLimit-Remaining: 0`
- Сообщение "rate limit exceeded" / "too many requests"

**Exponential Backoff в Code ноде:**
```javascript
// Используй в Code node с retry логикой
const delays = [1000, 2000, 4000, 8000]; // ms
let lastError;

for (let attempt = 0; attempt < delays.length; attempt++) {
  try {
    const response = await this.helpers.request({
      method: 'GET',
      url: '{{ $json.url }}',
      headers: {'Authorization': 'Bearer {{ $credentials.apiKey }}'}
    });
    return [{json: JSON.parse(response)}];
  } catch (error) {
    lastError = error;
    if (error.statusCode === 429 || error.statusCode >= 500) {
      await new Promise(r => setTimeout(r, delays[attempt]));
      continue;
    }
    throw error; // не повторяем 4xx (кроме 429)
  }
}
throw lastError;
```

## Retry логика — когда повторять, когда сдаваться

**Повторять:**
- 429 Too Many Requests (после Retry-After задержки)
- 500, 502, 503 (временные ошибки сервера)
- Network timeout (connection reset, ECONNRESET)

**НЕ повторять:**
- 400 Bad Request (неверные данные — повтор не поможет)
- 401 Unauthorized (токен неверный — нужно обновить)
- 403 Forbidden (нет прав — повтор не поможет)
- 404 Not Found (ресурс не существует)
- 422 Unprocessable Entity (ошибка валидации)

**Когда сдаваться:**
- После 3 попыток (MAX_RETRIES = 3)
- Если суммарное время > 30 секунд
- Если 401/403 (не временные ошибки)

**Формат ошибки для пользователя:**
```
API Error: {statusCode} {message}
URL: {url}
Attempts: {n}/3
Suggestion: {action}
```

## Специальные случаи

### GitHub API
- Rate limit: 5000 req/hour (authenticated), 60/hour (anonymous)
- Заголовок: `X-RateLimit-Reset` (unix timestamp когда сброс)

### OpenAI API
- Rate limit на токены/минуту и запросы/минуту
- Проверяй `error.type == "rate_limit_error"`

### Webhook timeouts
- n8n webhook ожидает ответ 30 секунд
- Если обработка дольше — используй async pattern: ответь 200 сразу, обрабатывай в фоне
