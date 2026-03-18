# BRAIN_ARCHITECTURE

## Purpose
This document defines the missing pre-execution decision layer of agent-n8On: the **Brain**.

The Brain exists before the workflow generation / repair loop.
Its job is to decide **how a request should be processed before handing work to deeper execution logic**.

This document complements `ARCHITECTURE.md` and `SPECIFICATION.md`.
It focuses specifically on:

- request routing,
- FAST / SLOW / CLARIFY modes,
- planning,
- confirmation,
- execution,
- verification,
- learned rules.

---

## 1. High-level idea
Not every user request should go through the same path.

Some requests are too ambiguous and must be clarified first.
Some are simple enough for direct execution.
Some require deliberate multi-step planning, confirmation, execution, and verification.

The Brain is the control layer that makes that decision.

---

## 2. Core routing scheme
```text
User
  -> Brain (Router)
       ├── CLARIFY -> ask clarifying question (no execution yet)
       ├── FAST    -> Controller -> direct action / direct n8n handling
       └── SLOW    -> Planner
                     -> plan steps
                     -> optional plan confirmation
                     -> Executor
                     -> Verifier
                     -> learned rules saved
```

This is the missing front-door architecture that sits **before** the repair loop described in `SPECIFICATION.md`.

---

## 3. Brain responsibilities
The Brain is responsible for deciding:

1. whether the request is clear enough to execute,
2. whether the request is simple enough for a direct path,
3. whether the request requires explicit multi-step planning,
4. whether the plan should be shown to the user before execution,
5. how to verify the outcome,
6. what to remember as learned operational rules.

The Brain must not be treated as a cosmetic wrapper around the LLM.
It is a control layer.

---

## 4. Router
### Role
The Router is the Brain entry point.
It receives the user request and chooses one of three modes:

- `CLARIFY`
- `FAST`
- `SLOW`

### Router decision goal
Choose the cheapest safe path.

### Router decision principles
#### Route to CLARIFY when:
- the user intent is underspecified,
- a critical input/output/target is missing,
- success cannot be tested meaningfully yet,
- proceeding would likely create junk or false confidence.

#### Route to FAST when:
- the request is clear,
- the task is narrow,
- the execution path is straightforward,
- a full planning phase would be unnecessary overhead.

#### Route to SLOW when:
- the request is complex,
- multiple steps or dependencies exist,
- workflow creation or repair likely needs explicit reasoning,
- the user may benefit from seeing the plan first,
- verification requires structured thinking.

---

## 5. CLARIFY mode
### Purpose
Prevent the system from pretending it understands what it does not understand.

### Behavior
In `CLARIFY`, the Brain does **not** commit to execution.
It asks the user a focused question to remove the blocking ambiguity.

### Examples of clarification needs
- destination unknown,
- trigger unclear,
- expected result not testable,
- missing integration target,
- ambiguous source data.

### Rule
A clarification question should be specific and unblock execution.
It should not be vague filler.

### Important note
The key rule here is architectural, not cosmetic:
**the system should not fall into workflow generation just because an LLM can guess.**

---

## 6. FAST mode
### Purpose
Handle clear, bounded requests with minimum overhead.

### Flow
```text
User -> Brain Router -> FAST -> Controller -> action / n8n direct path -> result
```

### Suitable cases
- simple workflow retrieval,
- direct workflow run,
- direct workflow update with known target,
- simple diagnostic request,
- simple n8n operation where the path is already obvious.

### FAST mode rule
FAST is allowed only when skipping explicit planning does not materially reduce safety or correctness.

### FAST mode relation to n8n
FAST may still invoke n8n-related operations directly through the Controller.
This does **not** mean the task bypasses validation or verification entirely.
It means it bypasses heavyweight planning.

---

## 7. SLOW mode
### Purpose
Handle requests that require deliberate decomposition, structured execution, and explicit verification.

### Flow
```text
User
 -> Brain Router
 -> SLOW
 -> Planner
 -> plan steps
 -> optional user confirmation of plan
 -> Executor
 -> Verifier
 -> learned rules saved
```

### SLOW mode is required when:
- a workflow must be designed from intent,
- a repair loop is likely,
- multiple dependencies or transformations exist,
- execution order matters,
- verification is non-trivial,
- the task carries a high risk of silent wrongness.

---

## 8. Planner
### Role
The Planner converts the user request into a structured execution plan.

### Planner output should include at minimum:
- goal,
- assumptions,
- required inputs,
- intended actions,
- expected outputs,
- verification idea,
- whether plan confirmation is needed.

### Planner rule
The Planner should produce **actionable** steps, not vague summaries.

Bad planning:
- “Create something for the user”
- “Fix workflow if needed”

Good planning:
- identify trigger,
- generate workflow draft,
- validate payload,
- execute test run,
- inspect output,
- compare against expected result,
- ask user to confirm,
- continue repair if mismatch remains.

---

## 9. Plan confirmation
### Purpose
For some SLOW tasks, the user should be shown the plan before execution starts.

### Use plan confirmation when:
- the task is large or costly,
- assumptions are significant,
- side effects may matter,
- the user should approve the direction before execution.

### Confirmation rule
Plan confirmation is not needed for every task.
It is a control tool, not ceremony.

### If user rejects or corrects the plan
The Brain should revise the plan rather than forcing execution.

---

## 10. Executor
### Role
The Executor carries out the approved or internally accepted plan.

### Responsibilities
- execute steps in order,
- call the relevant lower-level tools/components,
- pass outputs forward between steps,
- preserve enough state for verification and debugging.

### In n8n-related work, Executor may:
- create workflows,
- update workflows,
- validate workflows,
- run workflows,
- inspect executions,
- apply repair attempts,
- ask for further clarification if execution exposes missing information.

---

## 11. Verifier
### Role
The Verifier checks whether the execution actually achieved the intended result.

### This is not the same as “no exception happened.”
The Verifier must compare results against the goal.

### Verification dimensions
#### Technical verification
- no n8n execution errors,
- valid run state,
- no broken node path,
- no activation/runtime failure.

#### Functional verification
- observed result matches requested result,
- expected side effect occurred,
- produced output is materially correct.

#### User-facing verification
- ask the user whether it works in their real context.

### Verifier relation to existing product rules
The Verifier is the component-level realization of the success criteria already defined in `SPECIFICATION.md`.

---

## 12. Learned rules
### Purpose
The Brain should not stay stateless if the system repeatedly learns useful operational constraints.

### Learned rules may capture:
- preferred handling patterns,
- known-safe shortcuts,
- recurring integration quirks,
- user-specific working preferences,
- recurring repair patterns that improved results.

### Learned rules must not become hidden chaos
They should be:
- inspectable,
- bounded,
- overridable,
- saved deliberately.

### Rule
A learned rule should only be persisted if it improves future routing or execution quality without silently weakening correctness.

---

## 13. Relationship to Controller
### Controller role
The Controller is the lower-level action layer that can execute deterministic operations and connect Brain decisions to real system actions.

### Relationship
- Brain decides the processing strategy.
- Controller carries out the relevant direct path or delegated actions.

### Simplified relationship
```text
Brain = decide how to handle
Controller = do the handling work
```

---

## 14. Relationship to repair loop
The repair loop in `SPECIFICATION.md` begins after the system has already committed to execution.

The Brain architecture described here sits **before and around** that loop:

- Router decides whether the system should clarify, execute directly, or plan.
- Planner structures SLOW execution.
- Executor performs the workflow work.
- Verifier evaluates outcome.
- Learned rules influence future routing.

So the repair loop is not the entire intelligence layer.
It is one part of the deeper SLOW execution path.

---

## 15. Full request lifecycle
```text
User request
  -> Brain Router
      -> CLARIFY
           -> ask precise question
           -> wait for user answer
      -> FAST
           -> Controller
           -> direct operation / direct n8n path
           -> verify outcome
      -> SLOW
           -> Planner
           -> plan steps
           -> optional plan confirmation
           -> Executor
           -> Verifier
           -> if needed: repair loop
           -> ask user to confirm
           -> save learned rules
```

---

## 16. Core architectural truth
Without this Brain layer, the system risks treating all requests as if they should go straight into workflow work or LLM generation.

That is sloppy architecture.

The real control flow is:

1. first decide **how** to handle the request,
2. then execute,
3. then verify,
4. then learn.

That decision layer is part of the product architecture and must be documented explicitly.
