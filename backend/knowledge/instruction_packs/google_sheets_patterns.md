# Google Sheets Node — Common Patterns and Pitfalls

## Node type
`n8n-nodes-base.googleSheets`

## Required fields
- `operation`: append, read, update, delete, clear
- `documentId`: the spreadsheet ID from the URL
- `sheetName`: exact sheet tab name (case-sensitive)

## Common errors

### "Invalid range"
- Cause: range not in A1 notation or sheet name misspelled
- Fix: use format `SheetName!A1:Z100` or just `A1:Z100` if sheetName is set

### "Permission denied" / "PERMISSION_DENIED"
- Cause: OAuth2 scope missing `spreadsheets` or service account lacks share
- Fix: re-authorize with `https://www.googleapis.com/auth/spreadsheets` scope

### "Requested entity was not found"
- Cause: wrong documentId or spreadsheet was deleted/unshared
- Fix: verify the spreadsheet URL and sharing permissions

## Best practices
- For append: use `options.dataLocationOnSheet = headerRow` to auto-detect columns
- For read: set `range` to limit data fetched (performance)
- Row numbers in n8n are 1-indexed, matching Google Sheets convention
- For update: use `matchingColumns` to identify which row to update
- Date values: Google Sheets stores dates as serial numbers; use a Set node to format
