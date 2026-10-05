# C++ DAO `list` / paginated `list` have no ORDER BY — DEFECT

**Status: scoped, not started.** Found 2026-10-04 while porting the DAOs to
Python (python-target `py-database/3`; decisions log item 16 in
`Initiatives/python-target/NEXT_SESSION.md`). The C++ code was not changed.
The Python DAO deliberately diverged: it orders by the primary key.

## What was found

`Database/templates/crudl.h.tmpl`:

- line ~73 (`list()`): `SELECT {select_cols} FROM "{table}"`
- line ~87 (`list(offset, limit)`): `SELECT {select_cols} FROM "{table}"
  LIMIT :lim OFFSET :off`

Neither has an `ORDER BY`. SQL guarantees no row order without one. SQLite
happens to return rowid (= integer pk) order, so tests pass; on **PostgreSQL**
row order follows physical heap order, which changes after UPDATEs / VACUUM —
so paging with `LIMIT/OFFSET` can **skip or duplicate rows** across pages.
Also C++ and Python now return different orders for the same PG table.

The Java DAO (`JavaDatabase/JavaCrudlAdapter.py:113`, `SELECT … FROM "<table>"`)
has the same shape — verify and include it if it pages the same way.

## Scope

One epic: **`stable-list-order`**. Changes generated SQL → **moves
`UnitTests/golden/` (and possibly `golden_java/`) bytes**; that is the
intended contract change of this initiative. See `epics/README.md`.
