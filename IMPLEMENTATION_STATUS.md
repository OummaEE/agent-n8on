# IMPLEMENTATION_STATUS.md

Last updated: 2026-03-19

This document tracks what is **actually implemented and working** vs what is **scaffolded** vs what is **planned only**.

If it is not listed as "implemented" here, do not describe it as working in any doc or UI.

---

## 1. Provider Layer

### Active in production path

- **ProviderManager** initialised at startup in `n8on.py` from `AgentConfig`
- **`ask_ollama()`** routes through `ProviderManager.chat()` when available
  - Falls back to direct `requests.post()` if ProviderManager init failed
  - Logs provider choice via `DecisionLogger`
- **IntentClassifier** accepts optional `provider` param; when set, LLM calls go through it
- **SmartErrorInterpreter** accepts optional `provider` param; same behavior
- **BrainLayer** passes `_provider_mgr._local` (OllamaProvider) to classifier/interpreter

### Partially wired

- **OllamaProvider** (`providers/local_ollama.py`) — used as the active local provider
- **APIProvider** (`providers/api_provider.py`) — stub, raises `NotImplementedError`
- **Auto mode** — ProviderManager supports it; will try local then fall back to API

### Model override precedence (as implemented)

1. Hardcoded default: `qwen2.5-coder:14b`
2. `%APPDATA%/Agent n8On/config.json` → `model` field (installer-written)
3. Environment variable: `OLLAMA_MODEL`
4. `AgentConfig.load()` merges all three in that order

### Not yet implemented

- Actual API provider calls (Claude, OpenAI)
- Per-task provider selection (e.g. use stronger model for complex tasks)

---

## 2. Knowledge Layer

### Active in production path

- `skills/instructions/*.md` — 4 instruction files loaded by keyword match in `brain_layer.py`
- `skills/n8n_blocks/*.json` — 9 node block templates
- `skills/n8n_templates/*.json` — 3 pre-built workflow templates
- `n8n_recipes.py` — 21K lines of node generation recipes
- `brain/learned_rules.md` — manually maintained lessons learned

### Partially wired

- **`KnowledgeSelector`** is instantiated in `BrainLayer.__init__()` and called in `_slow_path()`
  - Retrieves `repair_hints`, `instruction_fragments`, `template_matches` before plan execution
  - Logs which knowledge sources were used via `DecisionLogger`
  - Retrieved context is not yet injected into LLM prompts (retrieval works, injection is next step)
- **Instruction packs** — 3 initial packs (http_request, google_sheets, webhook) in `knowledge/instruction_packs/`
- **Repair memory** — `knowledge/repair_memory/error_corrections.json` (empty, ready for entries)

### Not yet implemented

- Knowledge context injection into LLM system prompts
- Automatic repair memory population (from successful repairs)
- Auto-template generation (from confirmed workflows)
- RAG / vector search
- Online documentation augmentation

---

## 3. Offline-First Policy

### Active in production path

- Ollama runs locally — works without internet
- `/api/status` reports `internet` and `effective_mode` fields (refreshed each status check)
- `NetworkStatus` class detects internet + Ollama availability
- `ProviderManager` respects mode: `local` never attempts API; `auto` tries local first
- If `provider_mode=api` and API is not implemented, returns explicit error (not silent failure)

### Partially wired

- `agent_config.py` supports `knowledge_mode: local_first | local_only`
- `KnowledgeSelector` only searches local files (no online augmentation path exists yet)

### Not yet implemented

- Honest degradation messaging to user when knowledge is limited
- Online documentation fetch when internet is available

---

## 4. Configuration

### Active in production path

- **`AgentConfig`** loaded at startup in `n8on.py`, used to initialise:
  - `ProviderManager` (ollama_url, model, provider_mode, api_key)
  - `NetworkStatus` (ollama_url)
  - `/api/status` response (provider_mode, knowledge_mode)
- Load precedence: hardcoded defaults → installer config.json → env vars
- Legacy `OLLAMA_URL` / `MODEL` globals still exist and are used by direct Ollama calls

### Not yet implemented

- Config hot-reload (requires restart)
- UI settings page
- Config validation warnings

---

## 5. Structured Decision Logging

**Status: fully active in production path**

**Log location:**
- Windows: `%APPDATA%/Agent n8On/decisions.jsonl`
- Other / fallback: `backend/memory/decisions.jsonl`

**Format:** JSON lines (one JSON object per line, with `"event"` and `"ts"` fields).

### Event types and wiring status

| # | Event | Status | Wired at | Fields logged |
|---|-------|--------|----------|---------------|
| 1 | `routing` | **fully active** | `brain_layer.py` `handle()` | route (FAST/SLOW/CLARIFY), message preview, reason (multi-step connector, action verb count, too vague, default) |
| 2 | `provider` | **fully active** | `n8on.py` `ask_ollama()` | provider (ollama/api), mode (local/api/auto/legacy), fallback used, internet state, ollama state, reason |
| 3 | `knowledge` | **fully active** | `brain_layer.py` `_slow_path()` | sources checked, sources used, augmentation mode (local_only), fragments count, reason (which packs matched, why) |
| 4 | `execution` | **fully active** | `executor.py` `_run_n8n_workflow_step()`, `_run_n8n_debug_step()` | workflow_id, workflow_name, execution_id, step_intent, success, error, failing_node |
| 5 | `repair` | **fully active** | `brain_layer.py` `_handle_step_failure()` | attempt number, workflow_id, execution_id, error, failing_node, fix_description, what_changed, success |
| 6 | `confirmation` | **fully active** | `brain_layer.py` `_request_plan_confirmation()`, `_handle_plan_confirmation()`, `_handle_solution_choice()` | state (asked/confirmed/cancelled/modified/rejected), user_response, problem_description, workflow_id, execution_id |

### Security

- **Never logs**: secrets, tokens, passwords, credential values, API keys
- Message previews truncated to 120 chars
- Error messages truncated to 300 chars
- Credential extraction in `_handle_solution_choice()` is NOT logged

### Legacy logging (still present)

- `print()` statements in brain components
- Chat history saved to `memory/chat_history.json`
- Intent cache in `memory/intent_cache.json`
- Session state in `memory/session_state.json`

### Not yet implemented

- Log rotation / size limits
- Log viewer in UI
- Log export / analysis tools

---

## 6. UI

### Active in production path

- Status badge: shows Ollama connected/disconnected + model name
- Status badge shows provider_mode (if not local) and offline indicator
- Status endpoint returns: `provider_mode`, `knowledge_mode`, `internet`, `effective_mode`

### Not yet implemented

- Display of knowledge mode in UI
- Symptom collection form for user confirmation
- Plan approval UI for SLOW tasks

---

## 7. Brain Layer

### Active in production path

- Router: FAST/SLOW/CLARIFY classification (regex + action verb counting)
- Router.route_with_reason(): returns (path, reason) for structured logging
- IntentClassifier: LLM-based semantic classification with 15+ intents
  - Now routes through ProviderManager (OllamaProvider) when available
- Planner: converts intent to ordered PlanSteps (no LLM)
- Executor: runs steps with dependency handling (no LLM)
- Verifier: checks execution results (no LLM)
- ErrorInterpreter: rule-based error mapping (no LLM)
- SmartErrorInterpreter: LLM-based error analysis
  - Now routes through ProviderManager when available
- BrainLayer: orchestrator with pending state machine for confirmations
- Skill discovery: keyword-based matching in `_SKILL_KEYWORDS`
- Knowledge retrieval: KnowledgeSelector called in `_slow_path()` (retrieval active, injection pending)
- Decision logging: routing, knowledge, execution, repair, and confirmation events logged

### Not yet implemented

- Knowledge context injection into LLM prompts
- Provider-aware routing (choose model by task complexity)

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

**Installer rebuild required?** No — the new code is backward compatible. If `ProviderManager` fails to init, `ask_ollama()` falls back to the legacy direct Ollama call. No new config fields are required by the installer.

---

## 9. Integration Points Summary

| Call Site | File | Logging Event |
|-----------|------|---------------|
| `ask_ollama()` | `n8on.py` | `provider` — mode, provider, fallback, internet, ollama, reason |
| `BrainLayer.handle()` | `brain_layer.py` | `routing` — route, reason (from Router.route_with_reason) |
| `BrainLayer._slow_path()` | `brain_layer.py` | `knowledge` — sources checked/used, augmentation, fragments, reason |
| `Executor._run_n8n_workflow_step()` | `executor.py` | `execution` — workflow_id, name, execution_id, success, error, failing_node |
| `Executor._run_n8n_debug_step()` | `executor.py` | `execution` — workflow_id, name, execution_id, success, error |
| `BrainLayer._handle_step_failure()` | `brain_layer.py` | `repair` — attempt, workflow_id, execution_id, error, failing_node, fix, what_changed |
| `BrainLayer._request_plan_confirmation()` | `brain_layer.py` | `confirmation` — state=asked |
| `BrainLayer._handle_plan_confirmation()` | `brain_layer.py` | `confirmation` — state=confirmed/cancelled/modified |
| `BrainLayer._handle_solution_choice()` | `brain_layer.py` | `confirmation` — state=confirmed/cancelled |
| `IntentClassifier._classify_with_llm()` | `intent_classifier.py` | (routed through ProviderManager, logged at ask_ollama level) |
| `SmartErrorInterpreter.interpret()` | `intent_classifier.py` | (routed through ProviderManager, logged at ask_ollama level) |

---

## 10. Non-n8n Skills (broad assistant features)

### Present in code but secondary to n8n-first focus

These exist in `backend/skills/` and are loaded via `skills_enabled.json`:
- `auth_browse.py` — browser automation (Playwright)
- `google_drive.py`, `google_calendar.py` — Google integrations
- `telegram_bot.py` — Telegram messaging
- `excel_reports.py`, `pdf_analyzer.py` — document tools
- `voice_input.py` — audio input
- `kommun_parser.py`, `boostcamp_crm.py` — domain-specific parsers

**Policy**: These are kept as secondary tooling. Core product loop is n8n workflow generation/repair. These skills may be used as n8n workflow building blocks but are not the product's primary value.
