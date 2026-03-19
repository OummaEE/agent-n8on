# ROADMAP

## Purpose
This roadmap captures what still needs to be built next.

Unlike `IMPLEMENTATION_STATUS.md`, this file is about **future implementation priorities**, not current verified reality.

The main rule is simple:
**each phase should make the core loop more reliable, more accurate, or more usable on real user machines.**

Core loop:
request -> routing -> provider choice -> knowledge retrieval -> workflow generation -> validation -> execution -> repair -> user confirmation

---

## Phase 0 — Finish Windows installation validation
Goal: confirm the latest installer/runtime fixes on clean Windows.

Tasks:
- final clean Windows test after the latest rebuild,
- verify runtime download and unpack,
- verify n8n startup,
- verify backend can find Python correctly,
- verify first-run behavior,
- verify logs are usable when failure occurs.

Success condition:
- installer works end-to-end on clean Windows after the latest fixes.

---

## Phase 1 — Full lifecycle management (installer + uninstaller)
Goal: make install and uninstall honest and complete.

Tasks:
- add `installed_by_agent` metadata for managed dependencies,
- add uninstall prompt for optional removal of Ollama and models,
- stop Ollama before cleanup,
- remove agent-installed Node.js only if ownership metadata confirms it,
- uninstall agent-installed global `n8n`,
- always remove app-specific config/cache/log folders,
- show the user what will be removed and what space may be freed.

Success condition:
- install and uninstall lifecycle is reliable and does not leave unmanaged mess behind.

---

## Phase 2 — Provider layer (`local`, `api`, `auto`)
Goal: stop depending on a single local-only model path.

Tasks:
- add provider abstraction,
- support local-only mode,
- support API-only mode,
- support auto mode,
- choose provider based on online/offline state, task complexity, and local capability,
- expose provider status to the UI.

Why this matters:
- weak local machines may not generate workflows reliably,
- users need a fallback path,
- the product must be honest about what path is actually being used.

Success condition:
- the system can intentionally choose between local and API generation instead of being hard-wired to Ollama only.

---

## Phase 3 — Offline-first n8n knowledge layer
Goal: make the agent strong through n8n-specific knowledge, not only through raw model strength.

Tasks:
- create a local n8n knowledge folder,
- store node docs, patterns, schemas, examples, and recipes,
- make the system retrieve relevant n8n context before generation,
- prefer local knowledge first,
- support online augmentation when internet is available.

Why this matters:
- the product is n8n-first,
- weak local models need targeted help,
- offline users still need useful workflow generation support.

Success condition:
- the agent can retrieve relevant n8n knowledge even without internet.

---

## Phase 4 — Error-correction memory (“грабли”)
Goal: stop repeating the same repair mistakes.

Tasks:
- log recurring failure patterns,
- log which fixes actually worked,
- reuse known corrections before new blind repair attempts,
- store and retrieve repair patterns by error type.

Success condition:
- similar workflow failures are repaired faster using known successful fixes.

---

## Phase 5 — Minimal Golden Templates / BlockLibrary
Goal: stop regenerating the hardest n8n structures from scratch.

Tasks:
- choose a small set of high-value node patterns first,
- build trusted JSON templates for those patterns,
- reuse them in generation and repair,
- keep them versioned and inspectable.

Suggested first targets:
- HTTP Request,
- Wait / retry / backoff,
- Google Sheets append-or-update,
- binary-data handling,
- expression-heavy mappings.

Success condition:
- the system reduces avoidable structural errors by relying on trusted blocks.

---

## Phase 6 — Self-growing workflow library
Goal: turn successful workflows into reusable assets.

Tasks:
- export successful workflow JSON after real success,
- sanitize secrets,
- save reusable local workflow templates,
- search the local library before generating from scratch.

Success condition:
- repeated tasks get faster and more reliable because successful workflows are reused.

---

## Phase 7 — Online augmentation / optional RAG expansion
Goal: improve difficult or rare-node generation when local knowledge is not enough.

Tasks:
- optionally retrieve fresh online documentation,
- optionally add vector retrieval over local knowledge if simpler retrieval is insufficient,
- keep this optional and modular.

Important constraint:
- do not make the base product depend entirely on this,
- offline-first behavior must remain valid.

Success condition:
- rare or complex tasks improve when internet is available, without making offline users helpless.

---

## Phase 8 — Skills / knowledge packs refinement
Goal: convert the most useful external knowledge into n8n-relevant local instruction packs.

Tasks:
- identify the most valuable skills/packs for n8n workflows,
- normalize them into local instruction or template packs,
- avoid dumping everything into the core agent,
- keep the system inspectable and focused.

Success condition:
- the product gains narrow, high-value expertise without feature sprawl.

---

## Phase 9 — Formal plugin architecture (later)
Goal: support cleaner extensibility only after the core is strong.

Tasks:
- formalize plugin loading rules,
- define safe interfaces,
- keep plugins versioned and optional,
- avoid turning the core into a marketplace too early.

Success condition:
- plugins exist as a clean extension mechanism, not as chaos.

---

## Prioritization rule
Do **not** build later phases just because they sound smart.
A later phase should only move up if it clearly improves:
- workflow quality,
- repair quality,
- offline usability,
- weak-machine usability,
- installation reliability.

---

## Things deliberately not treated as done
This roadmap assumes the following are **not yet complete** until verified:
- final Windows installer stability after the latest fixes,
- hybrid provider selection,
- local n8n docs retrieval,
- strong offline knowledge mode,
- mature self-growing workflow library,
- mature plugin system.
