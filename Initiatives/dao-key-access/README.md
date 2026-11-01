# DAO key access: read by a `unique` field, DB-assigned primary key

**Status: scoped, not started.** Requested 2026-10-31 by `mocap-contracts`
(`harpia-handoff.md` item 3, "nice to have"); Rafael accepted both.

- Today a DAO reads only by the integer primary key (`HARPIA_ID` after
  stable-hidden-names-DEFECT). Records are often found by a `unique` field
  (mocap: a `unique string id`), which costs the consumer hand-written SQL on
  Harpia's tables.
- The primary key is caller-assigned (`USAGE.md` §16), so every insert costs a
  `max(key) + 1` round trip.

## Scope

Two independent epics — see `epics/README.md`:

- **`read-by-unique`** — generated `read_by_<field>(value, out)` for every
  `unique` field, C++ / Python / Java.
- **`db-assigned-key`** — an explicit `.harpia` opt-in for the database to
  assign the key; task 1 is the DSL design decision (never inferred).

Sequenced after the two blocker DEFECTs (stable-hidden-names,
db-optional-presence), so the DAO code it touches is settled.
