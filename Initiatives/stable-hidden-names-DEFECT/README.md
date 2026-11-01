# Hidden field names carry the root-file hash, so a root edit breaks every database — DEFECT

**Status: scoped, not started.** Reported 2026-10-31 by `mocap-contracts`
(V5, Python target, SQLite), `harpia-handoff.md` item 1 — their `v0.8.0` waits
on it.

## What was found

`Message/Variables.py` names the front-end-injected fields `ID_<md5>`,
`STATUS_<md5>`, `ERROR_<md5>` and (one-to-many messages) `ORIGINATOR_<md5>`,
where `<md5>` is the hash of the **root** `.harpia` file's text. Any root edit
(e.g. adding an `import` line) renames every table's primary key column. The
next `migrate_<name>(conn)` on a database made by the previous generation then
tries to drop the old key column and add an empty new one:

```
sqlite3.OperationalError: cannot drop PRIMARY KEY column: "ID_cb110dd8..."
```

It rolls back (no rows lost) but the new code can't open the database, and if
the drop had worked the key values would be gone.

## Decision (Rafael, 2026-10-31)

Hidden fields get **fixed, hash-free names** in every language:
`HARPIA_ID`, `HARPIA_STATUS`, `HARPIA_ERROR`, `HARPIA_ORIGINATOR` (one-to-many
included). Plain `ID` / `ID_` was rejected: protoc forbids it next to a user
field `id` ("JSON camel-case name ... conflicts", proto3), and `id` is the most
common user field. A user field whose name collides with a hidden one is a
parse-time error. Filenames keep the hash (that is what keeps two roots'
outputs apart); only field/column names change.

Databases made by earlier generations hold `ID_<hash>` etc.; `migrate_<name>`
renames them (`ALTER TABLE ... RENAME COLUMN` works on a primary key column in
SQLite and PG), the way `renamed_from` does for declared fields.

## Scope

One epic, **`fixed-hidden-names`** — see `epics/README.md`.
