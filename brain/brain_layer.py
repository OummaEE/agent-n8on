"""BrainLayer — top-level orchestrator sitting above AgentController.

Request flow:
  User message
       ↓
  BrainLayer.handle()
       ├── _handle_pending()  ← check awaiting confirmation first
       ↓
  Router.route()               ← pre-route before controller
       ↓ CLARIFY → ask user
       ↓ SLOW (require_confirmation=True) → format plan, await "да/нет/изменить"
       ↓ SLOW (require_confirmation=False) → Plan → Execute → Verify
       ↓ FAST → controller.handle_request()
            ├── handled=True  → wrap & return
            └── handled=False → unhandled (LLM fallback)

Improvements added (2026-03-03):
  1. Активный цикл обучения — _load_learned_rules / _save_learned_rule
  2. Подтверждение плана — pending state machine for SLOW tasks
  3. Динамические навыки — _find_relevant_skill injected into slow path context

Improvements added (2026-03-06):
  4. ErrorInterpreter — анализ ошибок и предложение решений человеческим языком
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.executor import Executor, StepResult
from brain.planner import PlanStep, Planner
from brain.router import Router
from brain.verifier import VerificationResult, Verifier
from brain.error_interpreter import ErrorInterpreter, InterpretedError
from brain.intent_classifier import IntentClassifier, SmartErrorInterpreter, ClassifiedIntent

# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------

_HIGH_RISK_INTENTS = frozenset({
    "N8N_DEBUG_WORKFLOW",
    "CLEAN_DUPLICATES_KEEP_NEWEST",
    "PURGE_TRASH",
    "DELETE_OLD_DUPLICATES_FOLLOWUP",
})
_MEDIUM_RISK_INTENTS = frozenset({
    "N8N_RUN_WORKFLOW",
    "N8N_CREATE_WORKFLOW",
    "N8N_CREATE_FROM_TEMPLATE",
    "FIND_DUPLICATES_ONLY",
    "RESTORE_FROM_TRASH",
})

# ---------------------------------------------------------------------------
# Skill keyword mapping  (Improvement 3)
# ---------------------------------------------------------------------------

# Each entry: (list-of-keywords, filename-in-skills/instructions/)
_SKILL_KEYWORDS: List[tuple] = [
    (
        # Keep specific debug terms; avoid "error"/"fail" which also appear in
        # API-error messages and would shadow the API-errors skill.
        [
            "debug", "ошибка", "execution", "упал",
            "исправь", "исправить", "починить", "отладь", "crashed",
        ],
        "debug_n8n_workflow.md",
    ),
    (
        [
            "сложный", "complex", "много узлов", "large", "sub-workflow",
            "subworkflow", "разбить", "chunks", "части", "split",
        ],
        "create_complex_workflow.md",
    ),
    (
        [
            "400", "401", "403", "404", "429", "500", "api error",
            "rate limit", "http error", "timeout", "unauthorized",
            "forbidden", "rate", "retry",
        ],
        "handle_api_errors.md",
    ),
]


class BrainLayer:
    """Orchestrate the full User → Plan → Execute → Verify pipeline."""

    CLARIFY_RESPONSE = (
        "Could you give me a bit more detail? "
        "What exactly would you like me to do?"
    )

    def __init__(
        self,
        controller: Any,
        *,
        require_confirmation: bool = False,
        rules_file: Optional[Path] = None,
        skills_dir: Optional[Path] = None,
        memory_dir: Optional[Path] = None,
    ) -> None:
        self.controller = controller
        self.router = Router()
        self.planner = Planner()
        self.executor = Executor(controller)
        self.verifier = Verifier()
        self.error_interpreter = ErrorInterpreter()  # Improvement 4

        # Semantic LLM-based intent classifier (задание 1+2)
        # cache_dir persists cache between sessions; falls back to in-memory if None.
        _cache_dir = memory_dir if memory_dir is not None else Path(__file__).parent.parent / "memory"
        self.intent_classifier = IntentClassifier(cache_dir=_cache_dir)
        self.semantic_error_interpreter = SmartErrorInterpreter()

        # -- Improvement 2: plan confirmation state --
        self._require_confirmation = require_confirmation
        self._pending: Optional[Dict] = None

        # -- Improvement 1: learned rules --
        self._rules_file: Path = (
            rules_file
            if rules_file is not None
            else Path(__file__).parent / "learned_rules.md"
        )
        self._learned_rules: List[str] = []

        # -- Improvement 3: dynamic skills dir --
        self._skills_dir: Path = (
            skills_dir
            if skills_dir is not None
            else Path(__file__).parent.parent / "skills" / "instructions"
        )

        self._load_learned_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle(self, user_message: str) -> Dict[str, Any]:
        """Process *user_message* and return a structured result dict.

        Routing priority:
          0. Pending confirmation — if user answered to a previous plan request.
          1. Pending solution choice — if user chose a solution after error.
          2. CLARIFY — too vague, ask user first (skip controller).
          3. SLOW    — multi-step; use Plan→Execute→Verify (skip controller).
          4. FAST    — try controller; if handled wrap it, else mark unhandled.
        """
        # --- Step 0: check pending confirmation ---
        if self._pending is not None:
            pending_result = self._handle_pending(user_message)
            if pending_result is not None:
                return pending_result

        # --- Step 1: pre-route ---
        pre_path = self.router.route(user_message, controller_handled=False)

        if pre_path == "CLARIFY":
            return self._clarify_result(user_message)

        if pre_path == "SLOW":
            if self._require_confirmation:
                return self._request_plan_confirmation(user_message)
            return self._slow_path(user_message)

        # --- Step 2: FAST — try the controller ---
        ctrl_result = self.controller.handle_request(user_message)
        controller_handled = bool(ctrl_result.get("handled", False))

        # --- Step 3: Check if controller returned an error that needs interpretation ---
        if controller_handled and self._is_error_result(ctrl_result):
            return self._handle_controller_error(ctrl_result, user_message)

        if controller_handled:
            return self._fast_result(ctrl_result)

        # --- Step 4: Controller didn't handle → try LLM semantic classification ---
        # Handles phrasings the regex classifier doesn't recognise (задание 1+2).
        classified = self._semantic_classify(user_message)
        if classified is not None:
            return self._handle_semantic_intent(classified, user_message)

        return self._unhandled_result(ctrl_result)

    # ------------------------------------------------------------------
    # Semantic classifier integration (задание 1+2)
    # ------------------------------------------------------------------

    def _get_classifier_context(self) -> Dict[str, Any]:
        """Build context for LLM intent classifier based on current pending state."""
        context: Dict[str, Any] = {}
        if self._pending:
            stage = self._pending.get('stage', '')
            if stage == 'awaiting_confirm':
                context['awaiting'] = 'plan_confirmation'
            elif stage == 'awaiting_solution_choice':
                err = self._pending.get('interpreted_error')
                if err:
                    context['last_error'] = str(getattr(err, 'original_error', ''))[:200]
                context['awaiting'] = 'solution_choice'
        return context

    def _semantic_classify(self, user_message: str) -> Optional[ClassifiedIntent]:
        """Classify via LLM. Returns ClassifiedIntent if confident, else None.
        
        Called as fallback when controller.handle_request() returned handled=False.
        Non-CHAT intents with confidence >= 0.75 are routed; below that we let
        Ollama handle it naturally (CHAT fallback).
        """
        try:
            context = self._get_classifier_context()
            classified = self.intent_classifier.classify(user_message, context)
            # Only route if LLM has enough confidence and it's not a plain chat
            if classified.intent != 'CHAT' and classified.confidence >= 0.75:
                return classified
        except Exception:
            pass
        return None

    def _handle_semantic_intent(
        self, classified: ClassifiedIntent, user_message: str
    ) -> Dict[str, Any]:
        """Route a semantically classified intent to the right handler."""
        intent = classified.intent
        entities = classified.entities

        # --- Clarification needed ---
        if classified.missing_required and classified.clarify_question:
            return {
                'path': 'CLARIFY',
                'handled': True,
                'response': classified.clarify_question,
                'tool_name': 'semantic_clarify',
                'tool_result': {
                    'intent': intent,
                    'confidence': classified.confidence,
                    'missing': classified.missing_required,
                },
                'steps': [], 'plan': [], 'verified': False, 'verification': None,
            }

        # --- n8n intents: build a natural language request and re-try controller ---
        if intent == 'LIST_WORKFLOWS':
            ctrl = self.controller.handle_request('покажи все n8n workflows')
            return self._fast_result(ctrl) if ctrl.get('handled') else self._unhandled_result(ctrl)

        if intent == 'LIST_TEMPLATES':
            ctrl = self.controller.handle_request('покажи доступные шаблоны n8n workflow')
            return self._fast_result(ctrl) if ctrl.get('handled') else self._unhandled_result(ctrl)

        if intent == 'CREATE_WORKFLOW':
            request = self._build_create_request(entities, user_message)
            ctrl = self.controller.handle_request(request)
            if ctrl.get('handled'):
                return self._fast_result(ctrl) if not self._is_error_result(ctrl) else self._handle_controller_error(ctrl, user_message)
            return self._unhandled_result(ctrl)

        if intent == 'DEBUG_WORKFLOW':
            wf = entities.get('workflow_name') or entities.get('workflow_id', '')
            ctrl = self.controller.handle_request(f'отладь n8n workflow {wf}')
            return self._fast_result(ctrl) if ctrl.get('handled') else self._unhandled_result(ctrl)

        if intent == 'RUN_WORKFLOW':
            wf = entities.get('workflow_name') or entities.get('workflow_id', '')
            ctrl = self.controller.handle_request(f'запусти n8n workflow {wf}')
            return self._fast_result(ctrl) if ctrl.get('handled') else self._unhandled_result(ctrl)

        # --- Other tool intents: pass original message to controller ---
        if intent in ('MANAGE_FILES', 'SYSTEM_INFO', 'WEB_SEARCH', 'SEND_MESSAGE', 'OPEN_URL'):
            ctrl = self.controller.handle_request(user_message)
            return self._fast_result(ctrl) if ctrl.get('handled') else self._unhandled_result(ctrl)

        # --- CONFIRM / CANCEL without pending state ---
        if intent == 'CONFIRM':
            return {
                'path': 'FAST', 'handled': True,
                'response': 'Хорошо! Уточни, что именно подтвердить.',
                'tool_name': 'semantic_confirm', 'tool_result': None,
                'steps': [], 'plan': [], 'verified': False, 'verification': None,
            }

        if intent == 'CANCEL':
            self._pending = None
            return {
                'path': 'FAST', 'handled': True,
                'response': 'Хорошо, отменено. Чем могу помочь?',
                'tool_name': 'cancelled', 'tool_result': None,
                'steps': [], 'plan': [], 'verified': False, 'verification': None,
            }

        # Fallback — let Ollama handle
        return self._unhandled_result({'response': ''})

    def _build_create_request(self, entities: Dict[str, Any], original: str) -> str:
        """Build a structured request string from classified entities."""
        source = entities.get('source', '')
        channels = entities.get('channels', [])
        schedule = entities.get('schedule', '')
        schedule_time = entities.get('schedule_time', '')
        destination = entities.get('destination', 'telegram')
        topic = entities.get('topic', '')
        fmt = entities.get('format', '')

        if isinstance(channels, list):
            channels_str = ', '.join(channels)
        else:
            channels_str = str(channels)

        parts = ['создай n8n workflow:']
        if source == 'telegram' and channels_str:
            parts.append(f'собирать посты из телеграм каналов {channels_str}')
        elif source:
            parts.append(f'источник: {source}')
        if schedule:
            time_part = f' в {schedule_time}' if schedule_time else ''
            parts.append(f'расписание: {schedule}{time_part}')
        if topic:
            parts.append(f'тема: {topic}')
        if fmt:
            parts.append(f'формат: {fmt}')
        if destination:
            parts.append(f'отправлять в: {destination}')

        return ' | '.join(parts) if len(parts) > 1 else original

    # ------------------------------------------------------------------
    # Improvement 4: Error interpretation
    # ------------------------------------------------------------------

    def _is_error_result(self, ctrl_result: Dict[str, Any]) -> bool:
        """Check if controller result indicates an error that should be interpreted."""
        # Explicit error flag
        if ctrl_result.get("success") is False:
            return True
        
        # Check for error indicators in response
        response = str(ctrl_result.get("response", "")).lower()
        error_indicators = [
            "status=stopped",
            "cannot fix automatically",
            "forbidden",
            "error",
            "failed",
            "не удалось",
            "ошибка",
            "needs_attention",
        ]
        
        # Must have error indicator AND not be a successful completion
        if any(ind in response for ind in error_indicators):
            # Avoid false positives for successful error handling messages
            success_indicators = ["успешно", "готов", "создан", "completed", "success"]
            if not any(s in response for s in success_indicators):
                return True
        
        return False

    def _handle_controller_error(
        self, 
        ctrl_result: Dict[str, Any], 
        user_message: str
    ) -> Dict[str, Any]:
        """Interpret a controller error and return user-friendly response with solutions."""
        
        # Extract error message from various possible locations
        error_msg = self._extract_error_message(ctrl_result)
        
        # Build context for interpretation
        context = self._build_error_context(ctrl_result, user_message)
        
        # Interpret the error
        interpreted = self.error_interpreter.interpret(error_msg, context)
        
        # Store pending state if there are auto-executable solutions
        auto_solutions = [s for s in interpreted.solutions if s.auto_executable]
        if auto_solutions or interpreted.can_retry_with_modification:
            self._pending = {
                "stage": "awaiting_solution_choice",
                "interpreted_error": interpreted,
                "original_request": user_message,
                "ctrl_result": ctrl_result,
                "context": context,
            }
        
        return self._error_interpretation_result(interpreted, ctrl_result)

    def _extract_error_message(self, ctrl_result: Dict[str, Any]) -> str:
        """Extract the actual error message from controller result."""
        # Try explicit error field first
        if ctrl_result.get("error"):
            return str(ctrl_result["error"])
        
        # Try nested context
        context = ctrl_result.get("context", {})
        if context.get("last_error"):
            return str(context["last_error"])
        
        # Parse from response string
        response = str(ctrl_result.get("response", ""))
        
        # Look for common patterns
        patterns = [
            r"msg=([^\n]+)",
            r"reason=([^\n]+)", 
            r"error[=:]([^\n]+)",
            r"Forbidden[^\n]*",
            r"403[^\n]*",
            r"timeout[^\n]*",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        
        # Fallback to full response
        return response[:500] if response else "Unknown error"

    def _build_error_context(
        self, 
        ctrl_result: Dict[str, Any], 
        user_message: str
    ) -> Dict[str, Any]:
        """Build context dict for error interpretation."""
        context = {
            "task": user_message,
            "step": ctrl_result.get("tool_name", ""),
            "params": {},
            "service": self._detect_service(user_message, ctrl_result),
        }
        
        # Extract params from various locations
        if ctrl_result.get("context"):
            context["params"] = ctrl_result["context"].get("params", {})
        
        if ctrl_result.get("tool_result"):
            tool_result = ctrl_result["tool_result"]
            if isinstance(tool_result, dict):
                context["params"].update(tool_result)
        
        # Count items from user message (channels, URLs, etc.)
        channels = re.findall(r"@[\w]+", user_message)
        if channels:
            context["params"]["channels"] = channels
        
        return context

    def _detect_service(self, task: str, ctrl_result: Dict[str, Any]) -> str:
        """Determine which service is involved based on task and result."""
        task_lower = task.lower()
        result_str = str(ctrl_result).lower()
        
        if "rsshub" in task_lower or "rsshub" in result_str:
            return "rsshub"
        if "telegram" in task_lower:
            return "telegram"
        if "twitter" in task_lower or "x.com" in task_lower:
            return "twitter"
        if "instagram" in task_lower:
            return "instagram"
        if "n8n" in task_lower:
            return "n8n"
        if "social_parser" in result_str:
            return "rsshub"  # social_parser uses rsshub
        
        return "unknown"

    def _error_interpretation_result(
        self, 
        interpreted: InterpretedError,
        ctrl_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build result dict with interpreted error and solutions."""
        return {
            "path": "FAST",
            "handled": True,
            "response": interpreted.user_message,
            "tool_name": "brain_error_analysis",
            "tool_result": {
                "error_type": interpreted.error_type,
                "likely_cause": interpreted.likely_cause,
                "solutions": [
                    {
                        "title": s.title,
                        "description": s.description,
                        "complexity": s.complexity,
                        "auto_executable": s.auto_executable,
                    }
                    for s in interpreted.solutions
                ],
                "can_auto_retry": interpreted.can_retry_with_modification,
                "suggested_modification": interpreted.suggested_modification,
                "original_error": interpreted.original_error,
            },
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "awaiting_solution": True,
            "original_ctrl_result": ctrl_result,
        }

    def _handle_solution_choice(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Handle user's choice of solution after error interpretation."""
        if self._pending is None or self._pending.get("stage") != "awaiting_solution_choice":
            return None
    
        msg = user_message.strip()
        msg_lower = msg.lower()
        interpreted: InterpretedError = self._pending["interpreted_error"]
        original_request = self._pending["original_request"]
        context = self._pending["context"]
    
        # --- NEW: Check if user provided credentials/API key ---
        credentials = self._extract_credentials_from_message(msg)
        if credentials:
            return self._retry_with_credentials(original_request, context, credentials)
    
        # Check for solution number choice (1, 2, 3, etc.)
        number_match = re.search(r"^(\d+)$|вариант\s*(\d+)|option\s*(\d+)", msg_lower)
        if number_match:
            choice = int(next(g for g in number_match.groups() if g))
            if 1 <= choice <= len(interpreted.solutions):
                solution = interpreted.solutions[choice - 1]
                return self._execute_solution(solution, original_request, context)
    
        # Check for "да" / "yes" — execute first auto-executable solution
        _YES = ["да", "yes", "ок", "ok", "давай", "попробуй", "сделай", "1"]
        if any(w in msg_lower for w in _YES):
            auto_solutions = [s for s in interpreted.solutions if s.auto_executable]
            if auto_solutions:
                return self._execute_solution(auto_solutions[0], original_request, context)
            elif interpreted.can_retry_with_modification:
                return self._retry_with_modification(
                    original_request, 
                    interpreted.suggested_modification
                )
    
        # Check for "нет" / "no" — cancel
        _NO = ["нет", "no", "отмен", "cancel", "не надо", "другой", "иначе"]
        if any(w in msg_lower for w in _NO):
            self._pending = None
            return {
                "path": "FAST",
                "handled": True,
                "response": "Хорошо, отменено. Опиши задачу по-другому, если хочешь попробовать иначе.",
                "tool_name": "solution_cancelled",
                "tool_result": None,
                "steps": [],
                "plan": [],
                "verified": False,
                "verification": None,
            }
    
        # --- NEW: Check if user is asking clarifying question ---
        if "?" in msg or any(q in msg_lower for q in ["какой", "какого", "к чему", "от чего", "what", "which"]):
            return self._answer_clarifying_question(msg, interpreted, context)
    
        # Unrecognised — show solutions again
        return {
            "path": "FAST",
            "handled": True,
            "response": (
                "Не понял выбор. Напиши номер варианта (1, 2, 3...) или 'да' для первого варианта.\n\n"
                + interpreted.user_message
            ),
            "tool_name": "brain_error_analysis",
            "tool_result": None,
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "awaiting_solution": True,
        }

    def _extract_credentials_from_message(self, msg: str) -> Optional[Dict[str, str]]:
        """Extract API keys, tokens, or other credentials from user message."""
        credentials = {}
    
        # Telegram bot token pattern: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
        bot_token_match = re.search(r'\b(\d{8,10}:[A-Za-z0-9_-]{35})\b', msg)
        if bot_token_match:
            credentials["telegram_bot_token"] = bot_token_match.group(1)
    
        # Telegram user ID pattern
        user_id_match = re.search(r'id[:\s]*(\d{6,12})|(\d{9,12})', msg, re.IGNORECASE)
        if user_id_match:
            credentials["telegram_user_id"] = user_id_match.group(1) or user_id_match.group(2)
    
        # Generic API key patterns
        api_key_match = re.search(r'api[_\s]?key[:\s]*([A-Za-z0-9_-]{20,})', msg, re.IGNORECASE)
        if api_key_match:
            credentials["api_key"] = api_key_match.group(1)
    
        # Bearer token
        bearer_match = re.search(r'bearer[:\s]*([A-Za-z0-9_.-]+)', msg, re.IGNORECASE)
        if bearer_match:
            credentials["bearer_token"] = bearer_match.group(1)
    
        return credentials if credentials else None

    def _retry_with_credentials(
        self, 
        original_request: str, 
        context: Dict[str, Any],
        credentials: Dict[str, str]
    ) -> Dict[str, Any]:
        """Retry the original request with provided credentials."""
        self._pending = None
    
        # Store credentials in context for the retry
        context["credentials"] = credentials
    
        # Build informative response
        cred_types = []
        if "telegram_bot_token" in credentials:
            cred_types.append("токен Telegram бота")
        if "telegram_user_id" in credentials:
            cred_types.append("Telegram ID")
        if "api_key" in credentials:
            cred_types.append("API ключ")
    
        cred_summary = ", ".join(cred_types)
    
        return {
            "path": "FAST",
            "handled": True,
            "response": f"Получил {cred_summary}. Сейчас создам workflow с этими данными и попробую запустить снова.",
            "tool_name": "retry_with_credentials",
            "tool_result": {
                "credentials_received": list(credentials.keys()),
                "original_request": original_request,
            },
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "next_action": {
                "type": "retry_with_credentials",
                "request": original_request,
                "credentials": credentials,
                "context": context,
            },
        }

    def _answer_clarifying_question(
        self, 
        question: str, 
        interpreted: InterpretedError,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Answer user's clarifying question about the error or solutions."""
        question_lower = question.lower()
    
        # Detect what they're asking about
        if any(w in question_lower for w in ["какой", "какого", "к чему", "от чего", "what", "which"]):
            if "api" in question_lower or "ключ" in question_lower or "key" in question_lower:
                service = context.get("service", "unknown")
            
                # Service-specific answers
                if service == "rsshub" or service == "telegram":
                    answer = (
                        "Для чтения постов из Telegram-каналов через RSSHub не нужен API ключ — "
                        "это публичный сервис.\n\n"
                        "Но rsshub.app имеет лимиты. Варианты:\n"
                        "1. **Свой RSSHub** — `docker run -d -p 1200:1200 diygod/rsshub`\n"
                        "2. **Telegram Bot API** — создай бота через @BotFather, добавь в каналы, "
                        "дай мне токен бота (формат: `123456789:ABCdef...`)\n\n"
                        "Какой вариант выбираешь?"
                    )
                elif service == "n8n":
                    answer = (
                        "Для n8n нужен API ключ из настроек n8n:\n"
                        "Settings → API → Create API Key\n\n"
                        "Или проверь файл `.env` — там должен быть `N8N_API_KEY`."
                    )
                else:
                    answer = (
                        f"Сервис: {service}\n\n"
                        f"Ошибка была: {interpreted.likely_cause}\n\n"
                        "Уточни, какой именно сервис ты хочешь использовать, "
                        "и я скажу, какие credentials нужны."
                    )
            
                return {
                    "path": "FAST",
                    "handled": True,
                    "response": answer,
                    "tool_name": "clarifying_answer",
                    "tool_result": {"question": question, "service": service},
                    "steps": [],
                    "plan": [],
                    "verified": False,
                    "verification": None,
                    "awaiting_solution": True,  # Keep waiting for solution
                }
    
        # Generic: re-explain the error
        return {
            "path": "FAST",
            "handled": True,
            "response": (
                f"Ошибка: {interpreted.likely_cause}\n\n"
                f"{interpreted.user_message}"
            ),
            "tool_name": "clarifying_answer",
            "tool_result": None,
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "awaiting_solution": True,
        }

    def _execute_solution(
        self, 
        solution, 
        original_request: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a chosen solution."""
        self._pending = None
    
        # If solution requires user action, explain what to do
        if solution.requires_user_action and not solution.auto_executable:
            return {
                "path": "FAST",
                "handled": True,
                "response": f"Для этого варианта нужно твоё участие:\n\n{solution.description}",
                "tool_name": "solution_requires_user",
                "tool_result": {"solution": solution.title},
                "steps": [],
                "plan": [],
                "verified": False,
                "verification": None,
            }
    
        # Build modified request based on solution
        modified_request = self._build_modified_request(
            original_request, solution, context
        )
    
        # Execute the modified request
        return {
            "path": "FAST",
            "handled": True,
            "response": f"Пробую: {solution.title}\n\n{solution.description}",
            "tool_name": "solution_executing",
            "tool_result": {"solution": solution.title, "modified_request": modified_request},
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "next_action": {
                "type": "retry_modified",
                "request": modified_request,
            },
        }

    def _build_modified_request(
        self, 
        original_request: str, 
        solution, 
        context: Dict[str, Any]
    ) -> str:
        """Build a modified request based on the solution."""
        # For "reduce items" solution — limit to first 5 channels
        if "меньш" in solution.title.lower() or "начать" in solution.title.lower():
            channels = context.get("params", {}).get("channels", [])
            if isinstance(channels, list) and len(channels) > 5:
                limited_channels = " ".join(channels[:5])
                # Replace original channels with limited set
                for ch in channels:
                    original_request = original_request.replace(ch, "")
                original_request = original_request.strip() + " " + limited_channels
    
        return original_request

    def _retry_with_modification(
        self, 
        original_request: str, 
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Retry the original request with suggested modifications."""
        self._pending = None
    
        reason = modification.get("reason", "Пробую с изменениями")
    
        return {
            "path": "FAST",
            "handled": True,
            "response": reason,
            "tool_name": "solution_retry_modified",
            "tool_result": {"modification": modification},
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "next_action": {
                "type": "retry_modified",
                "modification": modification,
            },
        }

    # ------------------------------------------------------------------
    # Improvement 1: Active learning loop
    # ------------------------------------------------------------------

    def _load_learned_rules(self) -> None:
        """Read rules from learned_rules.md into memory on startup."""
        try:
            content = self._rules_file.read_text(encoding="utf-8")
            self._learned_rules = [
                line.strip()
                for line in content.splitlines()
                if line.strip().startswith("[")
            ]
        except FileNotFoundError:
            self._learned_rules = []

    def _save_learned_rule(
        self, context: str, error: str, fix: str, rule: str
    ) -> None:
        """Append a new learned rule to the file and update in-memory list."""
        entry = (
            f"[{date.today()}] [{context}] → [{error}] → [{fix}] → [{rule}]\n"
        )
        with open(self._rules_file, "a", encoding="utf-8") as fh:
            fh.write(entry)
        self._learned_rules.append(entry.strip())

    # ------------------------------------------------------------------
    # Improvement 3: Dynamic skills
    # ------------------------------------------------------------------

    def _find_relevant_skill(self, task_description: str) -> Optional[str]:
        """Return the content of the most relevant skill instruction file,
        or None if no keyword match is found."""
        msg = task_description.lower()
        for keywords, filename in _SKILL_KEYWORDS:
            if any(kw in msg for kw in keywords):
                path = self._skills_dir / filename
                try:
                    return path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    return None
        return None

    def _get_learned_lessons(self) -> str:
        """Return the content of learned_lessons.md (from skills/instructions/).
        Returns empty string if file is missing or empty."""
        path = self._skills_dir / "learned_lessons.md"
        try:
            content = path.read_text(encoding="utf-8").strip()
            return content if content else ""
        except FileNotFoundError:
            return ""

    # ------------------------------------------------------------------
    # Improvement 2: Plan confirmation
    # ------------------------------------------------------------------

    def _assess_risk(self, plan_steps: List[PlanStep]) -> str:
        """Classify overall risk of a plan: 'low', 'medium', or 'high'."""
        intents = {s.intent for s in plan_steps}
        if intents & _HIGH_RISK_INTENTS:
            return "high"
        if len(plan_steps) >= 2 or (intents & _MEDIUM_RISK_INTENTS):
            return "medium"
        return "low"

    def _format_plan_for_user(
        self, plan_steps: List[PlanStep], user_message: str
    ) -> str:
        """Format a plan into a human-readable string with risk assessment."""
        risk = self._assess_risk(plan_steps)
        affected = ", ".join(dict.fromkeys(s.intent for s in plan_steps))

        lines = ["ПЛАН ВЫПОЛНЕНИЯ:", ""]
        for i, step in enumerate(plan_steps):
            dep_str = (
                f" (зависит от шага {step.depends_on})"
                if step.depends_on
                else ""
            )
            lines.append(f"  {i + 1}. {step.description}{dep_str}")

        lines.extend([
            "",
            f"Изменяемые области: {affected}",
            f"Оценка риска: {risk.upper()}",
            "",
            "Выполнить? (да / нет / изменить)",
        ])
        return "\n".join(lines)

    def _request_plan_confirmation(self, user_message: str) -> Dict[str, Any]:
        """Generate a plan and ask the user to confirm before executing."""
        plan_steps = self.planner.plan(user_message)
        formatted = self._format_plan_for_user(plan_steps, user_message)
        self._pending = {
            "stage": "awaiting_confirm",
            "plan": plan_steps,
            "user_message": user_message,
        }
        return {
            "path": "SLOW",
            "handled": True,
            "response": formatted,
            "tool_name": "plan_confirmation",
            "tool_result": {
                "plan": [
                    {"intent": s.intent, "description": s.description}
                    for s in plan_steps
                ]
            },
            "steps": [],
            "plan": plan_steps,
            "verified": False,
            "verification": None,
            "awaiting_confirmation": True,
        }

    def _handle_pending(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Handle user response to a pending state (confirmation or solution choice)."""
        if self._pending is None:
            return None

        stage = self._pending.get("stage", "")

        # Handle solution choice (Improvement 4)
        if stage == "awaiting_solution_choice":
            return self._handle_solution_choice(user_message)

        # Handle plan confirmation (Improvement 2)
        if stage == "awaiting_confirm":
            return self._handle_plan_confirmation(user_message)

        if stage == "awaiting_modification":
            return self._handle_plan_modification(user_message)

        return None  # unknown stage — fall through

    def _handle_plan_confirmation(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Handle user's response to plan confirmation."""
        msg = user_message.strip().lower()

        _YES = ["да", "yes", "ок", "ok", "выполн", "подтвер",
                "go", "proceed", "конечно", "давай"]
        _NO  = ["нет", "no", "отмен", "cancel", "стоп", "stop",
                "не надо", "не выполн"]
        _MOD = ["изменить", "modify", "change", "update",
                "другой", "скорректировать", "поправить"]

        if any(w in msg for w in _YES):
            plan          = self._pending["plan"]
            original_msg  = self._pending["user_message"]
            self._pending = None
            return self._slow_path(original_msg, plan_steps=plan)

        if any(w in msg for w in _NO):
            self._pending = None
            return self._cancelled_result()

        if any(w in msg for w in _MOD):
            self._pending["stage"] = "awaiting_modification"
            return self._ask_modification_result()

        # Unrecognised — re-show the plan
        formatted = self._format_plan_for_user(
            self._pending["plan"], self._pending["user_message"]
        )
        return {
            "path": "SLOW",
            "handled": True,
            "response": (
                "Пожалуйста, ответь: да / нет / изменить\n\n" + formatted
            ),
            "tool_name": "plan_confirmation",
            "tool_result": None,
            "steps": [],
            "plan": self._pending["plan"],
            "verified": False,
            "verification": None,
            "awaiting_confirmation": True,
        }

    def _handle_plan_modification(self, user_message: str) -> Dict[str, Any]:
        """Handle user's modification request for the plan."""
        # User described what to change → re-plan with combined message
        original_msg  = self._pending["user_message"]
        combined_msg  = f"{original_msg} ({user_message})"
        self._pending = None
        return self._request_plan_confirmation(combined_msg)

    def _cancelled_result(self) -> Dict[str, Any]:
        return {
            "path": "SLOW",
            "handled": True,
            "response": "Выполнение отменено.",
            "tool_name": "plan_cancelled",
            "tool_result": None,
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "awaiting_confirmation": False,
        }

    def _ask_modification_result(self) -> Dict[str, Any]:
        return {
            "path": "SLOW",
            "handled": True,
            "response": "Что именно нужно изменить в плане?",
            "tool_name": "plan_modification_request",
            "tool_result": None,
            "steps": [],
            "plan": self._pending["plan"] if self._pending else [],
            "verified": False,
            "verification": None,
            "awaiting_confirmation": True,
        }

    # ------------------------------------------------------------------
    # Path handlers
    # ------------------------------------------------------------------

    def _fast_result(self, ctrl_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "path": "FAST",
            "handled": True,
            "response": ctrl_result.get("response", ""),
            "tool_name": ctrl_result.get("tool_name", ""),
            "tool_result": ctrl_result.get("tool_result"),
            "steps": ctrl_result.get("steps", []),
            "plan": [],
            "verified": True,
            "verification": None,
        }

    def _clarify_result(self, user_message: str) -> Dict[str, Any]:
        return {
            "path": "CLARIFY",
            "handled": True,
            "response": self.CLARIFY_RESPONSE,
            "tool_name": "clarify",
            "tool_result": None,
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
        }

    def _unhandled_result(self, ctrl_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "path": "FAST",
            "handled": False,
            "response": ctrl_result.get("response", ""),
            "tool_name": "",
            "tool_result": None,
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
        }

    def _slow_path(
        self,
        user_message: str,
        plan_steps: Optional[List[PlanStep]] = None,
    ) -> Dict[str, Any]:
        """Execute the full Plan → Execute → Verify pipeline.

        Parameters
        ----------
        user_message:
            Original user message (used for skill lookup and planning).
        plan_steps:
            Pre-generated plan (used when called after confirmation).
            If None, Planner.plan() is called.
        """
        # Plan (or use pre-generated)
        if plan_steps is None:
            plan_steps = self.planner.plan(user_message)

        # --- Improvement 3: find relevant skill + learned lessons ---
        skill_context = self._find_relevant_skill(user_message)
        lessons       = self._get_learned_lessons()

        # Execute
        step_results: List[StepResult] = self.executor.execute_plan(plan_steps)

        # --- Improvement 4: Check for step failures and interpret errors ---
        failed_steps = [r for r in step_results if not r.success and not r.skipped]
        if failed_steps:
            # Get the first failure and interpret it
            first_failure = failed_steps[0]
            return self._handle_step_failure(
                step_result=first_failure,
                step=plan_steps[first_failure.step_index] if first_failure.step_index < len(plan_steps) else None,
                original_request=user_message,
                params=plan_steps[first_failure.step_index].params if first_failure.step_index < len(plan_steps) else {}
            )

        # Verify
        verification: VerificationResult = self.verifier.verify(step_results)

        # Build response text
        response_lines = [f"[SLOW] {verification.summary}"]
        for r in step_results:
            status = "OK" if r.success else ("SKIP" if r.skipped else "FAIL")
            response_lines.append(
                f"  step {r.step_index} [{status}] {r.intent}: "
                f"{r.response[:120] if r.response else r.error[:120] if r.error else ''}"
            )
        if verification.issues:
            response_lines.append("Issues:")
            for issue in verification.issues:
                response_lines.append(f"  - {issue}")

        result: Dict[str, Any] = {
            "path": "SLOW",
            "handled": True,
            "response": "\n".join(response_lines),
            "tool_name": "brain_slow_path",
            "tool_result": {
                "plan": [
                    {"intent": s.intent, "description": s.description,
                     "params": s.params, "depends_on": s.depends_on}
                    for s in plan_steps
                ],
                "step_results": [
                    {"index": r.step_index, "intent": r.intent,
                     "success": r.success, "skipped": r.skipped,
                     "response": r.response, "error": r.error}
                    for r in step_results
                ],
                "verification": {
                    "ok": verification.ok,
                    "summary": verification.summary,
                    "issues": verification.issues,
                },
            },
            "steps": [
                {"intent": r.intent, "success": r.success,
                 "response": r.response}
                for r in step_results
            ],
            "plan": plan_steps,
            "verified": verification.ok,
            "verification": verification,
            "awaiting_confirmation": False,
        }

        # --- Attach skill context and learned rules to result ---
        if skill_context:
            result["skill_context"] = skill_context
        if lessons:
            result["learned_lessons"] = lessons
        if self._learned_rules:
            result["learned_rules"] = self._learned_rules

        return result

    def _handle_step_failure(
        self,
        step_result: StepResult,
        step: Optional[PlanStep],
        original_request: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle a failed step: interpret the error and suggest solutions.
    
        Instead of returning raw logs, analyze the error in context
        and return a human-readable response with solution options.
        """
        # Build context for interpreter
        context = {
            "task": original_request,
            "step": step.intent if step else str(step_result.intent),
            "params": params,
            "service": self._detect_service(original_request, {"tool_result": params}),
        }
    
        # Interpret the error
        error_msg = step_result.error or str(step_result.response) or "Unknown error"
        interpreted = self.error_interpreter.interpret(error_msg, context)
    
        # Store pending state for solution choice
        auto_solutions = [s for s in interpreted.solutions if s.auto_executable]
        if auto_solutions or interpreted.can_retry_with_modification:
            self._pending = {
                "stage": "awaiting_solution_choice",
                "interpreted_error": interpreted,
                "original_request": original_request,
                "context": context,
                "failed_step": step_result,
            }
    
        return {
            "path": "SLOW",
            "handled": True,
            "response": interpreted.user_message,
            "tool_name": "brain_error_analysis",
            "tool_result": {
                "error_type": interpreted.error_type,
                "likely_cause": interpreted.likely_cause,
                "solutions": [
                    {
                        "title": s.title,
                        "description": s.description,
                        "complexity": s.complexity,
                        "auto_executable": s.auto_executable,
                    }
                    for s in interpreted.solutions
                ],
                "can_auto_retry": interpreted.can_retry_with_modification,
                "suggested_modification": interpreted.suggested_modification,
                "original_error": interpreted.original_error,
                "failed_step_index": step_result.step_index,
                "failed_intent": step_result.intent,
            },
            "steps": [],
            "plan": [],
            "verified": False,
            "verification": None,
            "awaiting_solution": True,
        }
