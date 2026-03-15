#!/usr/bin/env python3
"""
Патч для интеграции Agent Controller Layer в agent_v3.py

УСТАНОВКА:
==========
1. Скопировать controller.py в папку с agent_v3.py
2. Применить изменения из этого файла к agent_v3.py

ИЗМЕНЕНИЯ:
==========
"""

# ============================================================
# ИЗМЕНЕНИЕ 1: Импорт контроллера (добавить после импортов)
# ============================================================
# Строка ~37 (после import io)

"""
# ---- ADD THIS ----
try:
    from controller import create_controller
    CONTROLLER_AVAILABLE = True
except ImportError:
    CONTROLLER_AVAILABLE = False
    print("⚠️  Controller module not found. Running in legacy mode.")
"""


# ============================================================
# ИЗМЕНЕНИЕ 2: Создание контроллера (после определения TOOLS)
# ============================================================
# Строка ~1830 (после TOOLS = {...})

"""
# ---- ADD THIS ----
# ============================================================
# AGENT CONTROLLER LAYER (v5.2+)
# ============================================================
CONTROLLER = None
if CONTROLLER_AVAILABLE:
    try:
        CONTROLLER = create_controller(MEMORY_DIR, TOOLS)
        print(f"✅ Agent Controller Layer initialized")
    except Exception as e:
        print(f"⚠️  Failed to initialize Controller: {e}")
        CONTROLLER = None
"""


# ============================================================
# ИЗМЕНЕНИЕ 3: Интеграция в process_message()
# ============================================================
# Строка ~1975 (в начале функции process_message, ПЕРЕД smart intent detection)

"""
def process_message(user_message: str, history: list) -> dict:
    # ---- ADD THIS BLOCK AT THE VERY BEGINNING ----
    
    # ============================================================
    # CONTROLLER LAYER (if available)
    # ============================================================
    if CONTROLLER:
        try:
            controller_result = CONTROLLER.handle_request(user_message)
            
            if controller_result.get("handled"):
                # Запрос обработан через controller
                print(f"🎯 Handled by Controller: {controller_result.get('thinking', '')}")
                
                # Log interaction
                log_interaction(user_message, 
                               controller_result.get("tool_name", "controller"),
                               controller_result.get("tool_result", ""))
                
                # Update profile
                update_profile_from_conversation(user_message,
                                                controller_result.get("tool_name", "controller"),
                                                controller_result.get("response", ""))
                
                # Save history
                history.append({"role": "user", "content": user_message})
                save_chat_history(history)
                
                # Return controller result
                return controller_result
        
        except Exception as e:
            print(f"⚠️  Controller error: {e}")
            # Fall through to legacy LLM processing
    
    # ---- END OF CONTROLLER BLOCK ----
    # If not handled by controller, continue with existing code...
    
    steps = []  # Track all tool calls for this message
    last_tool_name = None
    last_tool_result = None
    
    # ... rest of process_message continues as before ...
"""


# ============================================================
# ИЗМЕНЕНИЕ 4: Улучшение tool_find_duplicates для State Manager
# ============================================================
# Строка ~537 (функция tool_find_duplicates)

"""
def tool_find_duplicates(path: str) -> str:
    # Existing code...
    try:
        files_by_size = {}
        for root, dirs, files in os.walk(path):
            # ... (existing scan code) ...
        
        duplicates = {k: v for k, v in files_by_size.items() if len(v) > 1}
        
        # ---- ADD THIS: Update controller state if available ----
        if CONTROLLER and duplicates:
            try:
                CONTROLLER.state.update_duplicates_scan(path, duplicates)
            except:
                pass
        # ---- END ----
        
        if not duplicates:
            return f"No duplicates found in {path}"
        
        # ... rest of function continues ...
"""


# ============================================================
# ИЗМЕНЕНИЕ 5: Защита delete_files от несуществующих путей
# ============================================================
# Строка ~1328 (функция tool_delete_files)

"""
def tool_delete_files(paths: list, permanent: bool = False) -> str:
    # ---- ADD THIS AT THE BEGINNING ----
    # Validate all paths exist before deletion
    missing_paths = [p for p in paths if not os.path.exists(p)]
    if missing_paths:
        error_msg = f"❌ Не могу удалить несуществующие файлы:\\n"
        for p in missing_paths[:5]:  # show max 5
            error_msg += f"  - {p}\\n"
        if len(missing_paths) > 5:
            error_msg += f"  ... и ещё {len(missing_paths) - 5}\\n"
        error_msg += f"\\n💡 Подсказка: используй find_duplicates или list_files чтобы получить реальные пути."
        return error_msg
    # ---- END ----
    
    # ... existing deletion code continues ...
"""

# ============================================================
# ПОЛНЫЙ ПРИМЕР ИНТЕГРАЦИИ
# ============================================================

INTEGRATION_EXAMPLE = """
# Пример использования в agent_v3.py после интеграции:

# 1. Пользователь: "найди дубликаты в Downloads и удали старые"
#    → Controller распознаёт CLEAN_DUPLICATES_KEEP_NEWEST
#    → Выполняет clean_duplicates напрямую
#    → Результат возвращается без LLM

# 2. Пользователь: "найди дубликаты в Downloads"
#    → Controller распознаёт FIND_DUPLICATES_ONLY
#    → Выполняет find_duplicates
#    → Сохраняет состояние: pending_intent = "CLEAN_DUPLICATES_AVAILABLE"

# 3. Пользователь (follow-up): "удали старые"
#    → Controller проверяет pending_intent
#    → Распознаёт DELETE_OLD_DUPLICATES_FOLLOWUP
#    → Использует сохранённый last_duplicates_path
#    → Выполняет clean_duplicates без LLM

# 4. Пользователь: "напиши мне письмо директору"
#    → Controller не распознаёт намерение
#    → Возвращает {"handled": False}
#    → Передаётся в legacy LLM processing
"""

print(INTEGRATION_EXAMPLE)
