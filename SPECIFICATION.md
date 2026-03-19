# SPECIFICATION

## Purpose
This document defines the **target behavior** of agent-n8On as an n8n-first desktop application.

This file describes what the product **should** do when the architecture is fully realized.
It must not be confused with current implementation reality.

For what is already verified, see [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md).
For what is planned next, see [`ROADMAP.md`](./ROADMAP.md).

The goal is not merely to generate workflows. The goal is to produce working workflows, verify their behavior, and continue debugging until the user confirms success.

---

## 1. Product scope
agent-n8On is a desktop application that should:

1. install a local automation environment with minimal user friction,
2. route requests through Brain-based handling,
3. choose an appropriate generation path (`local`, `api`, or `auto`),
4. retrieve relevant n8n-specific context,
5. create n8n workflows from natural-language requests,
6. test those workflows,
7. repair them iteratively,
8. confirm the result with the user before treating the task as done.

---

## 2. Primary user story
### Main flow
1. User explains the desired automation in plain language.
2. Brain routes the request to `CLARIFY`, `FAST`, or `SLOW`.
3. Provider layer chooses whether the task should use `local`, `api`, or `auto` mode.
4. Knowledge layer retrieves relevant n8n-specific context.
5. Agent generates a workflow or updates an existing one when needed.
6. Agent validates the workflow structure.
7. Agent runs the workflow in test conditions.
8. Agent inspects execution results and outputs.
9. Agent repairs the workflow if needed.
10. Agent checks whether the output matches the requested result.
11. Agent asks the user whether everything works on their side.
12. If the user reports a problem, the agent gathers concrete symptoms and continues debugging.

---

## 3. Definition of success
A workflow is considered technically and functionally correct only when all three stages below are satisfied.

### Stage A — Technical execution success
n8n must return no execution errors.

Examples:
- no node execution error,
- no schema/validation error,
- no activation error,
- no runtime crash visible in n8n execution data.

### Stage B — Requested result match
During testing, the agent must observe a result that matches the result requested by the user.

Examples:
- user asked for a row to be added to a sheet, and the row appears,
- user asked for a message to be sent, and the message is visible in the target output,
- user asked for transformed data, and the produced data matches the requested structure or content.

### Stage C — User confirmation
After Stage A and Stage B are satisfied, the agent must ask the user to confirm whether everything works in real usage.

If the user says it does not work, the workflow must not be marked complete.

---

## 4. Definition of failure
The task is not complete if any of the following is true:

1. n8n returns an error.
2. n8n returns no error, but the observed result does not match the requested result.
3. technical checks pass, but the user reports incorrect behavior.
4. the workflow works only partially.
5. a critical integration dependency is missing or misconfigured.
6. the selected provider path cannot actually execute the task.
7. required online knowledge is unavailable and no local fallback exists.

---

## 5. Request intake requirements
When a user asks for an automation, the agent must identify:

- the desired action,
- the input source,
- the expected output,
- any trigger condition,
- any external service involved,
- any missing information required for execution.

### If information is missing
The agent may ask for missing details only when the workflow cannot be meaningfully generated or tested without them.

Examples:
- missing credential-dependent target,
- unknown destination resource,
- unclear success output.

---

## 6. Provider selection requirements
The system should support these modes:

- `local`
- `api`
- `auto`

### Local mode
Use only local models and local knowledge.
Appropriate for:
- offline operation,
- privacy-sensitive cases,
- machines where local performance is adequate.

### API mode
Use remote/API model(s).
Appropriate for:
- weak local machines,
- heavy workflow generation,
- tasks where local model quality is insufficient.

### Auto mode
The system should choose the safest available path based on:
- internet availability,
- local model availability,
- local model health,
- task complexity,
- user preference or policy.

### Provider truthfulness rule
The system must not claim `local + api` hybrid support if only local mode is implemented.

---

## 7. Knowledge / retrieval requirements
The system should not rely only on generic model memory.
It should retrieve relevant n8n-specific context for the current task.

### Required knowledge sources
The intended knowledge layer should be able to use:
- local n8n templates,
- local repair memory,
- local documentation cache,
- local instruction packs / skill files,
- optional online documentation augmentation.

### Offline-first rule
If internet is unavailable, the system should still be able to function using:
- local templates,
- local repair memory,
- local cached docs,
- local instruction packs.

### Online augmentation rule
If internet is available, the system may enrich the context with live documentation or updated external guidance.

### n8n-specific rule
The knowledge layer should be optimized for **n8n-specific documentation, schemas, patterns, and examples**, not general web knowledge alone.

---

## 8. Workflow generation requirements
The agent must generate workflows that are:

- valid n8n workflow JSON,
- structurally coherent,
- aligned with the requested task,
- minimal where possible,
- repairable in later iterations.

### Generation principles
1. Prefer the smallest viable workflow that can satisfy the request.
2. Avoid unnecessary nodes.
3. Prefer deterministic logic over magic.
4. Make node naming readable.
5. Preserve workflow readability for later debugging.
6. Prefer retrieved trusted context over hallucinated structure when available.

---

## 9. Validation requirements
Before test execution, the agent must run validation checks.

### Required checks
1. Workflow JSON is parseable.
2. Required top-level fields exist.
3. Nodes list is present and non-empty.
4. Connections are structurally valid.
5. Referenced node names exist.
6. Workflow name is valid.
7. Payload sent to n8n contains only accepted fields.

### Validation outcome
- If validation fails, the agent must repair before running.
- If validation passes, the agent may proceed to test execution.

---

## 10. Test execution requirements
The agent must execute the workflow in a way that allows inspection of both errors and outputs.

### The agent must try to observe:
- execution status,
- node-level failures,
- last executed node,
- returned data,
- whether the expected side effect occurred,
- whether the provider path used was adequate for the task.

### Success during testing requires both:
1. no n8n execution error,
2. visible evidence that the requested result occurred.

---

## 11. Repair loop specification
The repair loop is the heart of the product.

### Loop steps
1. Generate or update workflow.
2. Validate workflow.
3. Execute workflow.
4. Inspect execution logs and output.
5. Compare observed result against requested result.
6. If any mismatch or failure exists, modify workflow.
7. Repeat until success criteria are met or stop conditions are reached.

### Repair inputs
The agent may use:
- workflow JSON,
- execution errors,
- execution logs,
- observed outputs,
- user clarification,
- user-reported symptoms after confirmation step,
- retrieved local or online n8n-specific context.

### Repair goals
The agent should try to fix:
- node configuration mistakes,
- invalid connections,
- wrong field mappings,
- wrong trigger assumptions,
- output mismatches,
- logic errors that prevent requested behavior.

---

## 12. User confirmation loop
Even if automated tests pass, the task remains provisional until the user confirms it works.

### Required confirmation prompt
The agent should ask the user something equivalent to:

“Technically the workflow ran without errors and the expected test result appeared. Please check on your side: does everything work correctly? If not, tell me exactly what you see or receive.”

### If user says “no”
The agent must collect:
- what the user expected,
- what the user actually sees,
- whether anything was missing,
- whether the wrong data appeared,
- screenshots/logs/messages if available.

Then the agent re-enters the repair loop.

---

## 13. Stop conditions
The repair loop may stop when one of the following is true:

1. success criteria and user confirmation are met,
2. a required credential or external dependency is missing,
3. the external system itself is failing outside workflow logic,
4. the request is too underspecified to continue safely,
5. the selected provider path is unavailable and no valid fallback exists,
6. the required knowledge is unavailable offline and online augmentation is impossible,
7. the agent has reached a configured retry limit and must summarize the blocking issue.

### Important rule
A retry limit is a control mechanism, not a reason to pretend success.

---

## 14. Error categories
The agent should classify failures into categories where possible.

### Category A — Environment/setup errors
Examples:
- n8n not running,
- local service unavailable,
- missing package/runtime,
- broken installation.

### Category B — Workflow structure errors
Examples:
- invalid JSON,
- invalid connections,
- unsupported fields,
- malformed node configuration.

### Category C — Integration/config errors
Examples:
- missing credentials,
- expired token,
- wrong URL,
- permission denied,
- API contract mismatch.

### Category D — Logic errors
Examples:
- workflow runs but output is wrong,
- wrong field mapped,
- wrong branch selected,
- trigger/condition mismatch.

### Category E — User-side mismatch
Examples:
- test output looked correct, but real destination behavior differs,
- user received wrong format,
- user expected another side effect.

### Category F — Provider/path mismatch
Examples:
- local model too weak for the task,
- API mode required but unavailable,
- auto mode chose an inadequate path.

### Category G — Knowledge retrieval failure
Examples:
- needed n8n docs not available locally,
- internet unavailable for online augmentation,
- retrieval returned irrelevant context.

---

## 15. Logging requirements
The system should preserve enough information to debug failures.

### The system should log:
- user request,
- Brain routing decision,
- provider decision,
- knowledge source selection,
- generated workflow version,
- validation result,
- execution identifiers,
- execution errors,
- repair attempts,
- final user confirmation state.

### Minimum principle
If a workflow fails and the agent cannot explain why, logging is insufficient.

---

## 16. Scope rules for completion
The agent must not mark a task as done merely because:

- workflow JSON exists,
- workflow saved successfully,
- workflow activated successfully,
- n8n did not throw a red error once.

Completion requires:
- successful execution,
- result match,
- user confirmation.

---

## 17. Non-goals
The agent is not required to:

- solve every integration problem without user credentials,
- guess missing business intent when the request is too vague,
- declare success without evidence,
- become a generic assistant for unrelated desktop actions as part of the core spec.

---

## 18. Quality bar
The product quality bar is:

- easy to install,
- honest about failure states,
- persistent in debugging,
- strict about what “works” means,
- anchored to user-confirmed reality, not just internal technical checks,
- explicit about provider limitations,
- explicit about online/offline knowledge limitations.
