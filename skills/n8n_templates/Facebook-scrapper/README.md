# 🎯 Facebook Group Events Scraper

> **Stealth • Vision • Anti-Ban • LLM-Powered**  
> Умный мультимодальный скрейпер мероприятий из открытых Facebook-групп.  
> Понимает хаотичный текст и читает афиши через vision-модель.

---

## 💡 Проблема, которую решает скрипт

Участники публичных групп Facebook публикуют анонсы мероприятий совершенно произвольно:
- кто-то пишет подробный текст
- кто-то постит только картинку-афишу без единого слова текста
- кто-то пишет одной строкой с опечатками на шведском

Вручную мониторить десятки групп — рутина. Обычный CSS-парсер это не разберёт.

**Решение:** два уровня анализа — сначала LLM по тексту, затем vision по картинке если текст ничего не дал.

---

## 🏗️ Архитектура

```
main.py (точка входа)
    └── scraper/
         ├── config.py       ← все настройки из .env
         ├── browser.py      ← Persistent Context + stealth-патчи
         ├── human.py        ← плавный скролл, движения мышью, паузы
         ├── fb_collect.py   ← навигация + сбор постов + image_urls
         ├── llm_text.py     ← LLM text-анализ (gpt-5-mini)
         ├── llm_vision.py   ← Vision-анализ афиш (qwen2.5vl)
         ├── normalize.py    ← нормализация дат, дедуп-ключ
         ├── storage.py      ← CSV + state.json + метрики
         └── run.py          ← оркестратор pipeline
```

### Pipeline на каждую группу:

```
state.json (seen_urls)
       │
       ▼
  navigate_to_group()
       │
       ▼
  collect_posts()          ← текст + image_urls + ранний выход
       │
       ├─── LLM text ──────→ events (source=text)
       │         │
       │    no_event +       
       │    has_images       
       │         │
       └─── Vision ─────────→ events (source=vision)
                │
                ▼
          normalize + enrich
                │
                ▼
          save_to_csv  +  update state.json
```

---

## 📊 Выходные данные (events.csv, 16 колонок)

| Колонка | Описание |
|---|---|
| `title` | Название (извлечено LLM/vision) |
| `event_type` | Тип: konsert, utställning, loppis, kurs... |
| `date_raw` | Дата как написано в посте |
| `date_normalized` | ISO-дата YYYY-MM-DD (если удалось распознать) |
| `location` | Место проведения |
| `description` | Краткое описание 1–2 предложения |
| `contact` | Контакт/ссылка для записи |
| `confidence` | Уверенность LLM (0.0–1.0) |
| `source` | `text` или `vision` |
| `group_name` | Имя группы |
| `group_url` | URL группы |
| `post_author` | Автор поста |
| `post_date` | Когда опубликован |
| `post_url` | Прямая ссылка на пост |
| `image_urls` | Картинки поста (`;`-separated) |
| `scraped_at` | Время сбора |

---

## 🛡️ Антибот-стек

| Уровень | Техника |
|---|---|
| Persistent Context | Реальный профиль Chrome, сохранённая сессия FB |
| playwright-stealth | `navigator.webdriver`, plugins, languages |
| JS-патчи | Canvas fingerprint, WebGL, CDP-следы, chrome.runtime |
| Случайный UA | Chrome 128–131, 5 вариантов |
| Случайный viewport | 4 реалистичных разрешения |
| Плавный скролл | 150–450px, паузы 0.5–2.5с, 15% откат вверх |
| Мышь | Случайные движения по viewport |
| human_delay | `random.uniform(3–7с)` перед действиями |
| Пауза между группами | 15–35с случайная задержка |
| state.json | Ранний выход при виденных постах |

---

## 💻 Требования

- **Windows 10/11** (или macOS/Linux с поправкой путей)
- **Python 3.10+** ([скачать](https://www.python.org/downloads/))
- **Google Chrome** (с вашим Facebook-аккаунтом)
- **Git** ([скачать](https://git-scm.com/))
- **OpenAI API ключ** (или GenSpark Sandbox — ключ настраивается автоматически)

---

## 🚀 Установка (Windows)

### 1. Клонирование

```cmd
git clone https://github.com/OummaEE/Facebook-scrapper.git
cd Facebook-scrapper
```

### 2. Виртуальное окружение

```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Зависимости

```cmd
pip install -r requirements.txt
playwright install chromium
```

### 4. Настройка .env

```cmd
copy .env.example .env
notepad .env
```

**Найдите путь к профилю Chrome:**
1. Откройте Chrome
2. Введите в адресной строке: `chrome://version/`
3. Скопируйте **«Путь к профилю»** — убрав `\Default` в конце

```env
# Например:
CHROME_USER_DATA_DIR=C:\Users\Иван\AppData\Local\Google\Chrome\User Data

# Ваши группы (через запятую):
GROUP_URLS=https://www.facebook.com/groups/group1,https://www.facebook.com/groups/group2,https://www.facebook.com/groups/group3

# API ключ:
OPENAI_API_KEY=sk-xxxxxxx
```

---

## ▶️ Запуск

> ⚠️ **Закройте Chrome полностью перед запуском!**

```cmd
python main.py
```

### Пример вывода:

```
12:00:00  [INFO]  🚀 Facebook Group Events Scraper v3.0 запущен
12:00:00  [INFO]     Групп: 3 | Постов: 20 | LLM: gpt-5-mini | Vision: qwen2.5vl
──────────────────────────────────────────
12:00:05  [INFO]  📦 [1/3] https://facebook.com/groups/stockholm_events
12:00:05  [INFO]     📚 Уже видели: 47 URL из этой группы
12:00:08  [INFO]  ✅ Группа загружена
12:00:20  [INFO]     Раунд 1: +12 постов (всего: 12)
12:00:38  [INFO]     🛑 Ранний выход: пост уже видели ранее
12:00:40  [INFO]  🤖 LLM text-анализ: 12 постов...
12:00:41  [INFO]     [01/12] 'Konsert fredag 14 mars kl 19:00...'
12:00:42  [INFO]          ✅ СОБЫТИЕ [92%] → Jazzkonsert på Fasching
12:00:43  [INFO]     [02/12] 'Vem var på gårdagens show?...'
12:00:44  [INFO]          — Не мероприятие
12:00:49  [INFO]     [07/12] 'Se bifogad bild!' [imgs:2]
12:00:50  [INFO]          🖼  Кандидат для vision (2 изображения)
...
12:01:10  [INFO]  🖼️  Vision-анализ: 3 кандидата...
12:01:12  [INFO]     [01/03] Vision: https://scontent.fcdn...
12:01:15  [INFO]          ✅ VISION СОБЫТИЕ [88%] → Loppis i Södermalm

═══════════════════════════════════════════
  📅  НАЙДЕННЫЕ МЕРОПРИЯТИЯ (5 шт.)
═══════════════════════════════════════════
  [1] Jazzkonsert på Fasching  💬
       Тип:   konsert | Дата: fredag 14 mars kl 19:00
  [2] Loppis i Södermalm  🖼️
       Тип:   loppis | Дата: lördag 22 mars 10-15
...

  📊  ИТОГИ СЕССИИ
═══════════════════════════════════════════
  Групп обработано:    3
  Ранних выходов:      2
  Постов собрано:      38
  Событий из текста:   4
  Событий из vision:   3
  Итого найдено:       7
  Новых сохранено:     5
```

---

## 📁 Структура проекта

```
Facebook-scrapper/
│
├── main.py              ← Точка входа
├── requirements.txt     ← 5 зависимостей
├── .env.example         ← Шаблон конфига
├── .gitignore           ← Защищает .env, events.csv, state.json, venv/
├── README.md
├── CHANGELOG.md
│
└── scraper/
     ├── __init__.py
     ├── config.py        ← Централизованные настройки
     ├── browser.py       ← Stealth браузер
     ├── human.py         ← Человекоподобное поведение
     ├── fb_collect.py    ← Сбор постов + image_urls
     ├── llm_text.py      ← Text LLM анализ
     ├── llm_vision.py    ← Vision анализ
     ├── normalize.py     ← Нормализация + дедуп-ключ
     ├── storage.py       ← CSV + state.json
     └── run.py           ← Оркестратор
│
├── .env                 ← ВАШ конфиг (НЕ в репо!)
├── events.csv           ← Результаты (НЕ в репо!)
├── state.json           ← Состояние (НЕ в репо!)
└── scraper.log          ← Логи (НЕ в репо!)
```

---

## 🔧 Устранение неполадок

**«Chrome требует авторизации»** → Откройте Chrome вручную, войдите в Facebook, закройте Chrome.

**«Could not obtain lock file»** → Chrome запущен. Полностью закройте все окна Chrome.

**Посты не найдены (0 постов)** → Facebook изменил DOM. Откройте группу, F12 → найдите новые классы `article`, обновите `ARTICLE_SELECTORS` в `fb_collect.py`.

**Vision не находит события** → Снизьте порог: `VISION_CONFIDENCE_THRESHOLD=0.4`. Или попробуйте другую vision-модель.

**Дублирование в CSV** → Дедупликация работает по `post_url`. Если URL пустой — по hash полей. Проверьте, что `post_url` собирается корректно.

---

## ⚠️ Дозированное использование

| ✅ Безопасно | ❌ Рискованно |
|---|---|
| 1–2 запуска в день | Каждый час |
| 3–5 групп за сессию | 20+ групп |
| `POSTS_PER_GROUP=15–25` | `POSTS_PER_GROUP=100` |
| `HEADLESS=false` при настройке | Только headless без проверки |

---

*Только открытые публичные группы. Только для личного некоммерческого использования.*
