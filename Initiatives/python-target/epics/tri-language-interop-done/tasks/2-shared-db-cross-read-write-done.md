## Shared database: C++, Java and Python DAOs on one SQLite file (+ Postgres opt-in)

- **Depends on:** `py-database` 2a–2c, `py-crypto-phi` task 4.
- **Contract:** one generated project (all three targets), one SQLite
  file:
  - every row written by one language's DAO reads back equal through the
    other two, for every table message;
  - **Java participates only for its documented scalar-column subset**
    (`JavaDatabase/CLAUDE.md`'s scoped-down schema): on messages with
    deferred columns, Java is skipped and the skip is asserted, not hidden;
  - phi columns C++↔Python over a shared `LocalKeyProvider` store (Java
    has no phi support);
  - a migration run by one language leaves a schema the others read
    correctly;
  - Postgres variant opt-in (`HARPIA_PG_DSN`).
- **Watch for:** the Java table for a message with deferred columns is
  **narrower** than C++'s. Create tables through C++/Python in this test,
  never through Java, or the comparison is invalid.
- **Tests:** `UnitTests/test_db_xlang3.py` (gated as task 1); the PG half
  is picked up by `Docker/run_pg_tests.sh`.
