# Webhook Node — Common Patterns and Pitfalls

## Node type
`n8n-nodes-base.webhook`

## Required fields
- `httpMethod`: GET, POST, PUT, etc.
- `path`: URL path suffix (auto-prefixed by n8n base URL)

## Common errors

### "Workflow could not be activated"
- Cause: webhook path conflicts with another active workflow
- Fix: use unique path per workflow

### "No data received"
- Cause: incoming request body empty or wrong Content-Type
- Fix: check sender sends `Content-Type: application/json` for JSON bodies

## Response modes
- `onReceived` — respond immediately, process in background (default)
- `lastNode` — wait for workflow to finish, return last node output
- `responseNode` — use a "Respond to Webhook" node for custom response

## Best practices
- Use `lastNode` response mode for synchronous APIs
- Set `options.rawBody = true` if you need the unparsed request body
- For binary data (file uploads): n8n auto-parses multipart/form-data
- Test webhooks: use n8n "Test URL" (different from production URL)
- Production URL only works when workflow is activated
