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

Most users do not want to learn:

- npm,
- local services,
- environment variables,
- n8n workflow JSON,
- execution logs,
- node configuration,
- repair loops.

They want the automation to work.

That is the point of agent-n8On.

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

This matters because not every request should go straight into workflow generation or heavy LLM handling.

### 3. If needed, the agent creates or updates an n8n workflow
The system produces workflow JSON aligned with the requested task.

### 4. Agent validates the workflow
The system checks structural correctness before running.

### 5. Agent runs the workflow
The system triggers a test execution and inspects n8n output.

### 6. Agent repairs the workflow if needed
If there is an execution error or output mismatch, the agent updates the workflow and tries again.

### 7. Agent asks the user to verify
When automated checks pass, the agent asks the user whether everything works in real usage.

### 8. Agent continues debugging if the user reports a problem
If the user says the result is still wrong, the agent gathers concrete symptoms and re-enters the repair loop.

---

## Brain-first processing model
The front-door control flow is part of the product, not an implementation detail.

### CLARIFY
Used when the request is missing critical information or is too ambiguous to execute safely.

### FAST
Used when the request is clear, narrow, and can be handled directly without heavyweight planning.

### SLOW
Used when the request is complex and requires explicit planning, execution, verification, and often repair.

The dedicated routing and planning logic is documented in [`BRAIN_ARCHITECTURE.md`](./BRAIN_ARCHITECTURE.md).

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

---

## Current repository direction
This repository contains the evolving implementation of agent-n8On as an n8n-first desktop system.

The long-term architecture centers on:

- Brain-based request routing,
- local runtime orchestration,
- n8n workflow creation and update,
- execution inspection,
- repair loops,
- installer reliability,
- user confirmation flow,
- logs and diagnostics,
- learned operational rules.

Some historical parts of the repo reflect a broader local AI assistant direction. The current product direction is narrower and stricter: **n8n-first, repair-focused, user-confirmed automation**.

---

## Documentation map
Start here if you want the real product definition, not just scattered code behavior:

- [`PROJECT_IDEA.md`](./PROJECT_IDEA.md) — what the product is and why it exists
- [`SPECIFICATION.md`](./SPECIFICATION.md) — behavior rules and success criteria
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — system layers, responsibilities, and flow
- [`BRAIN_ARCHITECTURE.md`](./BRAIN_ARCHITECTURE.md) — routing, planning, execution, verification, learned rules
- [`INSTALLER_SPEC.md`](./INSTALLER_SPEC.md) — installer behavior and failure handling
- [`CLAUDE.md`](./CLAUDE.md) — AI-assisted development rules for this repo

If these documents conflict with older code comments or older README assumptions, the docs win.

---

## Product principles
1. **n8n-first, not feature-chaos**
2. **installer reliability is part of the product**
3. **a workflow that runs but does the wrong thing is not a success**
4. **Brain routing is part of correctness, not just convenience**
5. **user confirmation is mandatory before completion**
6. **honesty about failure is better than fake success**

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
- logs and diagnostics.

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

---

## Status
This project is actively evolving.
The product direction is now explicitly centered on:

- **one-click setup**
- **Brain-based request routing**
- **self-healing n8n workflows**
- **user-confirmed completion**

That is the standard the repository should be moving toward.
