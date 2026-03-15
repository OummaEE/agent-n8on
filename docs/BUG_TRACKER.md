# BUG TRACKER

## FIXED
### B1 — 'удали старые' deleted oldest random file (WRONG)
- Symptom: user said 'удали старые' and agent deleted oldest file in folder.
- Root cause: follow-up semantics missing; treated as general cleanup by date.
- Fix: policy + controller changes to only treat as duplicates follow-up when scan exists (pending).

### B2 — 'удали дубликаты' scanned C:\Users instead of target folder (CATASTROPHIC)
- Symptom: after scanning E:\Alexander, 'удали дубликаты' scanned entire home and found 245k groups.
- Root cause: folder context loss / unsafe default folder.
- Fix: enforce folder scoping; require explicit folder or last_scanned_folder.

### B3 — delete_files blocked inside allowed folder
- Symptom: 'Blocked (outside allowed folders)' even for E:\Alexander\file.txt.
- Root cause: allowed_folder not passed into delete_files/clean_duplicates.
- Fix: inject allowed_folder with precedence requested_folder > last_scanned_folder; add path normalization tests.

## OPEN
### O1 — Pending delete context for follow-ups
- Symptom: user requests delete, gets permanent-confirm prompt; follow-up 'в корзину' loses file/folder context.
- Plan: store pending_delete in controller state (TTL 5 min) and resolve follow-ups.

### O2 — Global trash per drive
- Current: _trash inside each folder.
- Desired: E:\_TRASH\... preserving relative path.

### O3 — test_controller.py encoding issues
- Symptom: mojibake / Unicode errors in console.
- Plan: normalize UTF-8, remove problematic symbols, set encoding in test harness.

