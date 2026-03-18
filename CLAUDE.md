# CLAUDE.md

## Purpose
This file defines the working rules for AI-assisted development in the `agent-n8on` repository.

The goal is to reduce drift, context rot, accidental breakage, and feature chaos.

---

## 1. Project identity
This repository is for an **n8n-first desktop agent**.

It is not a generic AI playground.
Its core value is:

1. one-click local setup,
2. autonomous n8n workflow generation,
3. iterative workflow repair,
4. final user confirmation.

Any code change that weakens that focus is suspicious by default.

---

## 2. Source-of-truth order
When making changes, use this order of truth:

1. `SPECIFICATION.md`
2. `ARCHITECTURE.md`
3. `PROJECT_IDEA.md`
4. actual runtime constraints in code and n8n
5. README examples

If README conflicts with spec, the spec wins.

---

## 3. Non-negotiable product rules
### Rule 1
A workflow is not successful merely because it was generated.

### Rule 2
A workflow is not successful merely because n8n saved it.

### Rule 3
A workflow is not successful merely because one execution returned no error.

### Rule 4
A workflow is only considered complete when:
- n8n returns no execution errors,
- the observed result matches the requested result,
- the user confirms that it works.

### Rule 5
If the user says it still does not work, the task is not complete.

---

## 4. Development priorities
Prioritize work in this order:

1. installer reliability,
2. workflow validation correctness,
3. execution inspection quality,
4. repair loop quality,
5. clear user confirmation flow,
6. UI polish,
7. extra features.

Do not sacrifice core reliability for shiny features.

---

## 5. Coding rules
### General
- Prefer small, explicit functions.
- Prefer readable control flow over cleverness.
- Prefer deterministic logic over hidden magic.
- Keep module responsibilities narrow.
- Avoid giant mixed-purpose functions when adding new features.

### For n8n-related code
- Preserve compatibility with n8n payload constraints.
- Never send fields that n8n rejects if they can be filtered out.
- Validate before running when possible.
- Preserve readable node names.
- Keep generated workflow structure debuggable.

### For repair logic
- Repairs must be tied to an observed failure or mismatch.
- Do not mutate working parts blindly.
- Prefer minimal corrective edits.
- Keep enough logging to understand what changed between attempts.

### For user-facing logic
- Be honest about uncertainty.
- Do not claim success without evidence.
- Ask for confirmation after automated checks pass.
- If the user reports failure, gather concrete symptoms and continue.

---

## 6. Repository behavior rules for AI assistants
When editing this repo, an AI assistant should:

1. read relevant docs first,
2. preserve the n8n-first product focus,
3. avoid introducing unrelated assistant features unless explicitly requested,
4. avoid rewriting architecture casually,
5. prefer incremental changes over chaotic refactors,
6. update docs when behavior changes.

---

## 7. What must be documented when changed
If any of these change, docs must be updated in the same work cycle:

- definition of success,
- repair loop logic,
- installer flow,
- architecture layers,
- workflow validation rules,
- user confirmation flow.

---

## 8. Anti-patterns
Avoid these anti-patterns:

- feature sprawl that dilutes the n8n-first core,
- declaring success too early,
- burying core product logic in unreadable mega-functions,
- undocumented changes to repair logic,
- silent failure handling,
- making the product sound broader than it really is.

---

## 9. Pull request / change intent guideline
Every meaningful change should be explainable in one sentence:

- what problem it fixes,
- which layer it affects,
- how it supports the core loop.

If a change cannot be tied back to the core loop, question whether it belongs.

---

## 10. Core loop reminder
Always optimize for this loop:

plain-language request -> n8n workflow -> validation -> execution -> repair -> user confirmation

That is the product.
Everything else is secondary.
