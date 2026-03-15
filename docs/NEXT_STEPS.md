# NEXT STEPS (Priority)

## P0 — Safety/UX blockers ✅ DONE
1. ✅ Pending delete context (follow-up 'в корзину') — test_pending_delete_memory.py
2. ✅ Strict follow-up semantics for 'удали старые' (duplicates only) — test_duplicate_flow.py
   - Fixed: mojibake keywords in controller.py classify() (22 lines, FIND_DUPLICATES/CLEAN_DUPLICATES/DISK/BROWSE/ORGANIZE all broken)
   - Fixed: keep='newest' default for 'удали старые', keep='oldest' only for 'удали новые'
   - Fixed: validate_cleanup now accepts "No duplicates found" as success

## P1 — Cleanup quality ✅ DONE
3. ✅ Global trash per drive (E:\_TRASH) — already in agent_v3.py
   ✅ Restore from trash — tool_restore_from_trash + RESTORE_FROM_TRASH intent
   ✅ List trash — tool_list_trash + LIST_TRASH intent
   ✅ Purge with confirmation — tool_purge_trash + PURGE_TRASH 2-turn flow
4. ✅ Duplicate cleanup confirmation thresholds (20 files / 500 MB)
   — CLEAN_DUPLICATES_CONFIRM 2-turn flow, dry_run preview before real cleanup

## P2 — Reliability
5. Fix test_controller.py encoding deterministically
   — File has double-encoded UTF-8 (cp1252 bytes saved as UTF-8)
   — Classes use garbled names → pytest collects 0 tests
   — Fix: decode file with mojibake_to_utf8(), rewrite with UTF-8 BOM
6. Add acceptance test script (PASS/FAIL for key scenarios)

## Backlog
- State manager: store tool call results and support follow-up
- Policy layer: extend for more dangerous operations
- Validator: retry/rollback improvements
- Improve browser automation (wait_for_selector, stability)
- Advanced memory retrieval (RAG)
