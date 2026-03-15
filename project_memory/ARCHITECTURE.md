# Архитектура Jane AI Agent

## Компоненты

### LLM (Ollama)
- URL: http://localhost:11434
- Модель(и): 

### Agent Core
- Главный файл: agent_v3.py
- Роли: intent detection, планирование, tools, память

### Tools / Skills (высокоуровнево)
Файлы:
Документы:
Browser automation:
Google:
Telegram:
n8n:
CRM:
Voice:
PDF:

### Memory
memory/
- chat_history.json
- user_profile.json
- tasks.json
- browser_sessions/

### UI
- Web UI: http://localhost:5000

---

## Главные архитектурные проблемы (обновлять!)
- [ ] Нет/слабый state manager между tool-вызовами
- [ ] LLM иногда выдумывает пути/аргументы
- [ ] Нет policy layer на опасные инструменты (powershell/удаление/Chrome)
- [ ] Недостаточно валидации результатов (validator)

---

## Целевая архитектура (куда идём)
- Intent → Policy → State → Planner → Executor → Validator
