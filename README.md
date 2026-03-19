# agent-n8On

**agent-n8On** is an **n8n-first desktop app** for people who want automations without wrestling with setup, workflow JSON, and endless manual debugging.

It is built around two core promises:

1. **One-click local setup** — the app installs and configures the environment needed to work with local n8n as much as possible automatically.
2. **Self-healing workflows** — the app generates n8n workflows from plain-language requests, tests them, and keeps repairing them until they work.

This is not just a workflow generator.
It is a workflow **generation + testing + repair + user confirmation** system.

---

## What problem it solves
n8n is powerful, but for most normal users it has two ugly barriers:

- **setup pain** — installing and configuring the environment is annoying and fragile,
- **debugging pain** — generating a workflow is easy compared to making it actually work.

A third practical problem also matters:

- **hardware limits** — weaker PCs may run local models, but not well enough to generate complex workflows reliably.

That is why agent-n8On must become strong not only through the model, but through **routing, templates, memory, and targeted n8n knowledge retrieval**.

---

## Who it is for
Primary users:

- non-technical users,
- solo founders,
- creators,
- operators,
- small teams,
- people who need automation but do not want to become n8n engineers.

Secondary users:

- semi-technical users who want to move faster by delegating workflow generation and repair.

---

## What makes it different
agent-n8On is **not** positioned as:

- a generic AI chat app,
- a broad local assistant for everything,
- a simple wrapper around templates,
- a “generate JSON and good luck” tool.

It is specifically focused on this loop:

**plain-language request -> Brain routing -> n8n workflow path -> validation -> execution -> repair -> user confirmation**

That loop is the product.

---

## Definition of success
A workflow is **not** considered successful just because it exists, saves, activates, or runs once.

A workflow is considered correct only when **all** of these are true:

1. **n8n returns no execution errors**
2. **the observed test result matches the result requested by the user**
3. **the user confirms that it works on their side**

If the technical checks pass but the user says it still does not work, the task is **not done**.
The agent must collect what the user sees or receives and continue debugging.

---

## Core product behavior
### 1. User describes the automation
The user explains in plain language what they want to happen.

### 2. Brain decides how to process the request
Before the system commits to workflow work, the Brain routes the request.

```text
User
  -> Brain (Router)
       ├── CLARIFY -> ask clarifying question
       ├── FAST    -> Controller -> direct action / direct n8n path
       └── SLOW    -> Planner
                     -> plan steps
                     -> optional plan confirmation
                     -> Executor
                     -> Verifier
                     -> learned rules saved
```

### 3. Model/provider layer decides how generation should run
The product target is to support:

- `local` — local LLM only,
- `api` — remote/API model only,
- `auto` — choose the safest available path.

This matters because weak machines may need targeted help instead of relying on raw local model strength.

### 4. Knowledge layer supplies n8n-specific context
The product target is to use:

- local templates,
- local repair memory,
- local/offline n8n knowledge,
- and, when available, online documentation augmentation.

### 5. If needed, the agent creates or updates an n8n workflow
The system produces workflow JSON aligned with the requested task.

### 6. Agent validates the workflow
The system checks structural correctness before running.

### 7. Agent runs the workflow
The system triggers a test execution and inspects n8n output.

### 8. Agent repairs the workflow if needed
If there is an execution error or output mismatch, the agent updates the workflow and tries again.

### 9. Agent asks the user to verify
When automated checks pass, the agent asks the user whether everything works in real usage.

### 10. Agent continues debugging if the user reports a problem
If the user says the result is still wrong, the agent gathers concrete symptoms and re-enters the repair loop.

---

## Current status vs target architecture
### Already present in the repo
- local Ollama-based model path,
- Brain-based request routing,
- n8n workflow CRUD / run / execution inspection,
- validation and repair-oriented product logic,
- local skills loading.

### Not yet fully implemented
- proper `local + API + auto` provider selection,
- dedicated local n8n documentation retrieval,
- explicit offline-first knowledge mode,
- online documentation augmentation layer,
- final verified post-fix Windows install cycle.

Read these files for the split between reality and plan:

- [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md)
- [`ROADMAP.md`](./ROADMAP.md)

---

## Main product promises
### One-click local setup
The product should absorb setup complexity instead of dumping it on the user.

That includes, as much as possible:

- dependency detection,
- dependency installation,
- runtime configuration,
- verification,
- useful install logs.

### Self-healing workflow generation
The product does not stop at producing workflow JSON.
It must:

- validate,
- execute,
- inspect errors,
- inspect outputs,
- repair,
- retry,
- confirm with the user.

### n8n-specific knowledge assistance
The product target is not “generic smartness.”
It must become strong through:

- n8n-specific templates,
- n8n-specific repair memory,
- targeted documentation retrieval,
- offline-first fallback when internet is unavailable.

---

## Documentation map
Start here if you want the real product definition, not just scattered code behavior:

- [`PROJECT_IDEA.md`](./PROJECT_IDEA.md) — what the product is and why it exists
- [`SPECIFICATION.md`](./SPECIFICATION.md) — target behavior rules and success criteria
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — system layers, responsibilities, and flow
- [`BRAIN_ARCHITECTURE.md`](./BRAIN_ARCHITECTURE.md) — routing, planning, execution, verification, learned rules
- [`INSTALLER_SPEC.md`](./INSTALLER_SPEC.md) — installer behavior and failure handling
- [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md) — what is actually implemented and verified now
- [`ROADMAP.md`](./ROADMAP.md) — what still needs to be built next
- [`CLAUDE.md`](./CLAUDE.md) — AI-assisted development rules for this repo

If these documents conflict with older code comments or older README assumptions, the docs win.

---

## Product principles
1. **n8n-first, not feature-chaos**
2. **installer reliability is part of the product**
3. **a workflow that runs but does the wrong thing is not a success**
4. **Brain routing is part of correctness, not just convenience**
5. **offline behavior must be explicit, not accidental**
6. **user confirmation is mandatory before completion**
7. **honesty about failure is better than fake success**

---

## Scope boundaries
### In scope
- local setup and runtime preparation,
- Brain-based request routing,
- n8n workflow generation,
- validation,
- execution inspection,
- iterative repair,
- user confirmation,
- learned rules,
- logs and diagnostics,
- n8n-specific knowledge retrieval.

### Out of scope for the core product
- pretending to be a generic assistant for every possible task,
- declaring success because JSON exists,
- declaring success because a single execution did not crash,
- hiding failure states behind vague messaging.

---

## Quality bar
A good version of this product should feel like this:

- easy to install,
- clear about what is happening,
- persistent in debugging,
- strict about what “working” means,
- grounded in what the user actually experiences.

If the app generates workflows but still leaves the user to manually untangle them, it has failed its main job.
If the app routes requests badly before execution starts, it will generate avoidable failures downstream.
If the app depends on internet or model strength without stating it clearly, it will confuse users.

---

## Status
This project is actively evolving.
The product direction is now explicitly centered on:

- **one-click setup**
- **Brain-based request routing**
- **self-healing n8n workflows**
- **provider-aware generation (local / API / auto)**
- **offline-first n8n knowledge support**
- **user-confirmed completion**

That is the standard the repository should be moving toward.
