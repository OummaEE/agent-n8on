# HTTP Request Node — Common Patterns and Pitfalls

## Node type
`n8n-nodes-base.httpRequest`

## Required fields
- `method`: GET, POST, PUT, DELETE, PATCH
- `url`: full URL including protocol

## Common errors

### "Cannot read property 'json' of undefined"
- Cause: responseFormat set to 'string' when API returns JSON
- Fix: set `responseFormat` to `json`

### "ETIMEDOUT" or "ECONNREFUSED"
- Cause: target server unreachable or wrong URL
- Fix: verify URL is correct and server is running

### 401/403 errors
- Cause: missing or wrong authentication
- Fix: check credentials node is connected and auth type matches API requirements

## Best practices
- Always set `options.timeout` for external APIs (default: 10000ms)
- Use `options.retry.maxTries = 3` for unreliable endpoints
- For pagination: use `options.pagination` with `requestInterval` to avoid rate limits
- Binary data: set `responseFormat` to `file` when downloading files
- Send JSON body: set `sendBody = true`, `contentType = json`, populate `bodyParameters`
