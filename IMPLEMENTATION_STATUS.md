# IMPLEMENTATION_STATUS.md

Last updated: 2026-03-18

This document tracks what is **actually implemented and working** vs what is **scaffolded** vs what is **planned only**.

If it is not listed as "implemented" here, do not describe it as working in any doc or UI.

---

## 1. Provider Layer

### Implemented (production path)

- **Ollama local provider**: all LLM calls go through `OLLAMA_URL/api/chat`
- **Model selection**: default `qwen2.5-coder:14b`
- **Model override precedence**:
  1. Hardcoded default: `qwen2.5-coder:14b` (`backend/n8on.py:69`)
  2. Installer config: `%APPDATA%/Agent n8On/config.json` field `model` (`backend/n8on.py:73-81`)
  3. Environment variable: `OLLAMA_MODEL` (used by `brain/intent_classifier.py:209`)
  - Note: `n8on.py` reads installer config but does NOT read `OLLAMA_MODEL` env var for its own `MODEL` constant. `intent_classifier.py` reads both. This is an inconsistency.

### Scaffolded (code exists, not connected to production path)

- `backend/providers/base.py` — abstract LLMProvider + LLMResponse
- `backend/providers/local_ollama.py` — OllamaProvider wrapping Ollama API
- `backend/providers/api_provider.py` — APIProvider stub (raises NotImplementedError)
- `backend/providers/provider_manager.py` — ProviderManager with local/api/auto modes
- `backend/providers/network_status.py` — internet/Ollama availability detection

**Status**: The provider abstraction is ready to be wired in. The current production code (`ask_ollama()` in `n8on.py`) still calls Ollama directly. Migration to ProviderManager is a future step.

### Not yet implemented

- Actual API provider calls (Claude, OpenAI)
- Auto mode with fallback
- Per-task provider selection

---

## 2. Knowledge Layer

### Implemented (production path)

- `skills/instructions/*.md` — 4 instruction files loaded by keyword match in `brain_layer.py`
- `skills/n8n_blocks/*.json` — 9 node block templates
- `skills/n8n_templates/*.json` — 3 pre-built workflow templates
- `n8n_recipes.py` — 21K lines of node generation recipes
- `brain/learned_rules.md` — manually maintained lessons learned

### Scaffolded (code exists, not connected to production path)

- `backend/knowledge/knowledge_selector.py` — keyword-based retrieval from:
  - `knowledge/repair_memory/error_corrections.json` — empty, ready for entries
  - `knowledge/instruction_packs/*.md` — 3 initial packs (http_request, google_sheets, webhook)
  - `knowledge/templates/` — empty, ready for golden/user templates
  - `knowledge/docs_cache/` — empty, reserved for future cached n8n docs

**Status**: KnowledgeSelector is ready to be called from brain_layer.py before workflow generation. Not yet wired in.

### Not yet implemented

- Automatic repair memory population (from successful repairs)
- Auto-template generation (from confirmed workflows)
- RAG / vector search
- Online documentation augmentation

---

## 3. Offline-First Policy

### Implemented

- Ollama runs locally — works without internet
- `/api/status` now reports `internet` and `effective_mode` fields
- `NetworkStatus` class detects internet + Ollama availability

### Scaffolded

- `agent_config.py` supports `knowledge_mode: local_first | local_only`

### Not yet implemented

- Runtime enforcement: code does not yet block API calls when offline
- Honest degradation messaging to user when knowledge is limited
- Online augmentation path

---

## 4. Configuration

### Implemented (production path)

- `OLLAMA_URL` hardcoded + env var override
- `MODEL` hardcoded + installer config override
- `N8N_URL` hardcoded + env var override
- `WEB_PORT` hardcoded

### Scaffolded

- `backend/agent_config.py` — unified AgentConfig with load precedence:
  1. Hardcoded defaults
  2. `%APPDATA%/Agent n8On/config.json`
  3. Environment variables
- Supports new fields: `provider_mode`, `api_key`, `knowledge_mode`, `installed_by_agent`

**Status**: AgentConfig is loaded and used by `/api/status`. Not yet used by `ask_ollama()` or other production code paths.

---

## 5. Logging

### Implemented (production path)

- `print()` statements in brain components
- Chat history saved to `memory/chat_history.json`
- Intent cache in `memory/intent_cache.json`
- Session state in `memory/session_state.json`

### Scaffolded

- `backend/decision_logger.py` — JSON-lines logger for:
  - routing decisions (FAST/SLOW/CLARIFY)
  - provider selection
  - knowledge sources used
  - repair attempts
  - user confirmations
- Writes to `%APPDATA%/Agent n8On/decisions.jsonl` (or `backend/memory/decisions.jsonl`)

**Status**: DecisionLogger is ready to be called from brain_layer.py and n8on.py. Not yet wired in.

---

## 6. UI

### Implemented

- Status badge: shows Ollama connected/disconnected + model name
- Status badge now also shows: provider_mode (if not local), offline indicator
- Status endpoint returns: `provider_mode`, `knowledge_mode`, `internet`, `effective_mode`

### Not yet implemented

- Display of knowledge mode in UI
- Symptom collection form for user confirmation
- Plan approval UI for SLOW tasks

---

## 7. Brain Layer

### Implemented (production path)

- Router: FAST/SLOW/CLARIFY classification (regex + action verb counting)
- IntentClassifier: LLM-based semantic classification with 15+ intents
- Planner: converts intent to ordered PlanSteps
- Executor: runs steps with dependency handling
- Verifier: checks execution results
- ErrorInterpreter: maps errors to human-readable explanations
- BrainLayer: orchestrator with pending state machine for confirmations
- Skill discovery: keyword-based matching in `_SKILL_KEYWORDS`

### Not yet implemented

- Knowledge injection into LLM prompts (via KnowledgeSelector)
- Provider-aware routing (choose model by task complexity)
- Structured logging of brain decisions

---

## 8. Installer / Uninstaller

### Implemented

- Tauri-based installer: downloads Ollama, Node.js, n8n
- Writes `config.json` with user's model choice
- Runtime build in GitHub Releases

### Not yet implemented

- `installed_by_agent` flag in config.json
- Uninstaller cleanup dialog
- Conditional removal of Ollama/Node.js/n8n
- Cleanup of `%APPDATA%/Agent n8On/` and `%LOCALAPPDATA%/Agent n8On/`

---

## 9. Non-n8n Skills (broad assistant features)

### Present in code but secondary to n8n-first focus

These exist in `backend/skills/` and are loaded via `skills_enabled.json`:
- `auth_browse.py` — browser automation (Playwright)
- `google_drive.py`, `google_calendar.py` — Google integrations
- `telegram_bot.py` — Telegram messaging
- `excel_reports.py`, `pdf_analyzer.py` — document tools
- `voice_input.py` — audio input
- `kommun_parser.py`, `boostcamp_crm.py` — domain-specific parsers

**Policy**: These are kept as secondary tooling. Core product loop is n8n workflow generation/repair. These skills may be used as n8n workflow building blocks but are not the product's primary value.
