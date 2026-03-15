# PROJECT MEMORY — Jane AI Agent

## What this is
Local AI assistant on Windows using Ollama + tools + Controller Layer.

## Key guarantees (current)
- Safe delete: moves to _trash (reversible), permanent delete requires explicit confirmation.
- Folder scoping: delete operations must be inside requested_folder or last_scanned_folder.
- Duplicate cleanup: should use clean_duplicates (keep newest, move older to trash).
- Path normalization: Windows path casing and separators normalized.

## Architecture (high-level)
- agent_v3.py: main runtime, tools router, UI/Telegram integration.
- controller.py: deterministic handling for supported intents (duplicates, file ops, etc.)
- tests: test_delete_safety.py (+ others)

## Run
- python agent_v3.py
- python test_delete_safety.py

