# Controller Layer — Quick Reference

## 🚀 Быстрый старт

```bash
# 1. Установка
python install_controller.py

# 2. Тестирование
python test_controller.py

# 3. Запуск агента
python agent_v3.py
```

---

## 💬 Примеры команд

### ✅ Работают через Controller (быстро, без LLM)

#### Дубликаты
```
✅ "найди дубликаты в Downloads и удали старые"
✅ "почисти дубликаты в C:/Temp"
✅ "сканируй Downloads на дубли"
✅ [follow-up] "удали старые"
✅ [follow-up] "убери их"
```

#### Организация
```
✅ "организуй файлы в Documents по типам"
✅ "разложи файлы в Downloads"
✅ "сортируй C:/Temp по расширениям"
```

#### Диск
```
✅ "сколько места занято в Downloads"
✅ "анализ диска C:/"
✅ "статистика использования Documents"
```

#### Браузер
```
✅ "открой gmail.com"
✅ "зайди на https://mail.google.com"
```

### ❌ НЕ работают через Controller (передаются в LLM)

```
❌ "создай презентацию про AI"  → LLM (нет такого intent)
❌ "отправь письмо директору"   → LLM (email пока не поддерживается)
❌ "расскажи анекдот"           → LLM (не задача агента)
```

---

## 🎯 Supported Intents

| Intent | Keywords (RU) | Keywords (EN) | Example |
|--------|--------------|---------------|---------|
| `CLEAN_DUPLICATES_KEEP_NEWEST` | дубликат + удал/очист | duplicate + delete/clean | "найди дубликаты и удали" |
| `FIND_DUPLICATES_ONLY` | дубликат + найд/покаж | duplicate + find/show | "найди дубликаты" |
| `DELETE_OLD_DUPLICATES_FOLLOWUP` | удал стар/их | delete old/them | "удали старые" (после find) |
| `ORGANIZE_FOLDER_BY_TYPE` | организ/разложи | organize/sort | "организуй Documents" |
| `DISK_USAGE_REPORT` | диск/место | disk/space | "сколько места в C:/" |
| `BROWSE_WITH_LOGIN` | открой/зайди | browse/open | "открой gmail.com" |

---

## 🔍 Debugging

### Проверить что Controller загружен

```python
# В консоли после запуска agent_v3.py должно быть:
✅ Agent Controller Layer v1.0 initialized
```

### Если не видишь эту строку:

```bash
# Проверить наличие controller.py
ls controller.py

# Переустановить
python install_controller.py
```

### Посмотреть обработанные запросы

```python
# В консоли при обработке через controller:
🎯 Handled by Controller: Executed workflow 'CLEAN_DUPLICATES_KEEP_NEWEST'
```

### Если запрос ушёл в LLM (не в controller):

1. Проверить ключевые слова в `IntentClassifier.INTENTS`
2. Добавить нужные варианты формулировок
3. Или это норма (запрос не входит в поддерживаемые интенты)

---

## 🛠️ Расширение Controller

### Добавить новое намерение (пример: Email)

**1. Добавить в INTENTS (controller.py):**

```python
class IntentClassifier:
    INTENTS = {
        # ... existing intents ...
        
        "SEND_EMAIL_SIMPLE": {
            "keywords": {
                "ru": ["отправ письм", "email", "напиш письм"],
                "en": ["send email", "email to"]
            },
            "requires": ["recipient", "subject"],
            "workflow": "send_email"
        },
    }
```

**2. Добавить в classify() (controller.py):**

```python
def classify(self, user_message: str):
    # ... existing checks ...
    
    # Email intent
    if self._matches_keywords(msg, ["отправ", "email", "письм"]):
        recipient = self._extract_email(msg)
        if recipient:
            return ("SEND_EMAIL_SIMPLE", {
                "recipient": recipient,
                "subject": self._extract_subject(msg) or "No subject"
            })
```

**3. Добавить workflow (controller.py):**

```python
class WorkflowPlanner:
    def plan(self, intent: str, params: Dict):
        # ... existing plans ...
        
        elif intent == "SEND_EMAIL_SIMPLE":
            return self._plan_send_email(params)
    
    def _plan_send_email(self, params: Dict):
        return [
            WorkflowStep(
                tool="send_email",
                args={
                    "to": params["recipient"],
                    "subject": params["subject"],
                    "body": "Sent via Jane Agent"
                },
                description=f"Отправляю письмо на {params['recipient']}"
            )
        ]
```

**4. Готово!**

```bash
# Теперь работает:
> отправь письмо на example@test.com

🎯 Intent: SEND_EMAIL_SIMPLE
📋 Params: {recipient: "example@test.com"}
✅ Email sent!
```

---

## 📊 Performance Tips

### DO ✅
- Используй короткие, чёткие команды
- Следуй двухшаговым flow для сложных операций (find → delete)
- Проверяй follow-up команды работают автоматически

### DON'T ❌
- Не пытайся описывать что нужно сделать на 3 абзаца
- Не миксуй несколько намерений в одном запросе
- Не ждёт что controller поймёт сложные составные задачи

---

## 🐛 Common Issues

### "Controller module not found"
→ `controller.py` не в папке с `agent_v3.py`

### "Tool not found"
→ Проверить что tool зарегистрирован в `TOOLS` dict

### "Операция заблокирована"
→ Policy Engine работает (это хорошо!)
→ Проверить путь не в `FORBIDDEN_PATHS`

### Follow-up не работает
→ Убедись что первая команда выполнена через controller
→ Проверить `state.pending_intent` сохранён

---

## 📞 Support

Если что-то не работает:

1. **Запустить тесты:** `python test_controller.py`
2. **Проверить логи:** смотри вывод в консоли
3. **Прочитать README:** `CONTROLLER_README.md`
4. **Дай знать!**

---

## 🎓 Learn More

- **Архитектура:** см. `CONTROLLER_README.md`
- **Код:** `controller.py` (хорошо документирован)
- **Интеграция:** `controller_integration_patch.py`
