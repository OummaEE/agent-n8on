# Error Message Patterns for n8n Workflows

Use this pattern when explaining workflow errors to the user.

## Formula

Every error message to the user must follow:

**What happened** + **Why (if known)** + **What to do next**

## Examples

| Bad | Good |
|-----|------|
| "Error 401" | "The Google Sheets node could not authenticate. The credential may have expired. Re-authorize the Google Sheets credential in n8n." |
| "HTTP Request failed" | "The HTTP Request node returned 404. The URL may be incorrect. Check the URL and try again." |
| "Execution error" | "The execution stopped at the Slack node. The channel name was not found. Verify the channel exists and the bot has access." |
| "Timeout" | "The HTTP Request node timed out after 10 seconds. The API may be slow. Try increasing the timeout or adding a retry." |
| "JSON parse error" | "The HTTP Request node received a non-JSON response. The API may return HTML on errors. Check the URL returns valid JSON." |

## Rules

1. **Name the failing node** — always say which node failed, by its actual name
2. **Name the error type** — auth, timeout, not found, invalid data, rate limit
3. **Give one actionable step** — not a list of 10 things to try
4. **Never blame the user** — say "the credential may have expired", not "you entered the wrong key"
5. **Be specific** — if the HTTP code is 429, say "rate limit exceeded", not "request failed"

## Error type quick reference

| Error signal | Type | Typical cause | First fix |
|-------------|------|---------------|-----------|
| 401, "unauthorized" | auth | Credential expired or wrong | Re-authorize credential |
| 403, 429, "too many requests" | rate_limit | API limit hit | Reduce batch size or add delay |
| 404, "not found" | not_found | Wrong ID, URL, or resource name | Verify the resource exists |
| 400, "invalid", "missing" | config | Wrong node parameters | Check required fields |
| timeout, ECONNREFUSED | network | Service down or unreachable | Check URL, retry later |
| "Cannot read property" | expression | Expression references missing field | Check input data structure |
| "Unexpected token" | parse | Non-JSON response | Check URL, Content-Type |

## For repair loop messages

When the agent is reporting a repair attempt:

- "Attempting to fix: [what changed]" — be specific about what was modified
- "The [Node Name] node now uses [new value] instead of [old value]"
- "Repair attempt [N/3]: [one-sentence description of the change]"

When the agent is bailing out:

- "I could not fix this automatically. The [Node Name] node needs [specific thing] that I cannot provide."
- Never say "unknown error" if any detail is available
- Always suggest one concrete manual step the user can take
