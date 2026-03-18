# ARCHITECTURE

## Purpose
This document describes the intended architecture of agent-n8On as an n8n-first desktop product.

The architecture should prioritize clarity, debuggability, and repairability over feature sprawl.

---

## 1. Architectural principle
The system is not just a chat app.
It is a layered workflow engineering system with a user interface on top.

The core architectural goal is:

- accept user intent,
- turn that intent into an n8n workflow,
- test the workflow,
- repair the workflow,
- confirm success with the user.

---

## 2. High-level layers
### Layer A — Desktop app / shell
Responsible for:
- packaging the application,
- launching the local services and UI,
- installer integration,
- local environment orchestration.

Examples:
- Tauri shell,
- local process management,
- install and startup flow.

### Layer B — UI layer
Responsible for:
- receiving user requests,
- showing progress,
- showing workflow/test/debug state,
- asking the user for confirmation,
- collecting user-reported failure details.

### Layer C — Agent orchestration layer
Responsible for:
- understanding the request,
- deciding whether to create, update, test, or repair,
- managing the iterative workflow loop,
- deciding when success criteria are met,
- deciding when to ask the user for confirmation.

This is the product brain.

### Layer D — n8n integration layer
Responsible for:
- creating workflows,
- updating workflows,
- activating workflows,
- running workflows,
- reading execution results,
- retrieving errors and outputs,
- validating payload compatibility with n8n.

### Layer E — Validation and repair layer
Responsible for:
- checking structural validity,
- checking execution outcome,
- comparing observed output to requested output,
- identifying likely repair points,
- feeding revised workflow definitions back into n8n.

### Layer F — Environment/runtime layer
Responsible for:
- local runtime dependencies,
- Ollama/local model availability,
- Node.js/npm availability,
- n8n availability,
- filesystem/log directories,
- local credentials/config loading.

### Layer G — Persistence/logging layer
Responsible for:
- request logs,
- workflow versions,
- execution IDs,
- repair attempts,
- user confirmation state,
- persistent memory/config state.

---

## 3. Core system flow
### Primary flow
1. User enters request.
2. UI sends request to orchestration layer.
3. Orchestration layer builds a plan.
4. n8n integration layer creates or updates workflow.
5. Validation layer checks structure.
6. n8n integration layer runs test execution.
7. Validation/repair layer inspects outputs and errors.
8. If failure exists, orchestration layer triggers repair.
9. If technical and functional checks pass, UI asks user to confirm.
10. If user reports failure, orchestration resumes repair loop.

---

## 4. Component responsibilities
### 4.1 Installer component
Responsibilities:
- detect environment,
- install missing runtime pieces,
- verify installation success,
- report failures clearly,
- write installer logs.

Must not:
- silently fail,
- claim success without verification.

### 4.2 Intent interpretation component
Responsibilities:
- identify what the user wants,
- extract trigger/input/output expectations,
- identify missing required details,
- normalize request into a workflow task definition.

Must not:
- invent critical missing details without grounds.

### 4.3 Workflow generation component
Responsibilities:
- create a valid initial workflow draft,
- keep structure readable,
- prefer minimal viable workflow.

Must not:
- optimize for complexity over clarity,
- generate untestable junk.

### 4.4 Workflow validation component
Responsibilities:
- confirm the workflow is structurally acceptable,
- block execution if validation fails.

Must not:
- let obviously invalid workflow payloads proceed.

### 4.5 Execution analysis component
Responsibilities:
- inspect n8n run result,
- detect execution errors,
- detect output mismatches,
- collect useful diagnostics.

### 4.6 Repair component
Responsibilities:
- modify workflow to address detected issues,
- preserve successful parts where possible,
- rerun the loop after each fix.

Must not:
- declare success after a blind edit,
- overwrite working parts carelessly when a localized fix is possible.

### 4.7 User confirmation component
Responsibilities:
- ask the user to verify after automated checks pass,
- collect what the user actually sees if there is still a problem.

Must not:
- treat technical success as final success.

---

## 5. Data contracts
### 5.1 Task definition contract
The orchestration layer should internally normalize user requests into a task definition that includes:

- user goal,
- trigger,
- input source,
- output target,
- expected result,
- missing dependencies,
- testable success signal.

### 5.2 Workflow contract
A workflow object must contain at minimum:
- name,
- nodes,
- connections,
- optional supported settings.

The payload must exclude fields that n8n rejects.

### 5.3 Execution analysis contract
Execution analysis should output at minimum:
- execution status,
- error presence/absence,
- key error message if any,
- observed result summary,
- comparison against expected result,
- next recommended action.

### 5.4 User confirmation contract
The confirmation state should capture:
- asked_for_confirmation: yes/no,
- user_confirmed_success: yes/no,
- user_reported_problem: yes/no,
- reported_symptoms: text.

---

## 6. Source-of-truth rules
### Product truth
The documentation files define what the product is supposed to do.

### Runtime truth
The actual execution state in n8n and local runtime defines what happened.

### User truth
If the user says the result is still wrong, the system must treat that as a real failure signal even if internal tests passed.

---

## 7. Architecture constraints
1. n8n-first focus must remain explicit.
2. Installer reliability is part of the architecture.
3. Repair loop logic is core architecture, not an add-on.
4. User confirmation is part of the control flow.
5. Logging must support post-failure diagnosis.

---

## 8. Failure-aware design rules
The system must assume that failure can occur at every layer:

- installer failure,
- dependency failure,
- workflow schema failure,
- execution failure,
- integration failure,
- logic mismatch,
- user-side mismatch.

Architecture should therefore prefer:
- explicit state,
- observable logs,
- narrow module responsibilities,
- resumable debugging flow.

---

## 9. Recommended repository-level document map
- `PROJECT_IDEA.md` — what the product is and why it exists
- `SPECIFICATION.md` — how the product must behave
- `ARCHITECTURE.md` — system layers and responsibilities
- `INSTALLER_SPEC.md` — install behavior and failure handling
- `CLAUDE.md` — AI coding rules and repo working constraints

---

## 10. Core architectural truth
The product is successful only if it closes this loop:

user intent -> workflow generation -> validation -> execution -> repair -> user confirmation

If any one of these parts is weak, the whole product becomes unreliable.