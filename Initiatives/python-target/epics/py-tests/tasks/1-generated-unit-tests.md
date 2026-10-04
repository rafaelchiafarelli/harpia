## Generated per-message Python unit tests (field access, serialization, CRUDL)

- **Depends on:** `py-serialization` (all), `py-database` tasks 2a–2c.
- **Contract:** a `PyTestAdapter` emits
  `<dest>/python/tests/test_<name>_<hash>.py` per table-bearing message
  (pytest). It builds a `sample()` with every column set to deterministic
  values, using the same value rules as `TestAdapter._value`, with
  variants a/b. Checks:
  - every field survives set → get;
  - JSON/XML/YAML round-trips;
  - `to_string` round-trip for non-phi messages;
  - a DB CRUDL round-trip on a temp-file SQLite. That uses a direct
    connection, not a pool, because the pool refuses `:memory:`.
  - **Full** columns, including embed/FK/map/repeated, since the Python DAO
    has full coverage (unlike Java's scoped tests).

  `pyproject.toml` declares `pytest` as a test extra.
- **Out of scope:** REST/SOAP/access/app-level bodies (task 2).
- **Tests:** `UnitTests/test_python_generated_tests.py` generates the
  fixture project and runs its emitted suite with pytest (all pass). A
  structural check that one test module exists per table message. Golden
  snapshot of the emitted tests.
