# Инструкция: Создание сложных n8n Workflow

## Правило: максимум 7-10 узлов в одном workflow

Если в workflow больше 10 узлов — LLM теряет контекст и начинает галлюцинировать поля.
**Всегда разбивай на sub-workflows.**

## Когда разбивать на sub-workflows

Разбивай если:
- Задача требует > 10 узлов
- Есть несколько независимых ветвей обработки
- Есть цикл (loop) с неизвестным числом итераций
- Задача концептуально делится на "сбор данных" + "обработка" + "сохранение"

## Как разбивать на sub-workflows

**Принцип разрезания:**
1. Найди естественные точки разреза (смена контекста, тип обработки)
2. Первый workflow: триггер + сбор данных + передача
3. Второй workflow: получение данных + обработка
4. Третий (опционально): сохранение результатов

**Узел-мост: Execute Workflow**
```json
{
  "type": "n8n-nodes-base.executeWorkflow",
  "typeVersion": 1.1,
  "parameters": {
    "source": "database",
    "workflowId": {"__rl": true, "value": "WORKFLOW_ID", "mode": "id"},
    "options": {}
  }
}
```

## Как связывать sub-workflows (входы/выходы)

**Передача данных из workflow A в workflow B:**

Workflow A (последний узел перед Execute Workflow):
```javascript
// Set node — подготовка данных для передачи
return [{json: {
  processedItems: $input.all().map(i => i.json),
  metadata: {count: $input.all().length, timestamp: new Date().toISOString()}
}}];
```

Workflow B (первый узел после trigger):
```javascript
// Code node — приём данных
const incoming = $input.first().json;
const items = incoming.processedItems || [];
return items.map(item => ({json: item}));
```

## Как передавать данные между sub-workflows

| Метод | Когда использовать |
|---|---|
| Прямая передача через Execute Workflow | Малый объём (<1MB), синхронно |
| Через переменные workflow | Простые скалярные значения |
| Через внешнее хранилище (файл/БД) | Большой объём данных |

**Execute Workflow передаёт данные автоматически** — выходные данные последнего узла становятся входными для вызванного workflow.

## Примеры декомпозиции

### RSS-агрегатор (15 узлов → 2 workflow)

**Workflow 1 "Fetch"** (7 узлов):
`Schedule Trigger → Fetch RSS 1 → Fetch RSS 2 → Merge → Filter New → Set Metadata → Execute Workflow 2`

**Workflow 2 "Process"** (6 узлов):
`Execute Workflow Trigger → AI Rewrite → Format → Filter Quality → Save to DB → Notify`

### Отчёт по дубликатам (12 узлов → 2 workflow)

**Workflow 1 "Scan"** (5 узлов):
`Manual Trigger → List Files → Hash Files → Group by Hash → Execute Workflow 2`

**Workflow 2 "Report"** (5 узлов):
`Execute Workflow Trigger → Filter Duplicates → Generate Report → Send Email → Mark Done`
