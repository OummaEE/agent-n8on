#!/usr/bin/env python3
"""
Автоматический установщик Agent Controller Layer для agent_v3.py

ИСПОЛЬЗОВАНИЕ:
    python install_controller.py

Что делает:
    1. Создаёт резервную копию agent_v3.py → agent_v3_backup.py
    2. Применяет все необходимые изменения автоматически
    3. Проверяет корректность интеграции
"""

import os
import shutil
import re
from datetime import datetime


def backup_file(filepath: str) -> str:
    """Создать резервную копию файла"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.replace(".py", f"_backup_{timestamp}.py")
    shutil.copy2(filepath, backup_path)
    return backup_path


def read_file(filepath: str) -> str:
    """Прочитать файл"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def write_file(filepath: str, content: str):
    """Записать файл"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def apply_patch(agent_code: str) -> str:
    """Применить все изменения к коду agent_v3.py"""
    
    # ============================================================
    # PATCH 1: Добавить импорт контроллера
    # ============================================================
    import_section = """
# ============================================================
# AGENT CONTROLLER LAYER (v5.2+)
# ============================================================
try:
    from controller import create_controller
    CONTROLLER_AVAILABLE = True
except ImportError:
    CONTROLLER_AVAILABLE = False
    print("⚠️  Controller module not found. Running in legacy mode.")
"""
    
    # Найти место после импортов (перед первым комментарием "# ====")
    pattern = r'(import io\n)'
    if re.search(pattern, agent_code):
        agent_code = re.sub(pattern, r'\1' + import_section, agent_code, count=1)
    
    # ============================================================
    # PATCH 2: Инициализация контроллера (после TOOLS dict)
    # ============================================================
    controller_init = """
# ============================================================
# CONTROLLER INITIALIZATION
# ============================================================
CONTROLLER = None
if CONTROLLER_AVAILABLE:
    try:
        CONTROLLER = create_controller(MEMORY_DIR, TOOLS)
        print(f"✅ Agent Controller Layer v1.0 initialized")
    except Exception as e:
        print(f"⚠️  Failed to initialize Controller: {e}")
        CONTROLLER = None
"""
    
    # Найти конец секции TOOLS (строка вида "TOOLS = {...}")
    # Вставить после неё
    pattern = r'(\n# ====.*?\n# LLM COMMUNICATION.*?\n# ====)'
    if re.search(pattern, agent_code, re.DOTALL):
        agent_code = re.sub(pattern, controller_init + r'\1', agent_code, count=1)
    
    # ============================================================
    # PATCH 3: Интеграция в process_message
    # ============================================================
    controller_handler = """    # ============================================================
    # CONTROLLER LAYER — INTENT-BASED ROUTING (v5.2+)
    # ============================================================
    if CONTROLLER:
        try:
            controller_result = CONTROLLER.handle_request(user_message)
            
            if controller_result.get("handled"):
                # Запрос обработан через controller
                print(f"🎯 Handled by Controller: {controller_result.get('thinking', '')[:100]}")
                
                # Log interaction
                log_interaction(user_message, 
                               controller_result.get("tool_name", "controller"),
                               controller_result.get("tool_result", ""))
                
                # Update profile
                update_profile_from_conversation(user_message,
                                                controller_result.get("tool_name", "controller"),
                                                str(controller_result.get("response", ""))[:500])
                
                # Save history
                history.append({"role": "user", "content": user_message})
                save_chat_history(history)
                
                # Return controller result (bypass LLM entirely)
                return controller_result
        
        except Exception as e:
            print(f"⚠️  Controller error: {e}")
            # Fall through to legacy LLM processing
    
    # ---- If not handled by controller, continue with LLM-based processing ----
    
    """
    
    # Найти начало process_message и вставить handler
    pattern = r'(def process_message\(user_message: str, history: list\) -> dict:\n    """.*?""")\n(    steps = \[\])'
    replacement = r'\1\n' + controller_handler + r'\2'
    agent_code = re.sub(pattern, replacement, agent_code, flags=re.DOTALL, count=1)
    
    # ============================================================
    # PATCH 4: Улучшение tool_find_duplicates
    # ============================================================
    state_update = """        
        # Update controller state if available
        if CONTROLLER and duplicates:
            try:
                CONTROLLER.state.update_duplicates_scan(path, duplicates)
                print(f"💾 Saved duplicates context to state manager")
            except Exception as e:
                print(f"⚠️  Failed to save state: {e}")
        """
    
    # Найти место в tool_find_duplicates после строки "duplicates = {k: v for k, v in files_by_size.items() if len(v) > 1}"
    pattern = r'(duplicates = \{k: v for k, v in files_by_size\.items\(\) if len\(v\) > 1\})\n'
    agent_code = re.sub(pattern, r'\1' + state_update + '\n', agent_code, count=1)
    
    # ============================================================
    # PATCH 5: Защита delete_files от несуществующих файлов
    # ============================================================
    delete_validation = """    # Validate all paths exist before deletion (GUARDRAIL)
    missing_paths = [p for p in paths if not os.path.exists(p)]
    if missing_paths:
        error_msg = f"❌ Не могу удалить несуществующие файлы:\\n"
        for p in missing_paths[:5]:  # show max 5
            error_msg += f"  - {p}\\n"
        if len(missing_paths) > 5:
            error_msg += f"  ... и ещё {len(missing_paths) - 5}\\n"
        error_msg += f"\\n💡 Подсказка: используй find_duplicates или list_files чтобы получить реальные пути."
        return error_msg
    
    """
    
    # Найти начало tool_delete_files
    pattern = r'(def tool_delete_files\(paths: list, permanent: bool = False\) -> str:\n    """.*?""")\n'
    replacement = r'\1\n' + delete_validation
    agent_code = re.sub(pattern, replacement, agent_code, flags=re.DOTALL, count=1)
    
    return agent_code


def verify_installation(agent_code: str) -> bool:
    """Проверить что все патчи применены"""
    checks = [
        ("Controller import", "from controller import create_controller"),
        ("Controller initialization", "CONTROLLER = None"),
        ("Controller handler", "controller_result = CONTROLLER.handle_request"),
        ("State update", "CONTROLLER.state.update_duplicates_scan"),
        ("Delete validation", "missing_paths = [p for p in paths if not os.path.exists(p)]"),
    ]
    
    results = []
    for name, pattern in checks:
        if pattern in agent_code:
            results.append((name, True))
            print(f"  ✅ {name}")
        else:
            results.append((name, False))
            print(f"  ❌ {name} — NOT FOUND")
    
    return all(r[1] for r in results)


def main():
    """Главная функция установщика"""
    print("=" * 60)
    print("Agent Controller Layer — Installer v1.0")
    print("=" * 60)
    print()
    
    # Проверить наличие файлов
    if not os.path.exists("agent_v3.py"):
        print("❌ ERROR: agent_v3.py not found in current directory")
        return
    
    if not os.path.exists("controller.py"):
        print("❌ ERROR: controller.py not found")
        print("   Download controller.py first!")
        return
    
    print("📂 Found files:")
    print("  ✅ agent_v3.py")
    print("  ✅ controller.py")
    print()
    
    # Создать резервную копию
    print("📦 Creating backup...")
    backup_path = backup_file("agent_v3.py")
    print(f"  ✅ Backup saved: {backup_path}")
    print()
    
    # Прочитать код
    print("📖 Reading agent_v3.py...")
    agent_code = read_file("agent_v3.py")
    print(f"  ✅ Loaded {len(agent_code)} characters")
    print()
    
    # Применить патч
    print("🔧 Applying patches...")
    patched_code = apply_patch(agent_code)
    print("  ✅ All patches applied")
    print()
    
    # Проверить
    print("🔍 Verifying installation...")
    if verify_installation(patched_code):
        print()
        print("✅ Verification PASSED")
        
        # Записать файл
        write_file("agent_v3.py", patched_code)
        print()
        print("💾 Updated agent_v3.py")
        print()
        print("=" * 60)
        print("🎉 INSTALLATION COMPLETE!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run: python agent_v3.py")
        print("  2. Try: 'найди дубликаты в Downloads и удали старые'")
        print("  3. Watch the controller handle it WITHOUT LLM!")
        print()
        
    else:
        print()
        print("❌ Verification FAILED")
        print("   Some patches were not applied correctly.")
        print("   Restoring from backup...")
        shutil.copy2(backup_path, "agent_v3.py")
        print("  ✅ Restored original file")


if __name__ == "__main__":
    main()
