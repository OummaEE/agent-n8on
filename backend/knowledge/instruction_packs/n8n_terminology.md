# n8n Terminology Reference

Use these canonical terms when generating workflows, naming nodes, explaining errors, and writing repair messages.

## Canonical terms

| Term | Means | Do NOT use |
|------|-------|-----------|
| workflow | User's automation (the full JSON) | flow, scenario, pipeline, automation |
| node | One step in a workflow | block, action, step, component |
| trigger | First node — starts the workflow | initiator, starter, entry point |
| execution | One run of a workflow | run, instance, job |
| credential | Stored auth (API key, OAuth token) | secret, token, password, auth |
| canvas | The visual build area in n8n UI | editor, board, workspace |
| connection | Line between two nodes | edge, wire, link |
| pin | Saved node output used for testing | freeze, lock, cache |
| expression | `{{ $json.field }}` — dynamic value reference | template, variable, interpolation |
| item | One data object flowing through nodes | record, row, entry, element |
| sticky note | Annotation on canvas | comment, label, note |

## Node naming rules

- Node names are proper nouns: "HTTP Request", "Google Sheets", "Slack"
- Feature names are lowercase: "canvas", "workflow", "execution"
- "n8n" is always lowercase, even at sentence start
- Generated node `name` fields should describe what the node does: "Fetch RSS Feed", "Filter Active Users", "Send Slack Alert"
- Avoid generic names like "HTTP Request1" — use descriptive names

## In error messages

- Say "node" not "block" or "step"
- Say "execution" not "run"
- Say "credential" not "API key" or "token" (unless referring to a specific key)
- Say "workflow" not "flow"
- Reference failing nodes by their actual name, not by type

## In repair explanations

- "The [Node Name] node failed because..." — not "Step 3 failed"
- "Check the credential for [Service]" — not "Check the API key"
- "The execution stopped at [Node Name]" — not "The run crashed at step 3"
