## C++: database-assigned key

- **Depends on:** task 1 (modifier + semantics), stable-hidden-names-DEFECT.
- **Contract:** per task 1's decision — for an opted-in table, the C++ DAO's
  `create` omits `HARPIA_ID` on INSERT, reads the assigned key back
  (`last_insert_rowid` / `RETURNING`) into the message; SQL DDL + migration
  per backend (SQLite `INTEGER PRIMARY KEY`, PG identity).
- **Tests (kept):** `test_stage8_db.py::test_db_assigned_key` + PG twin; a
  lexer test for the modifier.
- **Golden move:** an opted-in fixture message in `HarpiaTest/Include/`.
- **Docs:** `Database/CLAUDE.md`, `USAGE.md` §3 / §16.
