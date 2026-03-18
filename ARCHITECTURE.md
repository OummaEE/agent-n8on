# ARCHITECTURE

## Purpose
This document describes the intended architecture of agent-n8On as an n8n-first desktop product.

The architecture should prioritize clarity, debuggability, repairability, and explicit separation between:

- what exists now,
- what is target architecture,
- what still depends on future implementation.

---

## 1. Architectural principle
The system is not just a chat app.
It is a layered workflow engineering system with a user interface on top.

The core architectural goal is:

- accept user intent,
- decide how the request should be handled,
- choose the right model/provider path,
- inject relevant n8n-specific knowledge,
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
- collecting user-reported failure details,
- surfacing whether the system is operating in local-only or online-assisted mode.

### Layer C — Brain / routing layer
Responsible for:
- receiving the raw user request first,
- deciding whether the request should go to `CLARIFY`, `FAST`, or `SLOW`,
- preventing premature execution when the request is underspecified,
- choosing the cheapest safe processing path.

This is the **front-door decision layer**.
It sits before deeper orchestration and before the repair loop.

### Layer D — Provider / model selection layer
Responsible for:
- deciding whether the task should use `local`, `api`, or `auto` mode,
- falling back when the preferred provider is unavailable,
- respecting offline constraints,
- keeping weak machines usable.

This layer is required because pure local generation may be too weak on low-spec machines.

### Layer E — Knowledge / retrieval layer
Responsible for:
- retrieving relevant n8n-specific knowledge for the current task,
- preferring local/offline knowledge first,
- optionally augmenting with online documentation when internet is available,
- supplying templates, recipes, repair memory, and documentation fragments.

This layer should eventually include:
- local n8n templates,
- local repair memory,
- local documentation snippets,
- optional online augmentation.

### Layer F — Agent orchestration layer
Responsible for:
- understanding the request in execution terms,
- deciding whether to create, update, test, or repair,
- managing the iterative workflow loop,
- deciding when success criteria are met,
- deciding when to ask the user for confirmation.

This is the deeper product brain after routing and provider selection have already chosen the path.

### Layer G — n8n integration layer
Responsible for:
- creating workflows,
- updating workflows,
- activating workflows,
- running workflows,
- reading execution results,
- retrieving errors and outputs,
- validating payload compatibility with n8n.

### Layer H — Validation and repair layer
Responsible for:
- checking structural validity,
- checking execution outcome,
- comparing observed output to requested output,
- identifying likely repair points,
- feeding revised workflow definitions back into n8n.

### Layer I — Environment/runtime layer
Responsible for:
- local runtime dependencies,
- Ollama/local model availability,
- optional API provider credentials,
- Node.js/npm availability,
- n8n availability,
- filesystem/log directories,
- local credentials/config loading,
- online/offline state detection.

### Layer J — Persistence/logging layer
Responsible for:
- request logs,
- workflow versions,
- execution IDs,
- repair attempts,
- user confirmation state,
- persistent memory/config state,
- learned operational rules,
- local templates,
- local documentation cache.

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

## 4. Provider-aware flow
After routing, the system should decide how generation and reasoning should run.

```text
Brain result
  -> Provider selector
       ├── local  -> Ollama / local model path
       ├── api    -> remote/API model path
       └── auto   -> choose safest available route
```

### `local`
Use only local model(s).
Suitable for:
- offline operation,
- privacy-sensitive workflows,
- users with sufficient local hardware.

### `api`
Use only remote/API model(s).
Suitable for:
- weak machines,
- high-complexity generation,
- cases where local model quality is insufficient.

### `auto`
Choose the best available path using factors such as:
- internet availability,
- local model health,
- task complexity,
- user preferences,
- policy rules.

### Current reality
The codebase currently appears to have only the **local Ollama path** implemented.
The provider layer is therefore partly a **target architecture item**, not fully implemented reality.
See [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md).

---

## 5. Knowledge / retrieval flow
The product should not rely only on generic model memory.
It should retrieve relevant n8n-specific context for the current task.

```text
Task intent
  -> Knowledge selector
       ├── local templates
       ├── local repair memory
       ├── local documentation cache
       ├── local instruction packs / skills
       └── online docs augmentation (if internet available)
```

### Offline-first rule
If internet is unavailable, the system should still be able to function using:
- local templates,
- local repair memory,
- local cached docs,
- local instruction packs.

### Online augmentation rule
If internet is available, the system may enrich the context with live documentation or updated external guidance.

### Current reality
The repo currently appears to have:
- local skills loading,
- n8n API operations,
- local model usage.

The repo does **not yet appear** to have a dedicated local n8n documentation retrieval layer or provider-aware hybrid generation path in production code.
See [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md).

---

## 6. Core system flow
### Primary flow
1. User enters request.
2. UI sends request to the Brain / routing layer.
3. Brain routes the request to `CLARIFY`, `FAST`, or `SLOW`.
4. Provider layer decides whether execution should use `local`, `api`, or `auto` path.
5. Knowledge layer retrieves relevant n8n-specific context.
6. If `CLARIFY`, the system asks a focused question and waits.
7. If `FAST`, the system uses the Controller or direct path to perform the action and then verifies the outcome.
8. If `SLOW`, the system builds a plan.
9. If needed, the plan is shown to the user for confirmation.
10. The system creates or updates the workflow.
11. Validation layer checks structure.
12. n8n integration layer runs test execution.
13. Validation/repair layer inspects outputs and errors.
14. If failure exists, orchestration triggers repair.
15. If technical and functional checks pass, UI asks user to confirm.
16. If user reports failure, the system resumes repair and may update learned rules.

---

## 7. Component responsibilities
### 7.1 Installer component
Responsibilities:
- detect environment,
- install missing runtime pieces,
- verify installation success,
- report failures clearly,
- write installer logs.

Must not:
- silently fail,
- claim success without verification.

### 7.2 Brain Router component
Responsibilities:
- classify the request into `CLARIFY`, `FAST`, or `SLOW`,
- block premature execution when critical information is missing,
- decide whether lightweight direct handling is safe,
- decide whether explicit planning is required.

Must not:
- force every request into the same path,
- treat all requests as if they should immediately hit workflow generation,
- guess away critical ambiguity.

### 7.3 Provider selector component
Responsibilities:
- choose between local and API reasoning/generation modes,
- degrade safely when internet is unavailable,
- avoid sending weak local hardware into tasks it cannot handle reliably.

Must not:
- pretend hybrid mode exists if only local mode is implemented,
- hide provider failures behind fake success.

### 7.4 Knowledge selector component
Responsibilities:
- retrieve only relevant n8n-specific context,
- prefer offline/local knowledge first,
- add online augmentation only when available and useful.

Must not:
- depend entirely on live internet access,
- dump irrelevant docs into the prompt.

### 7.5 Intent interpretation / planning component
Responsibilities:
- identify what the user wants,
- extract trigger/input/output expectations,
- identify missing required details,
- normalize request into a workflow task definition,
- produce actionable plan steps in `SLOW` mode.

Must not:
- invent critical missing details without grounds,
- produce vague non-actionable plans.

### 7.6 Plan confirmation component
Responsibilities:
- show the intended execution plan when the task warrants it,
- allow the user to correct or approve the direction,
- prevent avoidable wrong-path execution on large or risky tasks.

Must not:
- introduce ceremony for every tiny request,
- ignore user corrections once the plan is shown.

### 7.7 Workflow generation component
Responsibilities:
- create a valid initial workflow draft,
- keep structure readable,
- prefer minimal viable workflow.

Must not:
- optimize for complexity over clarity,
- generate untestable junk.

### 7.8 Workflow validation component
Responsibilities:
- confirm the workflow is structurally acceptable,
- block execution if validation fails.

Must not:
- let obviously invalid workflow payloads proceed.

### 7.9 Execution analysis / verifier component
Responsibilities:
- inspect n8n run result,
- detect execution errors,
- detect output mismatches,
- compare observed result against expected result,
- decide whether the task should proceed to confirmation or return to repair.

Must not:
- treat “no exception” as equivalent to “task succeeded”.

### 7.10 Repair component
Responsibilities:
- modify workflow to address detected issues,
- preserve successful parts where possible,
- rerun the loop after each fix.

Must not:
- declare success after a blind edit,
- overwrite working parts carelessly when a localized fix is possible.

### 7.11 User confirmation component
Responsibilities:
- ask the user to verify after automated checks pass,
- collect what the user actually sees if there is still a problem.

Must not:
- treat technical success as final success.

### 7.12 Learned-rules / memory component
Responsibilities:
- persist useful routing or execution lessons,
- store recurring safe patterns or recurring integration quirks,
- improve future routing and execution quality,
- support future repair memory and template reuse.

Must not:
- become hidden uncontrolled state,
- silently weaken correctness guarantees.

---

## 8. Data contracts
### 8.1 Task definition contract
The orchestration layer should internally normalize user requests into a task definition that includes:

- user goal,
- trigger,
- input source,
- output target,
- expected result,
- missing dependencies,
- testable success signal.

### 8.2 Workflow contract
A workflow object must contain at minimum:
- name,
- nodes,
- connections,
- optional supported settings.

The payload must exclude fields that n8n rejects.

### 8.3 Execution analysis contract
Execution analysis should output at minimum:
- execution status,
- error presence/absence,
- key error message if any,
- observed result summary,
- comparison against expected result,
- next recommended action.

### 8.4 User confirmation contract
The confirmation state should capture:
- asked_for_confirmation: yes/no,
- user_confirmed_success: yes/no,
- user_reported_problem: yes/no,
- reported_symptoms: text.

### 8.5 Brain decision contract
The Brain should output at minimum:
- selected mode (`CLARIFY`, `FAST`, or `SLOW`),
- reason for selection,
- whether plan confirmation is required,
- any blocking ambiguity,
- any learned rule applied.

### 8.6 Provider decision contract
The provider layer should output at minimum:
- selected mode (`local`, `api`, or `auto` result),
- reason for selection,
- fallback path if relevant,
- whether the system is online or offline.

---

## 9. Source-of-truth rules
### Product truth
The documentation files define what the product is supposed to do.

### Runtime truth
The actual execution state in n8n and local runtime defines what happened.

### User truth
If the user says the result is still wrong, the system must treat that as a real failure signal even if internal tests passed.

### Routing truth
If the request is underspecified, the Brain must treat that as a routing problem before it becomes an execution problem.

### Online/offline truth
If internet is unavailable, the system must treat that as a real knowledge/provider constraint instead of pretending online assistance exists.

---

## 10. Architecture constraints
1. n8n-first focus must remain explicit.
2. Installer reliability is part of the architecture.
3. Brain routing logic is core architecture, not a cosmetic wrapper.
4. Provider selection is core architecture, not an afterthought.
5. Offline-first knowledge behavior must be explicit.
6. Repair loop logic is core architecture, not an add-on.
7. User confirmation is part of the control flow.
8. Logging must support post-failure diagnosis.

---

## 11. Failure-aware design rules
The system must assume that failure can occur at every layer:

- installer failure,
- dependency failure,
- routing failure,
- provider failure,
- knowledge lookup failure,
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

## 12. Recommended repository-level document map
- `PROJECT_IDEA.md` — what the product is and why it exists
- `SPECIFICATION.md` — how the product must behave
- `ARCHITECTURE.md` — system layers and responsibilities
- `BRAIN_ARCHITECTURE.md` — routing, planning, execution, verification, learned rules
- `INSTALLER_SPEC.md` — install behavior and failure handling
- `IMPLEMENTATION_STATUS.md` — what is verified reality now
- `ROADMAP.md` — what still needs to be built next
- `CLAUDE.md` — AI coding rules and repo working constraints

---

## 13. Core architectural truth
The real product loop is larger than workflow repair alone:

user intent -> Brain routing -> provider selection -> knowledge retrieval -> planning or direct handling -> workflow generation -> validation -> execution -> repair -> user confirmation -> learning

If any one of these parts is weak, the whole product becomes unreliable.
