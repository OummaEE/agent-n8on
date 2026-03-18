# PROJECT_IDEA

## Product name
agent-n8On

## One-line definition
A desktop app for non-technical users that installs a local n8n environment with one click, generates n8n workflows from plain-language requests, and iteratively fixes those workflows until they work.

## Core problem
n8n is powerful, but for normal users it has two brutal barriers:

1. Setup friction: installing and configuring the environment is difficult.
2. Debugging friction: generating a workflow is not enough if the workflow still breaks or produces the wrong result.

Most users do not want to learn npm, local services, credentials, environment variables, workflow JSON, execution logs, node types, and repair loops. They want the automation to work.

## Product thesis
The product should act as an autonomous n8n layer:

- install the environment automatically,
- translate user intent into n8n workflows,
- run and inspect the workflow,
- repair the workflow when it fails,
- confirm the result with the user when technical checks pass.

## Target user
Primary user:

- non-technical users,
- solo founders,
- creators,
- operators,
- small teams,
- people who need automations but do not want to learn n8n deeply.

Secondary user:

- semi-technical users who want to move faster by delegating workflow generation and repair.

## Main product promises
### 1. One-click local setup
The app installs and configures the core runtime needed for local n8n usage as much as possible automatically.

### 2. Self-healing workflow generation
The app does not stop at generating workflow JSON. It keeps iterating until the workflow is both technically valid and functionally aligned with the requested result.

## Definition of “working correctly”
A workflow is considered correct only when both of these conditions are true:

1. n8n returns no errors during test execution.
2. The observed test result matches the result requested by the user.

After these two conditions are met, the agent must ask the user to verify whether everything actually works. If the user says no, the agent must gather what the user sees or receives and continue debugging.

## Differentiation
This product is not just:

- a chat assistant,
- a generic local AI app,
- a simple workflow generator,
- a wrapper around n8n templates.

It is specifically an n8n-first desktop agent focused on:

- zero-friction setup,
- autonomous workflow generation,
- autonomous repair,
- user-confirmed completion.

## High-level product loop
1. User describes what they want.
2. Agent interprets the request.
3. Agent creates or updates an n8n workflow.
4. Agent validates and runs the workflow.
5. Agent inspects errors and outputs.
6. Agent repairs the workflow if needed.
7. Agent checks whether the output matches the requested result.
8. Agent asks the user to confirm real-world correctness.
9. If user reports problems, agent continues debugging.

## Why this product matters
Today, many AI workflow products generate workflows, but then dump the hard part on the user. The hard part is not generation. The hard part is getting the automation to actually work.

This product focuses on the ugly middle: setup, testing, debugging, repair, and confirmation.

## Scope boundaries
In scope:

- local installation and environment setup,
- n8n workflow generation,
- n8n execution inspection,
- iterative workflow repair,
- user confirmation loop,
- logs and diagnostics.

Out of scope for the core product definition:

- becoming a generic assistant for every desktop task,
- unlimited non-n8n automations,
- pretending a workflow is “done” just because JSON exists.

## Product risks
1. Environment complexity on Windows.
2. n8n/API/version differences.
3. Credentials and external integrations failing for reasons outside the workflow JSON.
4. False positives where a workflow runs without technical errors but still does the wrong thing.
5. Scope creep into a generic all-purpose agent.

## Product principles
1. n8n-first, not feature-chaos.
2. Repair quality matters more than flashy generation.
3. A workflow that runs but does the wrong thing is not a success.
4. User confirmation is mandatory before marking a task done.
5. Installer reliability is part of the product, not an afterthought.
