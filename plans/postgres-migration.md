# Harpia Stage 8 Persistence: DB-agnostic via SOCI (SQLite kept, PostgreSQL added)

> Planning doc.
>
> A raw `libpq`-direct retarget (rewriting the generated DAO onto
> `PQexecParams`) was considered and rejected: it drops SQLite entirely (not
> agnostic), loses the hermetic in-memory test model, and requires a
> `PQexecParams` param-lifetime rewrite. Generating against SOCI instead avoids
> all three, so that's the strategy below.

## 1. Summary

Retarget Stage 8 from "hard-wired vendored SQLite" to a **`DbBackend` dialect
seam + a SOCI-based DAO**, so one generated codebase runs on SQLite *and*
PostgreSQL (and later MySQL). SOCI (`soci::session`, `use()`/`into()`/`rowset`,
`:name` placeholders) unifies the client API across backends, so the entire
INSERT/SELECT/UPDATE/DELETE + binding surface becomes **one dialect-free
template**. The only things that stay per-backend are the SQL dialect (types,
PK, CREATE/DROP, child tables), the migration introspection (`pragma_table_info`
vs `information_schema`), the version-stamp upsert, and the single
session-open site (SOCI backend factory + header). Input `.harpia` is unchanged,
so all `md5Hash`-qualified filenames/guards and the 6 pinned `HASH` constants are
unaffected.

Two findings (confirmed by reading the code) that shrink the work:
- **No `AUTOINCREMENT` today.** `Database/model.py:56-58` renders the PK as plain
  `"<type> PRIMARY KEY"` and the id (`ID_<hash>`) is **caller-assigned** — tests
  do `a.set_<pk>(1)` and bind it on INSERT. So there is no DB-generated-id
  semantics to preserve: the hardest portability problem (`RETURNING` vs
  `last_insert_rowid`) is **not active** and does not block the port. Postgres PK
  stays a plain `BIGINT PRIMARY KEY`, not `SERIAL`/`IDENTITY`.
- **SOCI absorbs the C-API divergence.** The whole "prepare → bind → step →
  finalize" (SQLite) vs "paramValues[] → PQexecParams → PQgetvalue" (libpq) split
  that would have dominated a raw libpq port collapses into uniform SOCI calls —
  it is no longer a per-backend concern at all.

## 2. The seam (DONE — eyeball first)

`Database/backends/` (new package, imported by nothing yet, so harpia stays green
on SQLite while the abstraction is reviewed):
- `base.py` — `DbBackend` ABC. Methods cover the *entire* per-backend surface:
  `sql_type(token)`, `int_type`, `column_def(...)`, `create_table`, `drop_table`,
  `map_child_table`, `rep_child_table`, `version_table`, `list_columns_sql`,
  `add_column`, `stamp_version`, plus the session-open metadata
  (`soci_backend`, `soci_backend_symbol`, `soci_backend_header`). No harpia deps
  (never imports `model`) → unit-testable in isolation; `model.py` depends on it,
  one direction.
- `sqlite.py` — `SqliteBackend`, reproduces today's SQL **verbatim** (parity is
  the acceptance test). Two documented, behaviour-equivalent deltas:
  `list_columns_sql` uses `pragma_table_info()` (table-valued, SELECTs a single
  `"name"` column — same shape as the PG query); child-table DDL uses
  `PRIMARY KEY("owner","key")` (no space), matching CrudlAdapter's one-liners.
- `__init__.py` — `get_backend(name)` registry (default `"sqlite"`), `register()`
  for later backends. Run `python3 -m Database.backends.sqlite` to print sample
  DDL.

## 3. SQL dialect delta (the only per-backend surface left)

| Concern | SQLite (`sqlite.py`) | PostgreSQL (`postgres.py`, to write) |
|---|---|---|
| Integer type | `INTEGER` | `BIGINT` |
| Float type | `REAL` | `DOUBLE PRECISION` |
| Text type | `TEXT` | `TEXT` (unchanged) |
| Primary key | `INTEGER PRIMARY KEY` (caller-assigned) | `BIGINT PRIMARY KEY` — **not** `SERIAL`/`IDENTITY` |
| Placeholders | SOCI `:name` (uniform — **not** a dialect concern) | SOCI `:name` |
| CREATE/DROP `IF [NOT] EXISTS` | supported | supported |
| Quoted identifiers | `"x"` | `"x"` (quoting preserves case; already everywhere) |
| List columns | `SELECT "name" FROM pragma_table_info('t')` | `SELECT column_name FROM information_schema.columns WHERE table_name='t' AND table_schema=current_schema()` |
| Version upsert | `INSERT OR REPLACE INTO …` | `INSERT … ON CONFLICT ("name") DO UPDATE SET "version"=EXCLUDED."version"` |
| Bool | `INTEGER`, kind `int` (0/1) | `BIGINT`, kind `int` (0/1) |
| Session open | `soci::session s(soci::sqlite3, path)` | `soci::session s(soci::postgresql, conninfo)` |

## 4. Files to change (per phase)

Neutral (delegate to the DAO, only the connection *type* touches them):
`rest.h.tmpl`, `soap.h.tmpl`, `grpc_service.h.tmpl`, `TestAdapter.py`, Assets demo
— all switch `::sqlite3*` → `::soci::session&` and `#include "sqlite3.h"` →
`<soci/soci.h>`; the SOCI *backend* header/symbol appears only where a session is
opened. `RestAdapter.py`/`SoapAdapter.py`/`GrpcServiceAdapter.py`/`DbIoAdapter.py`
need no Python change. Untouched entirely: front-end, JSON/XML/WSDL/proto/gRPC-
compiler, `dbio.h.tmpl`, `json/`, `xml/`, `proto/`, `wsdl/`, `zmq/`, `tokens.txt`,
`messages.txt`.

- **`model.py`** — `_SCALARS` split: keep the neutral `kind` map here; move the
  SQL type to `backend.sql_type(token)`. `Column` stores the token/kind; `sql_def`
  becomes `backend.column_def(...)`. `create_table_sql`, `MapField`/`RepeatedField`
  `*_sql`/`owner_sql` → dialect. `getter`/`set_stmt`/`entries`/`add_stmt` (protobuf
  accessors) stay — DB-neutral.
- **`SqlAdapter.py`** — consume `backend.create_table` / `map_child_table` /
  `rep_child_table`. (Adopt the canonical one-line child DDL → one-space golden
  diff, or keep pretty formatting and take only the type text from the dialect.)
- **`CrudlAdapter.py` + `crudl.h.tmpl`** — the big one, but smaller than a
  libpq-direct port would have been. `_bind_line`/`_extract_line`/`_bind_scalar`/`_col_decl` and the map/repeated
  write/read/remove builders (26-73, 241-438) → SOCI `use()`/`into()`/`rowset`
  (uniform, dialect-free). DDL strings come from the backend. `_fk_bind`/
  `_fk_extract` → SOCI. Ctor `::sqlite3* db` → `::soci::session& db`.
- **`MigrationAdapter.py` + `migrate.h.tmpl`** — introspection via
  `backend.list_columns_sql` read with a SOCI `rowset<row>` (first column =
  name); `add_column`/`stamp_version`/`version_table` from the backend; ctor →
  `soci::session&`.

## 5. Test-infrastructure — SOCI *keeps* the hermetic model

The generated unit tests keep using **SQLite in-memory** — through SOCI
(`soci::session s(soci::sqlite3, ":memory:")`) — so they stay hermetic,
zero-setup and parallel-`ctest` safe, exactly as today. No live Postgres server
is needed for the unit suite. Postgres is exercised by a **separate opt-in
integration target** against a real server (docker-compose or an embedded
cluster with a unique schema per test). This is the key advantage of Route B:
the hermetic property a raw libpq port would have broken is preserved.
Vendoring changes: add **SOCI core + the sqlite3 and postgresql
backends** (+ `libpq` for the PG backend) to the toolchain image and the
generated CMake; SQLite stays vendored (SOCI's sqlite3 backend links it).

## 6. Portability impact — stated plainly

Generated output stops being *fully* self-contained: it now depends on **SOCI**
(vendorable) and, *only when the PostgreSQL backend is used at runtime*, on
`libpq` + a running server. But because tests and the SQLite backend need no
server, "clone and `cmake && ctest` on any box" **still works** on the SQLite
backend — the hermetic story survives for anyone not opting into Postgres. This
is a materially smaller portability hit than a full SQLite-replacement plan
would have been.

## 7. Bonus enabled: per-table backend

Because backend selection is resolved per message, the `.harpia` directive can be
**per-table**: one generated project can put embedded/realtime tables on SQLite
and a shared library (e.g. conboard's portable rules DB) on PostgreSQL. A
libpq-direct port could not do this without `#ifdef` sprawl.

## 8. Branch/slice plan (each leaves harpia green on SQLite)

0. **`harpia-db-seam`** — `Database/backends/` (base + sqlite + registry). ✅ DONE.
1. **`harpia-soci-vendor`** — vendor SOCI (core + sqlite3 backend) into the image
   + generated CMake; prove a hello-SOCI links. No codegen change.
2. **`harpia-db-dialect`** — `model.py` (kind/type split) + `SqlAdapter` onto the
   seam. Regenerate `db/*_table.sql`. Parity (± documented deltas).
3. **`harpia-soci-crudl`** — `CrudlAdapter` + `crudl.h.tmpl` → SOCI (scalar/FK/
   map/repeated), still SQLite backend. Regenerate `db/*_crudl.h`. CRUDL round-
   trip tests pass over SOCI-sqlite.
4. **`harpia-soci-migrate`** — `MigrationAdapter` + `migrate.h.tmpl` via the
   dialect. Regenerate `migrate/`.
5. **`harpia-soci-services`** — thread `soci::session` through rest/soap/grpc
   templates + TestAdapter + Assets demo. Regenerate `rest/`,`soap/`,`grpc/`,
   `gen_tests/`. Live REST/SOAP/gRPC round-trips pass.
6. **`harpia-pg-backend`** — `backends/postgres.py` + backend selection
   (`.harpia` directive + `HARPIA_DB_BACKEND`) threaded through `main.py`; SOCI
   postgresql backend + `libpq` vendored; opt-in PG integration test
   (docker-compose). Generate against PG; CRUDL + REST round-trips on real PG.
7. **(opt) `harpia-db-per-table`** — per-table backend selection.
8. **`harpia-db-docs`** — `Database/CLAUDE.md` + `TestAdapter/CLAUDE.md`.

## 9. Golden strategy

Input `.harpia` unchanged → every `md5Hash` and the 6 pinned `HASH` constants are
stable. Regenerate per slice with `HARPIA_UPDATE_GOLDEN=1 pytest tests/test_golden.py`
so each commit's diff is scoped: `db/**` (dialect + SOCI DAO), `migrate/**`,
`rest/`/`soap/`/`grpc/**` (ctor type), `gen_tests/**`. Unaffected: `json/`, `xml/`,
`proto/`, `wsdl/`, `zmq/`, `dbio/`, `tokens.txt`, `messages.txt` — drift there
signals an accidental change.
