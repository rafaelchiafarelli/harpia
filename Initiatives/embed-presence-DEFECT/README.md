# An unset embedded message field reads back present — DEFECT

**Status: scoped, decisions taken 2026-11-01, not started.** Found
2026-11-01 while closing `harpia-handoff.md` item 2 (mocap-contracts: "an
unset optional field (scalar or nested)").

## What was found

A composed field whose target has no table (`data.val`, a `prince`) is
stored as flat columns (`val_vari`, `val_var`, `val_val`) with no column for
the embed itself. Writing a message with `val` unset binds the embed's
non-optional sub-fields as `0` / `""`; reading sets them through
`msg->mutable_val()->…` (C++) / `SetInParent()` (Python), which makes `val`
present. `read(create(m)) != m` for any `m` that leaves an embed unset.

## Decision (Rafael, 2026-11-01): option B, a hidden presence column

- One hidden column per embedded message field, at every nesting level:
  `HARPIA_HAS_<embed column prefix>` (`HARPIA_HAS_val`,
  `HARPIA_HAS_val_inner`), INTEGER, `1` present / `0` absent. The `HARPIA_`
  prefix is already reserved, so no user field can collide and every
  hidden-field recogniser skips it.
- Rejected option A (all embed columns NULL ⇒ absent): ambiguous for an
  embed of only `optional` fields (present-but-empty), and impossible for an
  embed with no scalar columns. B is also filterable in SQL.
- **Pre-change rows:** the migration adds the column as NULL; NULL reads as
  *present* (today's behaviour), so nothing reads differently after upgrade.
- On write, an absent embed binds `0` and its sub-columns as NULL; on read,
  `0` leaves the embed (and everything under it) unset.
- Java: no change (Java doesn't persist embedded fields).

## Scope

One epic, **`embed-presence`** — see `epics/README.md`.
