# IMPLEMENTATION_STATUS

## Purpose
This document describes **what is actually implemented and verified now**.

It exists to prevent confusion between:
- current implementation reality,
- target architecture,
- future roadmap.

For target behavior, see [`SPECIFICATION.md`](./SPECIFICATION.md).
For future work, see [`ROADMAP.md`](./ROADMAP.md).

---

## Current state summary
agent-n8On already has a meaningful local n8n-oriented foundation, but the full target architecture is **not yet implemented**.

The project is currently in a state where:
- core local agent behavior exists,
- Brain routing exists,
- local Ollama integration exists,
- n8n API integration exists,
- final Windows installer validation is still pending after the latest fixes,
- provider-aware hybrid (`local + api + auto`) mode is **not yet implemented**,
- dedicated local n8n documentation retrieval is **not yet implemented**.

---

## What is implemented in the current codebase
### 1. Local Ollama model path
The current code uses Ollama as the active model path.

Observed in code:
- `OLLAMA_URL = "http://localhost:11434"`
- `MODEL = "qwen2.5-coder:14b"`
- chat and workflow generation requests are sent to Ollama locally.

Implication:
- local mode exists,
- API fallback / provider switching is not yet visible in production code.

### 2. Brain / routing layer exists
The current code shows Brain-first routing support.

Observed in code/comments:
- `BRAIN = None  # BrainLayer wrapping CONTROLLER (SLOW/FAST/CLARIFY routing)`
- optional initialization of `BrainLayer`
- request handling attempts Brain/Controller first before falling back to the older loop.

Implication:
- Brain-based request routing exists conceptually and in code integration,
- this is not just documentation fantasy.

### 3. n8n integration exists
The current code already supports substantial n8n operations.

Observed capabilities:
- list workflows,
- get workflow,
- get executions,
- get execution,
- run workflow,
- update workflow,
- validate workflow,
- create workflow,
- activate workflow,
- delete workflow.

Implication:
- the product already has real n8n API control, not just plans.

### 4. Local skills loading exists
The current code loads local skills from the `skills/` directory.

Observed behavior:
- `load_skills()`
- merge skill tools into main `TOOLS`
- describe skills dynamically.

Implication:
- there is already a local extensibility mechanism,
- but this is not yet the same thing as a formal plugin architecture.

### 5. Local memory / logs exist
The current code already stores:
- chat history,
- user profile,
- tasks,
- logs.

Implication:
- some persistence exists,
- but advanced repair-memory / n8n-specific error memory is still a future extension.

---

## What was completed most recently on Windows/installer side
### CI / build / runtime work completed
1. Analyzed the self-hosted runner advice and decided to try `windows-2022` first.
2. Created a GitHub Actions workflow with:
   - diagnostics,
   - retry logic,
   - Defender exclusions.
3. Completed expert review and fixed 4 bugs:
   - exit code after retry,
   - hard fail,
   - broken output,
   - upload paths.
4. Ran 6 CI iterations and fixed specific issues one by one:
   - removed deprecated `npm config msvs_version`,
   - added `setuptools` for `No module 'distutils'`,
   - moved to Node 22 for `v8::SourceLocation not found`,
   - upgraded from Node 22.14 to 22.16,
   - added portable Node and `manifest.json` to fix zip/runtime packaging.
5. Runtime build succeeded and was uploaded to GitHub Releases.
6. Rebuilt installer and tested on Azure VM:
   - runtime downloaded,
   - runtime unpacked,
   - n8n started.
7. Fixed Windows `\\?\` path bug where backend could not find the Python script.
8. Final installer rebuild is ready for another test cycle.

---

## Important reality check
### Not yet confirmed
After the latest fixes, a fresh final Windows test has **not yet been completed**.

That means the following must still be treated as **not fully verified in practice**:
- complete install success on clean Windows after latest fixes,
- complete runtime startup stability after latest packaging changes,
- end-to-end workflow creation and repair success in the final rebuilt installer,
- uninstall behavior.

---

## What is NOT yet implemented or not yet visible in production code
### 1. Provider-aware hybrid mode
Not yet visible in the current codebase:
- `local + api + auto` provider selection,
- remote/API fallback for weak local machines,
- automatic provider choice based on online/offline state and task complexity.

Current reality:
- local Ollama path exists,
- hybrid/provider layer does not yet appear to be implemented.

### 2. Dedicated n8n documentation retrieval layer
Not yet visible in the current codebase:
- local n8n docs index,
- n8n-specific RAG,
- targeted retrieval over node documentation, schemas, and examples,
- offline-first documentation cache for n8n.

Current reality:
- agent can talk to n8n as a system,
- but does not yet appear to have a dedicated n8n knowledge retrieval layer.

### 3. Explicit offline-first knowledge mode
Not yet visible as a dedicated feature:
- graceful knowledge mode selection when internet is absent,
- clear distinction between local-only knowledge and online augmentation,
- explicit user-facing explanation of online/offline limitations.

### 4. Self-growing workflow library
Not yet confirmed implemented:
- export successful workflows into a reusable local library,
- sanitize secrets before saving templates,
- reuse successful workflows before generating from scratch.

### 5. Error-correction memory (“грабли”)
Not yet confirmed implemented as a dedicated system:
- persistent mapping of error patterns to successful fixes,
- first-class reuse of past corrections before new repair attempts.

### 6. Golden templates / BlockLibrary for n8n
Not yet confirmed implemented as a curated trusted layer:
- reusable JSON blocks for the hardest n8n nodes,
- systematic reuse in workflow generation.

### 7. Full uninstall lifecycle cleanup
Not yet confirmed end-to-end:
- `installed_by_agent` ownership metadata,
- optional removal of Ollama and models,
- optional removal of agent-installed Node.js,
- optional uninstall of agent-installed global `n8n`.

---

## Current online/offline behavior
### What should work offline now
If all local components are already installed and running, the current architecture should still be able to do some work offline:
- local Ollama chat/generation,
- local n8n API operations,
- local files/system operations,
- local skills.

### What is still weak or missing offline
Without internet and without a dedicated local n8n knowledge cache:
- the agent cannot rely on fresh online documentation,
- weak local models may struggle on complex workflow generation,
- there is no visible dedicated n8n offline docs retrieval layer yet.

---

## Immediate next reality-based priorities
- [ ] Re-run final Windows installer test after the latest fixes
- [ ] Validate end-to-end install and runtime behavior on clean Windows
- [ ] Validate workflow creation and repair after install
- [ ] Add explicit provider layer (`local`, `api`, `auto`)
- [ ] Add local n8n knowledge source(s) for offline-first retrieval
- [ ] Add implementation-safe split between target docs and current verified reality

---

## Documentation rule
When documenting agent-n8On:
- do not present planned architecture as already complete,
- do not present target-state features as production-ready unless they have been verified,
- keep implementation status explicit.

This file should be updated whenever a planned feature becomes verified reality.
