## PostgreSQL via `psycopg`

- **Depends on:** task 2c.
- **Contract:** with `HARPIA_DB_BACKEND=postgresql`, the generated DAOs
  run unchanged against a `psycopg` connection. The dialect differences
  (`%s` placeholders, `BIGINT`/`DOUBLE PRECISION` types) come entirely from
  `DbBackend`, as with C++ (SOCI) and Java (JDBC). `pyproject.toml`
  declares `psycopg` as an optional extra (`[project.optional-dependencies]
  postgres`), so a SQLite-only consumer doesn't need libpq.
- **Out of scope:** pool behavior on Postgres (`py-transports-http`
  task 1).
- **Tests:** opt-in `UnitTests/test_python_db_postgres.py`, skipped unless
  `HARPIA_PG_DSN` is set (same posture as `test_stage8_pg.py`). It runs the
  CRUDL round-trips of 2a–2c against Postgres. `Docker/run_pg_tests.sh`
  picks it up with no change.
