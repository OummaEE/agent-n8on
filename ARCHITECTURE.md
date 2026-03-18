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
- decide how the request should be handled,
- turn that intent into an n8n workflow when needed,
- test the workflow,
- repair the workflow,
- confirm success with the user.

A critical rule: **not every request should go straight into workflow generation or LLM-heavy handling**.
The system must first decide whether it should clarify, act directly, or plan deliberately.

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

### Layer C — Brain / routing layer
Responsible for:
- receiving the raw user request first,
- deciding whether the request should go to `CLARIFY`, `FAST`, or `SLOW`,
- preventing premature execution when the request is underspecified,
- choosing the cheapest safe processing path.

This is the **front-door decision layer**.
It sits before deeper orchestration and before the repair loop.

### Layer D — Agent orchestration layer
Responsible for:
- understanding the request in execution terms,
- deciding whether to create, update, test, or repair,
- managing the iterative workflow loop,
- deciding when success criteria are met,
- deciding when to ask the user for confirmation.

This is the deeper product brain after routing has already chosen the path.

### Layer E — n8n integration layer
Responsible for:
- creating workflows,
- updating workflows,
- activating workflows,
- running workflows,
- reading execution results,
- retrieving errors and outputs,
- validating payload compatibility with n8n.

### Layer F — Validation and repair layer
Responsible for:
- checking structural validity,
- checking execution outcome,
- comparing observed output to requested output,
- identifying likely repair points,
- feeding revised workflow definitions back into n8n.

### Layer G — Environment/runtime layer
Responsible for:
- local runtime dependencies,
- Ollama/local model availability,
- Node.js/npm availability,
- n8n availability,
- filesystem/log directories,
- local credentials/config loading.

### Layer H — Persistence/logging layer
Responsible for:
- request logs,
- workflow versions,
- execution IDs,
- repair attempts,
- user confirmation state,
- persistent memory/config state,
- learned operational rules.

---

## 3. Brain-first request flow
Before the system commits to workflow generation or repair, the Brain must choose how the request should be handled.

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

### CLARIFY path
Used when the request is too ambiguous or missing critical information.
The system should ask a focused clarifying question instead of pretending it understands.

### FAST path
Used when the request is clear, narrow, and safe enough for direct handling without heavyweight planning.

### SLOW path
Used when the request is complex, likely multi-step, or likely to require deliberate planning, execution, verification, and repair.

The dedicated Brain behavior is documented in [`BRAIN_ARCHITECTURE.md`](./BRAIN_ARCHITECTURE.md).

---

## 4. Core system flow
### Primary flow
1. User enters request.
2. UI sends request to the Brain / routing layer.
3. Brain routes the request to `CLARIFY`, `FAST`, or `SLOW`.
4. If `CLARIFY`, the system asks a focused question and waits.
5. If `FAST`, the system uses the Controller or direct path to perform the action and then verifies the outcome.
6. If `SLOW`, the system builds a plan.
7. If needed, the plan is shown to the user for confirmation.
8. The system creates or updates the workflow.
9. Validation layer checks structure.
10. n8n integration layer runs test execution.
11. Validation/repair layer inspects outputs and errors.
12. If failure exists, orchestration triggers repair.
13. If technical and functional checks pass, UI asks user to confirm.
14. If user reports failure, the system resumes repair and may update learned rules.

---

## 5. Component responsibilities
### 5.1 Installer component
Responsibilities:
- detect environment,
- install missing runtime pieces,
- verify installation success,
- report failures clearly,
- write installer logs.

Must not:
- silently fail,
- claim success without verification.

### 5.2 Brain Router component
Responsibilities:
- classify the request into `CLARIFY`, `FAST`, or `SLOW`,
- block premature execution when critical information is missing,
- decide whether lightweight direct handling is safe,
- decide whether explicit planning is required.

Must not:
- force every request into the same path,
- treat all requests as if they should immediately hit workflow generation,
- guess away critical ambiguity.

### 5.3 Intent interpretation / planning component
Responsibilities:
- identify what the user wants,
- extract trigger/input/output expectations,
- identify missing required details,
- normalize request into a workflow task definition,
- produce actionable plan steps in `SLOW` mode.

Must not:
- invent critical missing details without grounds,
- produce vague non-actionable plans.

### 5.4 Plan confirmation component
Responsibilities:
- show the intended execution plan when the task warrants it,
- allow the user to correct or approve the direction,
- prevent avoidable wrong-path execution on large or risky tasks.

Must not:
- introduce ceremony for every tiny request,
- ignore user corrections once the plan is shown.

### 5.5 Workflow generation component
Responsibilities:
- create a valid initial workflow draft,
- keep structure readable,
- prefer minimal viable workflow.

Must not:
- optimize for complexity over clarity,
- generate untestable junk.

### 5.6 Workflow validation component
Responsibilities:
- confirm the workflow is structurally acceptable,
- block execution if validation fails.

Must not:
- let obviously invalid workflow payloads proceed.

### 5.7 Execution analysis / verifier component
Responsibilities:
- inspect n8n run result,
- detect execution errors,
- detect output mismatches,
- compare observed result against expected result,
- decide whether the task should proceed to confirmation or return to repair.

Must not:
- treat “no exception” as equivalent to “task succeeded”.

### 5.8 Repair component
Responsibilities:
- modify workflow to address detected issues,
- preserve successful parts where possible,
- rerun the loop after each fix.

Must not:
- declare success after a blind edit,
- overwrite working parts carelessly when a localized fix is possible.

### 5.9 User confirmation component
Responsibilities:
- ask the user to verify after automated checks pass,
- collect what the user actually sees if there is still a problem.

Must not:
- treat technical success as final success.

### 5.10 Learned-rules component
Responsibilities:
- persist useful routing or execution lessons,
- store recurring safe patterns or recurring integration quirks,
- improve future routing and execution quality.

Must not:
- become hidden uncontrolled state,
- silently weaken correctness guarantees.

---

## 6. Data contracts
### 6.1 Task definition contract
The orchestration layer should internally normalize user requests into a task definition that includes:

- user goal,
- trigger,
- input source,
- output target,
- expected result,
- missing dependencies,
- testable success signal.

### 6.2 Workflow contract
A workflow object must contain at minimum:
- name,
- nodes,
- connections,
- optional supported settings.

The payload must exclude fields that n8n rejects.

### 6.3 Execution analysis contract
Execution analysis should output at minimum:
- execution status,
- error presence/absence,
- key error message if any,
- observed result summary,
- comparison against expected result,
- next recommended action.

### 6.4 User confirmation contract
The confirmation state should capture:
- asked_for_confirmation: yes/no,
- user_confirmed_success: yes/no,
- user_reported_problem: yes/no,
- reported_symptoms: text.

### 6.5 Brain decision contract
The Brain should output at minimum:
- selected mode (`CLARIFY`, `FAST`, or `SLOW`),
- reason for selection,
- whether plan confirmation is required,
- any blocking ambiguity,
- any learned rule applied.

---

## 7. Source-of-truth rules
### Product truth
The documentation files define what the product is supposed to do.

### Runtime truth
The actual execution state in n8n and local runtime defines what happened.

### User truth
If the user says the result is still wrong, the system must treat that as a real failure signal even if internal tests passed.

### Routing truth
If the request is underspecified, the Brain must treat that as a routing problem before it becomes an execution problem.

---

## 8. Architecture constraints
1. n8n-first focus must remain explicit.
2. Installer reliability is part of the architecture.
3. Brain routing logic is core architecture, not a cosmetic wrapper.
4. Repair loop logic is core architecture, not an add-on.
5. User confirmation is part of the control flow.
6. Logging must support post-failure diagnosis.

---

## 9. Failure-aware design rules
The system must assume that failure can occur at every layer:

- installer failure,
- dependency failure,
- routing failure,
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

## 10. Recommended repository-level document map
- `PROJECT_IDEA.md` — what the product is and why it exists
- `SPECIFICATION.md` — how the product must behave
- `ARCHITECTURE.md` — system layers and responsibilities
- `BRAIN_ARCHITECTURE.md` — routing, planning, execution, verification, learned rules
- `INSTALLER_SPEC.md` — install behavior and failure handling
- `CLAUDE.md` — AI coding rules and repo working constraints

---

## 11. Core architectural truth
The real product loop is larger than workflow repair alone:

user intent -> Brain routing -> planning or direct handling -> workflow generation -> validation -> execution -> repair -> user confirmation -> learning

If any one of these parts is weak, the whole product becomes unreliable.
