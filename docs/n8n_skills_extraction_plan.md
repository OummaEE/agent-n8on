# n8n .claude/skills — Extraction Plan for agent-n8on

**Date:** 2026-03-19
**Source:** `n8n-io/n8n/.claude/` (master branch)
**Goal:** Extract only what supports the core loop:
`request -> workflow -> validate -> execute -> repair -> confirm`

---

## 1. Full Inventory of n8n .claude/skills

| # | Skill | Purpose | Size |
|---|-------|---------|------|
| 1 | `n8n-conventions` | TypeScript/Vue/backend coding standards for the n8n monorepo | small |
| 2 | `reproduce-bug` | Structured framework to reproduce bugs with failing regression tests | large |
| 3 | `spec-driven-development` | Read spec -> implement -> verify alignment -> update spec | medium |
| 4 | `content-design` | UI copy guidelines (tone, terminology, i18n, error messages) | large |
| 5 | `create-pr` | PR title format, conventional commits, gh CLI template | medium |
| 6 | `linear-issue` | Linear ticket analysis (fetch, assess effort, identify node) | large |
| 7 | `loom-transcript` | Fetch Loom video transcripts via GraphQL API | small |

Also present (not skills):
- `commands/n8n-plan.md` — Linear ticket implementation planning
- `commands/n8n-triage.md` — Linear issue triage wrapper
- `agents/n8n-developer.md` — Full-stack n8n dev agent profile
- `agents/n8n-linear-issue-triager.md` — Issue triager agent

---

## 2. Classification: Useful vs. Ignore

### USEFUL for agent-n8on core loop

| Skill | Why useful | Which part of core loop |
|-------|-----------|-------------------------|
| **`n8n-conventions`** | Terminology glossary (workflow, node, trigger, execution, credential, canvas, connection). Error message pattern. Node naming conventions. | workflow generation, repair messaging |
| **`reproduce-bug`** | Test-layer routing table (which area -> which test pattern). Structured hypothesis -> test -> verify loop. Confidence scoring. | debugging, repair loop |
| **`content-design`** | **Terminology reference table** is gold — canonical n8n terms to use/avoid. Error message formula (what happened + why + what to do). | workflow generation (correct naming), repair (error interpretation) |

### IGNORE — n8n repo development only

| Skill | Why ignore |
|-------|-----------|
| `spec-driven-development` | About managing `.claude/specs/` in the n8n monorepo. Our spec is SPECIFICATION.md with different conventions. |
| `create-pr` | About n8n PR title format (`feat(editor): ...`). Not relevant to workflow generation. |
| `linear-issue` | About fetching/analysing Linear tickets via MCP. We don't use Linear. |
| `loom-transcript` | About fetching Loom video transcripts. No relevance to workflow generation or repair. |
| `commands/n8n-plan.md` | Linear ticket planning. |
| `commands/n8n-triage.md` | Linear issue triage. |
| `agents/n8n-developer.md` | Full-stack n8n monorepo developer. We're not developing n8n itself. |
| `agents/n8n-linear-issue-triager.md` | Linear issue triager agent. |

---

## 3. What to Extract and How to Adapt

### 3A. Terminology Reference -> `instruction_packs/n8n_terminology.md`

**Source:** `content-design/SKILL.md` terminology table + `n8n-conventions` key concepts

**Extract:**
```
| Term       | Use for                   | Avoid           |
|------------|---------------------------|-----------------|
| workflow   | User's automation         | flow, scenario  |
| node       | Step in workflow          | block, action   |
| trigger    | Workflow starter          | initiator       |
| execution  | Single workflow run       | run, instance   |
| credential | Stored authentication     | secret, token   |
| canvas     | Build area                | editor, board   |
| connection | Line between nodes        | edge, wire      |
| pin        | Save node output for test | freeze, lock    |
```

**Adapt for:** LLM system prompt context when generating workflow JSON.
The agent should use canonical n8n terminology in:
- generated node names
- error messages shown to users
- repair explanations

**Form:** `skills/instructions/n8n_terminology.md`

---

### 3B. Error Message Pattern -> `instruction_packs/error_message_patterns.md`

**Source:** `content-design/SKILL.md` error message section + `n8n-conventions` error handling

**Extract:**
- Formula: "What happened + why (if known) + what to do"
- Never blame the user
- Use specific node names, not generic labels
- Example: "Connection failed. Check the API key and try again."
- n8n error class: `UnexpectedError('message', { extra: { context } })`

**Adapt for:** SmartErrorInterpreter output formatting. When the agent explains
a workflow failure to the user, it should follow this pattern. Also useful for
the repair loop's user-facing messages.

**Form:** `skills/instructions/error_message_patterns.md`

---

### 3C. Bug Reproduction Test Routing -> `instruction_packs/debug_routing.md`

**Source:** `reproduce-bug/SKILL.md` area-to-test-layer routing table

**Extract the routing concept, NOT the specific paths:**

| Failure area        | What to inspect in n8n           | Agent action                    |
|---------------------|----------------------------------|---------------------------------|
| Node operation      | Node's execute() output          | Check node params, credentials  |
| Trigger/webhook     | Trigger registration + payload   | Verify webhook URL, method      |
| Execution engine    | Execution data, pinned data      | Get execution by ID, inspect    |
| Binary data         | Binary attachments in execution  | Check file size, encoding       |
| Credentials         | Auth headers / tokens            | Verify credential exists, test  |

**Also extract:**
- Confidence scoring: CONFIRMED / LIKELY / UNCONFIRMED / SKIPPED
- Hypothesis structure: "When [input/condition], the code does [wrong thing] because [root cause]"
- Hard bailout triggers (needs real API creds, race condition, manual UI)

**Adapt for:** The repair loop's failure classification. Currently `_handle_step_failure`
doesn't classify confidence. This routing table helps the agent decide whether a
repair is worth attempting or should bail with an honest "I can't fix this automatically."

**Form:** `skills/instructions/debug_routing.md` (merge with existing `debug_n8n_workflow.md`)

---

### 3D. Node Naming Conventions -> enhance existing `n8n_blocks/`

**Source:** `n8n-conventions` + `content-design` terminology

**Extract:**
- Node names are proper nouns: "Slack Node", "HTTP Request Node"
- Feature names are lowercase: "canvas", "workflow"
- "n8n" is always lowercase, even at sentence start
- Generated node `name` fields should be readable and descriptive

**Adapt for:** The workflow generation code in `n8n_blocks/` and `template_adapter.py`.
When the agent generates a workflow, node names should follow these conventions.

**Form:** Add a section to `skills/instructions/create_complex_workflow.md`

---

## 4. Priority Ranking — Top 5 for First Adaptation

| Priority | What | Source skill | Adapt into | Impact on core loop |
|----------|------|-------------|------------|---------------------|
| **1** | n8n terminology reference | `content-design` + `n8n-conventions` | `skills/instructions/n8n_terminology.md` | Workflow generation uses correct terms; error messages use canonical vocabulary; repair explanations are clearer |
| **2** | Error message patterns | `content-design` | `skills/instructions/error_message_patterns.md` | SmartErrorInterpreter produces better user-facing messages; matches n8n's own error style |
| **3** | Debug routing / confidence scoring | `reproduce-bug` | Merge into `skills/instructions/debug_n8n_workflow.md` | Repair loop classifies failures better; knows when to bail vs. retry; structured hypothesis |
| **4** | Node naming conventions | `content-design` + `n8n-conventions` | Append to `skills/instructions/create_complex_workflow.md` | Generated workflows have readable, n8n-standard node names |
| **5** | Hard bailout triggers | `reproduce-bug` | Add to `skills/instructions/debug_n8n_workflow.md` | Agent stops wasting repair cycles on unfixable failures (needs real API keys, race conditions) |

---

## 5. What NOT to Do

- Do NOT copy `spec-driven-development` — our SPECIFICATION.md serves this purpose differently
- Do NOT copy `create-pr` — we have our own git workflow
- Do NOT copy `linear-issue` or `loom-transcript` — no relevance to workflow generation
- Do NOT copy the n8n monorepo coding standards (TypeScript `satisfies`, Vue Composition API, Pinia stores) — we're not developing n8n itself
- Do NOT create new Python modules for this — it's all instruction_pack markdown
- Do NOT add these as "features" — they are reference material for the LLM context

---

## 6. Implementation Approach

Each adaptation should be:
1. A single markdown file in `skills/instructions/`
2. Written for LLM consumption (concise, table-heavy, example-rich)
3. Loaded by `KnowledgeSelector.retrieve_context()` when relevant keywords match
4. Tested by checking that the LLM output uses correct terminology / patterns

No new Python code required. No new modules. No new APIs.
Just markdown files that the existing knowledge retrieval system picks up.

---

## 7. Validation Criteria

After adaptation, verify:
- [ ] Generated workflow JSON uses canonical n8n terms (node names, descriptions)
- [ ] SmartErrorInterpreter output follows "what + why + what to do" pattern
- [ ] Repair loop logs confidence level (CONFIRMED/LIKELY/UNCONFIRMED)
- [ ] Repair loop bails on hard-bailout triggers instead of looping
- [ ] No n8n-repo-development concepts leaked into the agent's behavior
