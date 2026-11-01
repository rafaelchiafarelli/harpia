## C++ DAO: read_by_<field> for every `unique` field

- **Depends on:** the read-by-unique decisions in `../../README.md`;
  stable-hidden-names-DEFECT merged to `dev`.
- **Contract:** for each top-level, non-phi `unique` scalar field `f` of a
  table message, the generated C++ DAO gains
  `bool read_by_f(<f type> value, <Msg>* out)` — `SELECT ... WHERE f = :v`,
  the same row hydration as `read` (child tables included), audit as `read`
  when the message is phi-bearing. Returns false when no row matches.
- **Tests (kept):** `test_stage8_db.py::test_read_by_unique` (hit + miss,
  SQLite) + PG twin.
- **Golden move:** `UnitTests/golden/db/` for messages with `unique` fields.
- **Docs:** `Database/CLAUDE.md`, `USAGE.md` §7.
