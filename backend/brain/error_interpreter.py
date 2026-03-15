"""
ErrorInterpreter — анализирует ошибки и предлагает решения человеческим языком.

Вместо сырых логов типа "Forbidden 403" генерирует понятное объяснение
и ранжированные варианты решения.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Solution:
    """Одно возможное решение проблемы."""
    title: str                    # Краткое название
    description: str              # Что именно сделать
    complexity: str               # "easy" | "medium" | "hard"
    requires_user_action: bool    # Нужно ли участие пользователя
    auto_executable: bool         # Может ли агент сделать сам
    

@dataclass
class InterpretedError:
    """Результат интерпретации ошибки."""
    error_type: str                      # rate_limit, auth, network, invalid_data, unknown
    likely_cause: str                    # Вероятная причина в контексте задачи
    solutions: List[Solution]            # Варианты решения, от простого к сложному
    user_message: str                    # Готовый текст для пользователя
    original_error: str                  # Исходная ошибка
    can_retry_with_modification: bool    # Можно ли повторить с изменениями
    suggested_modification: Optional[Dict[str, Any]] = None  # Что изменить для retry


class ErrorInterpreter:
    """
    Интерпретатор ошибок. Превращает технические сообщения в понятные объяснения.
    """
    
    # Паттерны ошибок → тип
    _ERROR_PATTERNS = [
        # Rate limiting
        (r'429|rate.?limit|too.?many.?requests|throttl', 'rate_limit'),
        (r'403.*forbidden|forbidden.*403', 'rate_limit'),  # часто 403 = rate limit на публичных API
        
        # Authentication / Authorization
        (r'401|unauthorized|auth.*fail|invalid.*token|invalid.*key', 'auth'),
        (r'credentials?.*issue|check.*credentials?', 'auth'),
        
        # Network
        (r'timeout|timed?.?out|deadline.?exceeded', 'network_timeout'),
        (r'connection.?refused|econnrefused|connect.*fail', 'network_refused'),
        (r'network.*error|socket.*error|dns.*error', 'network_generic'),
        (r'ssl|certificate|cert.*error', 'network_ssl'),
        
        # Invalid data / Bad request
        (r'400|bad.?request|invalid.*param|validation.*fail', 'invalid_data'),
        (r'404|not.?found', 'not_found'),
        (r'500|502|503|504|internal.*error|server.*error', 'server_error'),
        
        # n8n specific
        (r'workflow.*not.*found', 'n8n_workflow_not_found'),
        (r'node.*not.*found|unknown.*node', 'n8n_node_error'),
        (r'execution.*fail', 'n8n_execution_error'),
    ]
    
    # Контекстные модификаторы — уточняют причину на основе контекста задачи
    _CONTEXT_HINTS = {
        'rate_limit': {
            'many_items': 'Слишком много элементов в одном запросе',
            'public_api': 'Публичный API ограничивает частоту запросов',
            'no_api_key': 'Без API ключа лимиты значительно ниже',
        },
        'auth': {
            'missing_credentials': 'Не указаны учётные данные',
            'expired_token': 'Токен мог истечь',
            'wrong_permissions': 'Недостаточно прав доступа',
        },
        'network_timeout': {
            'slow_api': 'API отвечает медленно',
            'large_request': 'Запрос слишком большой',
        }
    }
    
    def interpret(
        self, 
        error: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> InterpretedError:
        """
        Интерпретирует ошибку в контексте задачи.
        
        Args:
            error: Сырое сообщение об ошибке
            context: Контекст задачи:
                - task: исходный запрос пользователя
                - step: текущий шаг (n8n_create, fetch_posts, etc.)
                - params: параметры (channels, urls, etc.)
                - service: сервис (rsshub, telegram, etc.)
        
        Returns:
            InterpretedError с человекочитаемым объяснением и решениями
        """
        context = context or {}
        error_lower = error.lower()
        
        # 1. Определяем тип ошибки
        error_type = self._classify_error(error_lower)
        
        # 2. Извлекаем контекст задачи
        task_context = self._extract_task_context(context)
        
        # 3. Определяем вероятную причину
        likely_cause = self._determine_cause(error_type, task_context, error_lower)
        
        # 4. Генерируем решения
        solutions = self._generate_solutions(error_type, task_context)
        
        # 5. Формируем сообщение пользователю
        user_message = self._format_user_message(
            error_type, likely_cause, solutions, task_context
        )
        
        # 6. Определяем возможность автоматического retry
        can_retry, modification = self._can_retry_with_modification(
            error_type, task_context
        )
        
        return InterpretedError(
            error_type=error_type,
            likely_cause=likely_cause,
            solutions=solutions,
            user_message=user_message,
            original_error=error,
            can_retry_with_modification=can_retry,
            suggested_modification=modification
        )
    
    def _classify_error(self, error_lower: str) -> str:
        """Классифицирует ошибку по паттернам."""
        for pattern, error_type in self._ERROR_PATTERNS:
            if re.search(pattern, error_lower, re.IGNORECASE):
                return error_type
        return 'unknown'
    
    def _extract_task_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает релевантную информацию из контекста задачи."""
        task_context = {
            'item_count': 0,
            'service': 'unknown',
            'has_credentials': False,
            'is_public_api': True,
            'original_task': context.get('task', ''),
        }
        
        params = context.get('params', {})
        
        # Подсчёт элементов (каналы, URL, etc.)
        for key in ['channels', 'targets', 'urls', 'items']:
            if key in params:
                value = params[key]
                if isinstance(value, list):
                    task_context['item_count'] = len(value)
                elif isinstance(value, str):
                    # Подсчёт через запятые или @mentions
                    task_context['item_count'] = max(
                        len(value.split(',')),
                        len(re.findall(r'@\w+', value))
                    )
        
        # Определение сервиса
        step = context.get('step', '')
        task = context.get('task', '').lower()
        
        if 'rsshub' in str(params).lower() or 'rsshub' in task:
            task_context['service'] = 'rsshub'
            task_context['is_public_api'] = True
        elif 'telegram' in task:
            task_context['service'] = 'telegram'
        elif 'twitter' in task or 'x.com' in task:
            task_context['service'] = 'twitter'
        
        # Проверка credentials
        if params.get('api_key') or params.get('token') or params.get('credentials'):
            task_context['has_credentials'] = True
        
        return task_context
    
    def _determine_cause(
        self, 
        error_type: str, 
        task_context: Dict[str, Any],
        error_lower: str
    ) -> str:
        """Определяет вероятную причину с учётом контекста."""
        
        item_count = task_context.get('item_count', 0)
        service = task_context.get('service', 'unknown')
        
        if error_type == 'rate_limit':
            if item_count > 10:
                return (
                    f"Попытка обработать {item_count} элементов одновременно — "
                    f"публичный API {service} ограничивает количество запросов"
                )
            elif service == 'rsshub':
                return (
                    "Публичный rsshub.app имеет строгие лимиты на количество запросов. "
                    "При частых обращениях блокирует IP"
                )
            else:
                return "Сервис ограничил частоту запросов"
        
        elif error_type == 'auth':
            if not task_context.get('has_credentials'):
                return "Не указаны учётные данные для доступа к API"
            else:
                return "Учётные данные не приняты — возможно, истекли или неверные"
        
        elif error_type == 'network_timeout':
            if item_count > 5:
                return f"Запрос на {item_count} элементов занимает слишком много времени"
            return "Сервис не ответил вовремя"
        
        elif error_type == 'network_refused':
            return "Не удалось подключиться к сервису — возможно, он недоступен"
        
        elif error_type == 'not_found':
            return "Запрошенный ресурс не найден — проверь правильность адресов/имён"
        
        elif error_type == 'server_error':
            return "Ошибка на стороне сервиса — это не твоя проблема, нужно подождать"
        
        return "Не удалось определить точную причину"
    
    def _generate_solutions(
        self, 
        error_type: str, 
        task_context: Dict[str, Any]
    ) -> List[Solution]:
        """Генерирует список решений для данного типа ошибки."""
        
        solutions = []
        item_count = task_context.get('item_count', 0)
        service = task_context.get('service', 'unknown')
        
        if error_type == 'rate_limit':
            # Решение 1: Уменьшить количество
            if item_count > 5:
                solutions.append(Solution(
                    title="Начать с меньшего количества",
                    description=(
                        f"Сначала создам workflow для 5 каналов, проверю что работает, "
                        f"потом постепенно добавим остальные {item_count - 5}"
                    ),
                    complexity="easy",
                    requires_user_action=False,
                    auto_executable=True
                ))
            
            # Решение 2: Разбить на части
            if item_count > 10:
                batches = (item_count + 4) // 5  # округление вверх, по 5 штук
                solutions.append(Solution(
                    title="Разбить на несколько workflow",
                    description=(
                        f"Создать {batches} отдельных workflow по 5 каналов, "
                        f"запускать их в разное время (11:00, 11:10, 11:20...)"
                    ),
                    complexity="easy",
                    requires_user_action=True,
                    auto_executable=True
                ))
            
            # Решение 3: Свой сервер
            if service == 'rsshub':
                solutions.append(Solution(
                    title="Поднять свой RSSHub",
                    description=(
                        "Запустить локальный RSSHub через Docker — без лимитов. "
                        "Команда: docker run -d -p 1200:1200 diygod/rsshub"
                    ),
                    complexity="medium",
                    requires_user_action=True,
                    auto_executable=False
                ))
            
            # Решение 4: Добавить задержки
            solutions.append(Solution(
                title="Добавить паузы между запросами",
                description=(
                    "Вставить задержку 2-3 секунды между запросами к API, "
                    "чтобы не превышать лимит"
                ),
                complexity="easy",
                requires_user_action=False,
                auto_executable=True
            ))
        
        elif error_type == 'auth':
            solutions.append(Solution(
                title="Добавить API ключ",
                description=(
                    f"Для сервиса {service} нужен API ключ или токен. "
                    "Укажи его, и я добавлю в workflow"
                ),
                complexity="easy",
                requires_user_action=True,
                auto_executable=False
            ))
            
            if service == 'telegram':
                solutions.append(Solution(
                    title="Использовать Telegram Bot API",
                    description=(
                        "Создать бота через @BotFather, добавить в каналы, "
                        "и использовать его токен для чтения сообщений"
                    ),
                    complexity="medium",
                    requires_user_action=True,
                    auto_executable=False
                ))
        
        elif error_type in ('network_timeout', 'network_refused'):
            solutions.append(Solution(
                title="Повторить позже",
                description="Подождать 5-10 минут и попробовать снова",
                complexity="easy",
                requires_user_action=False,
                auto_executable=True
            ))
            
            solutions.append(Solution(
                title="Проверить доступность сервиса",
                description=f"Открой {service} в браузере и проверь, что он работает",
                complexity="easy",
                requires_user_action=True,
                auto_executable=False
            ))
        
        elif error_type == 'server_error':
            solutions.append(Solution(
                title="Подождать",
                description=(
                    "Ошибка на стороне сервиса. Обычно исправляется в течение часа. "
                    "Попробуем снова через 30 минут"
                ),
                complexity="easy",
                requires_user_action=False,
                auto_executable=True
            ))
        
        # Fallback — всегда предлагаем ручной режим
        if not solutions or error_type == 'unknown':
            solutions.append(Solution(
                title="Попробовать другой подход",
                description="Опиши задачу по-другому, и я предложу альтернативное решение",
                complexity="easy",
                requires_user_action=True,
                auto_executable=False
            ))
        
        return solutions
    
    def _format_user_message(
        self,
        error_type: str,
        likely_cause: str,
        solutions: List[Solution],
        task_context: Dict[str, Any]
    ) -> str:
        """Формирует человекочитаемое сообщение."""
        
        # Заголовок по типу ошибки
        headers = {
            'rate_limit': "Сервис заблокировал запрос из-за превышения лимитов",
            'auth': "Проблема с доступом — нужны учётные данные",
            'network_timeout': "Сервис не отвечает — слишком долго ждать",
            'network_refused': "Не удалось подключиться к сервису",
            'network_ssl': "Проблема с безопасным соединением",
            'not_found': "Запрошенные данные не найдены",
            'server_error': "Ошибка на стороне сервиса",
            'invalid_data': "Неверный формат запроса",
            'unknown': "Произошла ошибка",
        }
        
        header = headers.get(error_type, headers['unknown'])
        
        # Собираем сообщение
        lines = [header, ""]
        
        if likely_cause:
            lines.append(f"Причина: {likely_cause}")
            lines.append("")
        
        if solutions:
            lines.append("Варианты решения:")
            for i, sol in enumerate(solutions, 1):
                lines.append(f"{i}. **{sol.title}** — {sol.description}")
            lines.append("")
        
        # Добавляем вопрос
        auto_solutions = [s for s in solutions if s.auto_executable]
        if auto_solutions:
            lines.append(f"Могу сразу попробовать вариант 1. Или выбери другой номер.")
        else:
            lines.append("Какой вариант предпочитаешь?")
        
        return "\n".join(lines)
    
    def _can_retry_with_modification(
        self,
        error_type: str,
        task_context: Dict[str, Any]
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Определяет, можно ли повторить с изменениями."""
        
        item_count = task_context.get('item_count', 0)
        
        if error_type == 'rate_limit' and item_count > 5:
            return True, {
                'reduce_items_to': 5,
                'add_delay_seconds': 2,
                'reason': 'Уменьшаю количество элементов до 5 для первой попытки'
            }
        
        if error_type in ('network_timeout', 'server_error'):
            return True, {
                'retry_after_seconds': 30,
                'reason': 'Подождём 30 секунд и попробуем снова'
            }
        
        return False, None
