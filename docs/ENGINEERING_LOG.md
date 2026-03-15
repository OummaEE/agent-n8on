# ENGINEERING LOG

## 2026-02-12
### Safe-delete hardening
- Implemented safe delete: delete_files moves to _trash (reversible).
- Added permanent delete guard: requires permanent=true AND confirm=true.
- Added clean_duplicates routing through safe delete.
- Synced same patch to agent_v3_backup_*.py files.
- Added/updated tests: test_delete_safety.py (passed).

### Controller safety improvements
- Inject allowed_folder into delete operations (controller + direct LLM path).
- Fixed Windows path normalization to avoid false blocks.
- Known issue: test_controller.py has encoding/locale output issues in console.

