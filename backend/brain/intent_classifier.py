"""
IntentClassifier — семантический классификатор намерений на базе LLM.
Вместо regex и ключевых слов — понимание смысла через Ollama.
Включает кэширование частых паттернов для скорости.
"""
import json
import hashlib
import re
import requests
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ==============================================================================
# Задание 1: Системный промпт для классификатора
# ==============================================================================

CLASSIFIER_SYSTEM_PROMPT = """Ты — семантический классификатор намерений пользователя для AI-агента.
Твоя задача: понять, что хочет пользователь, и вернуть структурированный JSON.

ДОСТУПНЫЕ ИНТЕНТЫ (intent):

1. CREATE_WORKFLOW — создать автоматизацию / workflow / парсер / бота
   Триггеры: "автоматизируй", "создай workflow", "хочу чтобы каждый день", "настрой парсинг",
   "собирай данные", "мониторь", "отслеживай", "присылай мне", "сделай бота"

2. DEBUG_WORKFLOW — исправить / отладить / разобраться с ошибкой в workflow
   Триггеры: "почему не работает", "ошибка", "исправь", "отладь", "сломалось", "не запускается"

3. RUN_WORKFLOW — запустить существующий workflow
   Триггеры: "запусти", "выполни", "активируй", "включи workflow"

4. LIST_WORKFLOWS — показать список workflow / автоматизаций
   Триггеры: "покажи workflow", "список автоматизаций", "какие есть workflow", "мои автоматизации"

5. LIST_TEMPLATES — показать шаблоны / готовые решения
   Триггеры: "какие шаблоны", "готовые workflow", "примеры автоматизаций"

6. MANAGE_FILES — работа с файлами
   Триггеры: "найди файлы", "удали", "дубликаты", "очисти папку", "создай файл"

7. SYSTEM_INFO — информация о системе
   Триггеры: "место на диске", "память", "CPU", "системная информация"

8. WEB_SEARCH — поиск в интернете
   Триггеры: "найди в интернете", "загугли", "поищи", "что такое"

9. SEND_MESSAGE — отправить сообщение
   Триггеры: "отправь", "напиши", "пошли сообщение", "email", "в телеграм"

10. OPEN_URL — открыть сайт / приложение
    Триггеры: "открой", "зайди на", "покажи сайт"

11. CHAT — разговор, вопрос, благодарность (НЕ требует действий)
    Триггеры: "привет", "спасибо", "как дела", "что умеешь", "кто ты"

12. PROVIDE_INFO — пользователь даёт информацию (ответ на вопрос агента)
    Триггеры: сообщение содержит @каналы, токены, API ключи, URLs, числа
    Используй когда сообщение выглядит как ОТВЕТ, а не как новый запрос

13. CONFIRM — подтверждение действия
    Триггеры: "да", "ок", "давай", "подтверждаю", "согласен", "вариант 1"

14. CANCEL — отмена действия
    Триггеры: "нет", "отмена", "стоп", "не надо", "другое"

СУЩНОСТИ (entities) для извлечения:
- source: откуда данные (telegram, rss, website, email, twitter, instagram)
- channels: список каналов [@channel1, @channel2] — извлекай ВСЕ что начинается с @
- schedule: расписание (daily, hourly, weekly, "в 11 утра", "каждый час")
- schedule_time: конкретное время если указано ("11:00", "утром")
- destination: куда результат (telegram, email, file, notion)
- path: путь к файлу/папке
- url: URL сайта
- workflow_name: название workflow если упомянуто
- workflow_id: ID workflow если упомянуто
- query: поисковый запрос
- credentials: токены/ключи если переданы (НЕ парси, просто отметь has_credentials: true)
- format: формат вывода если указан ("название - описание", "кратко", "подробно")
- topic: тема/фильтр ("AI сервисы", "новости", "обновления")

ПРАВИЛА:
1. Извлекай ВСЕ @упоминания в channels, даже если их много
2. Если пользователь отвечает на вопрос агента — это PROVIDE_INFO, не новый запрос
3. Если не хватает критичной информации — заполни missing_required и clarify_question
4. confidence: 0.9+ уверен, 0.7-0.9 вероятно, <0.7 угадываю
5. Для CREATE_WORKFLOW всегда нужны: source, channels (если source=telegram)
6. Отвечай ТОЛЬКО JSON, без markdown

ФОРМАТ ОТВЕТА:
{
  "intent": "CREATE_WORKFLOW",
  "confidence": 0.95,
  "entities": {
    "source": "telegram",
    "channels": ["@channel1", "@channel2"],
    "schedule": "daily",
    "schedule_time": "11:00",
    "destination": "telegram",
    "topic": "AI новости",
    "format": "название - описание"
  },
  "missing_required": [],
  "clarify_question": null
}"""

ERROR_INTERPRETER_PROMPT = """Ты — эксперт по анализу ошибок. Объясни ошибку ПРОСТЫМ языком.

ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:
{task}

КОНТЕКСТ:
- Сервис: {service}
- Количество каналов/элементов: {item_count}
- Параметры: {params}

ОШИБКА:
{error}

Проанализируй и верни JSON:
{{
  "error_type": "rate_limit | auth | network | config | data | unknown",
  "explanation": "Что случилось — 1 простое предложение",
  "cause": "Почему это произошло в контексте этой задачи",
  "solutions": [
    {{
      "title": "Название решения",
      "description": "Что сделать — понятно для нетехнического человека",
      "can_auto_fix": true,
      "auto_fix_action": "reduce_items | add_delay | retry | use_local | null"
    }}
  ],
  "question_to_user": "Вопрос если нужен выбор, иначе null"
}}

ТИПЫ ОШИБОК:
- rate_limit: 403, 429, "too many requests", "forbidden" — лимиты API
- auth: 401, "unauthorized", "credentials" — проблемы с доступом
- network: timeout, connection refused — сеть недоступна
- config: 400, "invalid", "missing parameter" — неправильные настройки
- data: 404, "not found" — данные не найдены
- unknown: всё остальное

АВТО-ФИКСЫ:
- reduce_items: уменьшить количество каналов/элементов до 5
- add_delay: добавить паузы между запросами
- retry: просто повторить через минуту
- use_local: предложить локальный сервис вместо публичного

ВАЖНО:
- Пиши на русском
- Первым ставь решение которое можно сделать автоматически
- Не пугай пользователя техническими деталями"""


# ==============================================================================
# Dataclasses
# ==============================================================================

@dataclass
class ClassifiedIntent:
    """Результат классификации намерения."""
    intent: str                          # CREATE_WORKFLOW, DEBUG, CLARIFY, CHAT, etc.
    confidence: float                    # 0.0 - 1.0
    entities: Dict[str, Any]            # Извлечённые сущности
    missing_required: List[str]          # Чего не хватает для выполнения
    clarify_question: Optional[str]      # Вопрос пользователю
    original_message: str = ""           # Исходное сообщение
    raw_llm_response: str = ""           # Сырой ответ LLM (для отладки)
    from_cache: bool = False             # Пришло из кэша


@dataclass
class ErrorInterpretation:
    """Результат интерпретации ошибки."""
    error_type: str                      # rate_limit, auth, network, config, data, unknown
    explanation: str                     # Простое объяснение
    cause: str                          # Причина в контексте задачи
    solutions: List[Dict[str, Any]]      # Варианты решений
    question_to_user: Optional[str]      # Вопрос если нужен выбор
    can_auto_fix: bool                   # Есть автоматическое решение
    auto_fix_action: Optional[str]       # reduce_items | add_delay | retry | use_local
    original_error: str = ""            # Исходный текст ошибки


# ==============================================================================
# IntentClassifier
# ==============================================================================

class IntentClassifier:
    """Классификатор намерений с LLM и кэшированием."""

    # Кэш: normalized_message -> (ClassifiedIntent, timestamp)
    _cache: Dict[str, Tuple[ClassifiedIntent, datetime]] = {}
    _cache_ttl: timedelta = timedelta(hours=24)
    _cache_file: Optional[Path] = None

    def __init__(
        self,
        ollama_url: str = None,
        model: str = None,
        timeout: int = 45,
        cache_dir: Optional[Path] = None,
    ):
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.timeout = timeout
        if cache_dir:
            self._cache_file = Path(cache_dir) / "intent_cache.json"
            self._load_cache()

    def classify(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassifiedIntent:
        """
        Классифицирует намерение пользователя.

        Args:
            user_message: Сообщение пользователя
            context: Контекст (last_error, last_workflow, pending_task)

        Returns:
            ClassifiedIntent
        """
        # Быстрые проверки без LLM
        quick_result = self._quick_classify(user_message)
        if quick_result:
            return quick_result

        # Проверяем кэш
        cache_key = self._cache_key(user_message)
        cached = self._get_from_cache(cache_key)
        if cached:
            cached.original_message = user_message
            cached.from_cache = True
            return cached

        # Вызываем LLM
        result = self._classify_with_llm(user_message, context)

        # Кэшируем если уверены
        if result.confidence >= 0.85:
            self._add_to_cache(cache_key, result)

        return result

    def _quick_classify(self, message: str) -> Optional[ClassifiedIntent]:
        """Быстрая классификация без LLM для очевидных случаев."""
        msg = message.strip().lower()

        # Подтверждения
        if msg in ("да", "yes", "ок", "ok", "давай", "го", "1", "подтверждаю"):
            return ClassifiedIntent(
                intent="CONFIRM",
                confidence=0.99,
                entities={"choice": msg},
                missing_required=[],
                clarify_question=None,
                original_message=message,
                from_cache=False,
            )

        # Отмены
        if msg in ("нет", "no", "отмена", "cancel", "стоп", "не надо"):
            return ClassifiedIntent(
                intent="CANCEL",
                confidence=0.99,
                entities={},
                missing_required=[],
                clarify_question=None,
                original_message=message,
                from_cache=False,
            )

        # Выбор варианта по номеру
        if re.match(r'^[1-9]$|^вариант\s*[1-9]$', msg):
            num = re.search(r'[1-9]', msg).group()
            return ClassifiedIntent(
                intent="CONFIRM",
                confidence=0.99,
                entities={"choice": int(num)},
                missing_required=[],
                clarify_question=None,
                original_message=message,
                from_cache=False,
            )

        # Сообщение с кучей @каналов — скорее всего ответ с данными
        channels = re.findall(r'@[\w]+', message)
        if len(channels) >= 3:
            return ClassifiedIntent(
                intent="PROVIDE_INFO",
                confidence=0.95,
                entities={"channels": channels},
                missing_required=[],
                clarify_question=None,
                original_message=message,
                from_cache=False,
            )

        # Сообщение с токеном бота
        if re.search(r'\d{8,10}:[A-Za-z0-9_-]{35}', message):
            return ClassifiedIntent(
                intent="PROVIDE_INFO",
                confidence=0.99,
                entities={"has_credentials": True, "credential_type": "telegram_bot_token"},
                missing_required=[],
                clarify_question=None,
                original_message=message,
                from_cache=False,
            )

        return None

    def _classify_with_llm(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]],
    ) -> ClassifiedIntent:
        """Классификация через Ollama."""
        # Формируем контекст
        context_parts = []
        if context:
            if context.get("last_error"):
                context_parts.append(f"Предыдущая ошибка: {context['last_error'][:200]}")
            if context.get("last_workflow"):
                context_parts.append(f"Последний workflow: {context['last_workflow']}")
            if context.get("pending_task"):
                context_parts.append(f"Ожидает ответа: {context['pending_task']}")
            if context.get("awaiting"):
                context_parts.append(f"Агент ждёт: {context['awaiting']}")

        context_str = "\n".join(context_parts) if context_parts else "Нет контекста"

        user_prompt = f"""Контекст диалога:
{context_str}

Сообщение пользователя:
{user_message}"""

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 1500},
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            answer = resp.json().get("message", {}).get("content", "")
            parsed = self._parse_json(answer)

            # Дополнительно извлекаем каналы если LLM пропустил
            if not parsed.get("entities", {}).get("channels"):
                channels = re.findall(r'@[\w]+', user_message)
                if channels:
                    parsed.setdefault("entities", {})["channels"] = channels

            return ClassifiedIntent(
                intent=parsed.get("intent", "CHAT"),
                confidence=parsed.get("confidence", 0.5),
                entities=parsed.get("entities", {}),
                missing_required=parsed.get("missing_required", []),
                clarify_question=parsed.get("clarify_question"),
                original_message=user_message,
                raw_llm_response=answer,
                from_cache=False,
            )

        except requests.exceptions.Timeout:
            return self._fallback_classification(user_message, "LLM timeout")
        except requests.exceptions.ConnectionError:
            return self._fallback_classification(user_message, "LLM unavailable")
        except Exception as e:
            return self._fallback_classification(user_message, str(e))

    def _fallback_classification(self, message: str, error: str) -> ClassifiedIntent:
        """Fallback когда LLM недоступен — простая эвристика."""
        msg = message.lower()

        # Простые паттерны
        if any(w in msg for w in ["создай", "автоматиз", "workflow", "настрой", "хочу чтобы"]):
            intent = "CREATE_WORKFLOW"
        elif any(w in msg for w in ["ошибка", "исправь", "почему не", "debug", "отладь"]):
            intent = "DEBUG_WORKFLOW"
        elif any(w in msg for w in ["покажи", "список", "какие есть"]):
            intent = "LIST_WORKFLOWS"
        elif any(w in msg for w in ["найди", "поиск", "загугли"]):
            intent = "WEB_SEARCH"
        elif any(w in msg for w in ["открой", "зайди"]):
            intent = "OPEN_URL"
        else:
            intent = "CHAT"

        channels = re.findall(r'@[\w]+', message)
        return ClassifiedIntent(
            intent=intent,
            confidence=0.5,
            entities={"channels": channels} if channels else {},
            missing_required=[],
            clarify_question=None,
            original_message=message,
            raw_llm_response=f"Fallback due to: {error}",
            from_cache=False,
        )

    def _cache_key(self, message: str) -> str:
        """Генерирует ключ кэша для сообщения."""
        normalized = message.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        # Заменяем конкретные каналы на плейсхолдер (чтобы кэш работал для разных каналов)
        normalized = re.sub(r'@[\w]+', '@CHANNEL', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _get_from_cache(self, key: str) -> Optional[ClassifiedIntent]:
        """Получает из кэша если не протух."""
        if key not in self._cache:
            return None
        cached, timestamp = self._cache[key]
        if datetime.now() - timestamp > self._cache_ttl:
            del self._cache[key]
            return None
        return ClassifiedIntent(
            intent=cached.intent,
            confidence=cached.confidence,
            entities=dict(cached.entities),
            missing_required=list(cached.missing_required),
            clarify_question=cached.clarify_question,
            original_message=cached.original_message,
            raw_llm_response=cached.raw_llm_response,
            from_cache=True,
        )

    def _add_to_cache(self, key: str, result: ClassifiedIntent) -> None:
        """Добавляет в кэш."""
        self._cache[key] = (result, datetime.now())
        self._save_cache()

    def _load_cache(self) -> None:
        """Загружает кэш из файла."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            for key, item in data.items():
                timestamp = datetime.fromisoformat(item["timestamp"])
                if datetime.now() - timestamp < self._cache_ttl:
                    self._cache[key] = (
                        ClassifiedIntent(
                            intent=item["intent"],
                            confidence=item["confidence"],
                            entities=item["entities"],
                            missing_required=item["missing_required"],
                            clarify_question=item.get("clarify_question"),
                            original_message=item.get("original_message", ""),
                            raw_llm_response="",
                            from_cache=True,
                        ),
                        timestamp,
                    )
        except Exception:
            pass

    def _save_cache(self) -> None:
        """Сохраняет кэш в файл."""
        if not self._cache_file:
            return
        try:
            data = {}
            for key, (result, timestamp) in self._cache.items():
                data[key] = {
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "entities": result.entities,
                    "missing_required": result.missing_required,
                    "clarify_question": result.clarify_question,
                    "original_message": result.original_message,
                    "timestamp": timestamp.isoformat(),
                }
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _parse_json(self, text: str) -> Dict:
        """Парсит JSON из ответа LLM."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}


# ==============================================================================
# SmartErrorInterpreter
# ==============================================================================

class SmartErrorInterpreter:
    """Интерпретатор ошибок на базе LLM."""

    def __init__(
        self,
        ollama_url: str = None,
        model: str = None,
        timeout: int = 30,
    ):
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.timeout = timeout

    def interpret(
        self,
        error: str,
        context: Dict[str, Any],
    ) -> ErrorInterpretation:
        """
        Интерпретирует ошибку через LLM.

        Args:
            error: Текст ошибки
            context: task, service, channels, params

        Returns:
            ErrorInterpretation
        """
        # Подсчёт элементов
        item_count = 0
        channels = context.get("params", {}).get("channels", [])
        if isinstance(channels, list):
            item_count = len(channels)
        elif isinstance(channels, str):
            item_count = len(re.findall(r'@[\w]+', channels))

        prompt = ERROR_INTERPRETER_PROMPT.format(
            task=context.get("task", "Не указана"),
            service=context.get("service", "unknown"),
            item_count=item_count,
            params=json.dumps(context.get("params", {}), ensure_ascii=False)[:500],
            error=error[:1000],
        )

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 2000},
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            answer = resp.json().get("message", {}).get("content", "")
            parsed = self._parse_json(answer)

            solutions = parsed.get("solutions", [])
            can_auto = any(s.get("can_auto_fix") for s in solutions)
            auto_action = None
            for s in solutions:
                if s.get("can_auto_fix"):
                    auto_action = s.get("auto_fix_action")
                    break

            return ErrorInterpretation(
                error_type=parsed.get("error_type", "unknown"),
                explanation=parsed.get("explanation", f"Произошла ошибка: {error[:100]}"),
                cause=parsed.get("cause", "Не удалось определить причину"),
                solutions=solutions,
                question_to_user=parsed.get("question_to_user"),
                can_auto_fix=can_auto,
                auto_fix_action=auto_action,
                original_error=error,
            )

        except Exception as e:
            return self._fallback_interpretation(error, context, str(e))

    def _fallback_interpretation(
        self,
        error: str,
        context: Dict[str, Any],
        llm_error: str,
    ) -> ErrorInterpretation:
        """Fallback интерпретация без LLM."""
        error_lower = error.lower()

        if any(x in error_lower for x in ["403", "429", "rate", "too many", "forbidden"]):
            error_type = "rate_limit"
            explanation = "Сервис заблокировал запрос — слишком много обращений"
            cause = "Публичные API ограничивают количество запросов"
            solutions = [
                {
                    "title": "Уменьшить количество",
                    "description": "Начну с 5 каналов, потом добавим остальные",
                    "can_auto_fix": True,
                    "auto_fix_action": "reduce_items",
                },
                {
                    "title": "Добавить паузы",
                    "description": "Делать запросы с задержкой 2-3 секунды",
                    "can_auto_fix": True,
                    "auto_fix_action": "add_delay",
                },
            ]
        elif any(x in error_lower for x in ["401", "unauthorized", "credentials", "auth"]):
            error_type = "auth"
            explanation = "Нет доступа — нужны учётные данные"
            cause = "Сервис требует авторизацию"
            solutions = [
                {
                    "title": "Добавить API ключ",
                    "description": "Нужен токен или ключ для доступа к сервису",
                    "can_auto_fix": False,
                    "auto_fix_action": None,
                }
            ]
        elif any(x in error_lower for x in ["timeout", "timed out", "connection"]):
            error_type = "network"
            explanation = "Сервис не отвечает"
            cause = "Проблемы с сетью или сервис перегружен"
            solutions = [
                {
                    "title": "Повторить позже",
                    "description": "Подожду минуту и попробую снова",
                    "can_auto_fix": True,
                    "auto_fix_action": "retry",
                }
            ]
        else:
            error_type = "unknown"
            explanation = f"Произошла ошибка: {error[:100]}"
            cause = "Не удалось определить причину автоматически"
            solutions = [
                {
                    "title": "Попробовать иначе",
                    "description": "Опиши задачу по-другому",
                    "can_auto_fix": False,
                    "auto_fix_action": None,
                }
            ]

        return ErrorInterpretation(
            error_type=error_type,
            explanation=explanation,
            cause=cause,
            solutions=solutions,
            question_to_user="Какой вариант выбираешь?",
            can_auto_fix=any(s["can_auto_fix"] for s in solutions),
            auto_fix_action=next(
                (s["auto_fix_action"] for s in solutions if s["can_auto_fix"]), None
            ),
            original_error=error,
        )

    def format_for_user(self, interpretation: ErrorInterpretation) -> str:
        """Форматирует в читаемое сообщение."""
        lines = [interpretation.explanation, ""]
        if interpretation.cause:
            lines.append(f"Причина: {interpretation.cause}")
            lines.append("")
        if interpretation.solutions:
            lines.append("Варианты решения:")
            for i, sol in enumerate(interpretation.solutions, 1):
                auto_mark = " ✓" if sol.get("can_auto_fix") else ""
                lines.append(f"{i}. **{sol['title']}**{auto_mark}")
                lines.append(f"   {sol['description']}")
            lines.append("")
        if interpretation.question_to_user:
            lines.append(interpretation.question_to_user)
        elif interpretation.can_auto_fix:
            lines.append("Попробовать вариант 1 автоматически? (да/нет)")
        return "\n".join(lines)

    def _parse_json(self, text: str) -> Dict:
        """Парсит JSON."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except Exception:
                pass
        return {}
