# Debug Routing and Confidence Scoring

Use this when deciding how to debug a failing n8n workflow and whether a repair is worth attempting.

## Failure area routing

When a workflow execution fails, classify the failure area first, then choose what to inspect.

| Failure area | What to inspect via n8n API | Agent action |
|-------------|---------------------------|--------------|
| Node operation | `runData[nodeName][0].error` | Check node parameters, credential, input data |
| Trigger / webhook | Trigger node output, webhook URL | Verify webhook path, HTTP method, payload format |
| Expression error | `error.message` contains "Cannot read" | Check that referenced field exists in input items |
| Credential auth | HTTP 401/403 in node error | Verify credential exists, is not expired |
| Binary data | Binary attachment fields | Check file size limits, encoding, Content-Type |
| Rate limit | HTTP 429 or "too many requests" | Reduce batch size, add Wait node between calls |
| Connection/network | timeout, ECONNREFUSED | Check that external service is reachable |

## Confidence scoring for repair decisions

Before attempting a repair, classify confidence:

| Level | Meaning | Agent action |
|-------|---------|-------------|
| **CONFIRMED** | Root cause is clear from execution data (e.g., 401 + expired credential) | Attempt repair |
| **LIKELY** | Error pattern matches a known category but root cause is inferred | Attempt repair, tell user what was assumed |
| **UNCONFIRMED** | Error is ambiguous or multi-node failure | Ask user for more information before repair |
| **BAILOUT** | Repair is impossible without manual user action | Stop repair loop, explain why |

## Hard bailout triggers

Do NOT attempt repair. Tell the user honestly and suggest manual action.

| Trigger | Why unfixable | What to tell user |
|---------|--------------|-------------------|
| Credential does not exist in n8n | Agent cannot create credentials | "This workflow needs a [Service] credential. Please add it in n8n Settings > Credentials." |
| OAuth token expired and needs browser re-auth | Agent cannot open browser for OAuth | "The [Service] credential needs re-authorization. Open n8n, go to Credentials, and re-connect [Service]." |
| External API requires paid plan / approval | Agent cannot sign up for services | "The [Service] API returned 403. This may require a paid plan or API approval." |
| Race condition / timing-dependent failure | Retry won't reliably fix it | "This failure may be timing-dependent. Try running the workflow again manually." |
| Node requires manual UI configuration | Some nodes need canvas interaction | "The [Node Name] node needs manual configuration in the n8n editor." |
| Binary file too large for n8n limits | Agent cannot change n8n server limits | "The file exceeds n8n's size limit. Try with a smaller file or adjust n8n server settings." |

## Hypothesis structure for repair

When attempting a repair, structure the reasoning:

```
When [input/condition],
the [Node Name] node does [wrong behavior]
because [root cause].
Fix: [specific change to node parameters].
Confidence: [CONFIRMED/LIKELY].
```

Example:
```
When the workflow runs with 50 RSS feeds,
the HTTP Request node returns 429
because the API rate-limits to 10 requests/minute.
Fix: add a Wait node (5s) between batches of 10.
Confidence: CONFIRMED (429 status code in execution data).
```

## Max repair attempts

- 3 attempts maximum (existing MAX_RETRIES)
- Each attempt must change something different
- If all 3 fail, bailout with honest summary of what was tried
- Never repeat the same fix twice
