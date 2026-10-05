## DB-API 2.0 bind/extract runtime + dialect placeholder handling

- **Depends on:** `py-foundation` (all).
- **Contract:** `harpia_runtime/db/bind.py`.
  - `bind_value(msg, field_name)` returns the DB-API parameter for a
    scalar/enum field: int/float/str, enum as its int.
  - `extract_value(row_value, msg, field_name)` sets it back.
  - Both dispatch on `FieldDescriptor.cpp_type`. Python attribute names are
    the exact `.proto` names, so there is no accessor derivation (see
    `../../README.md` conventions).
  - **Placeholders are dialect-baked at generation time:** a generated DAO
    gets its SQL from `Database/backends` (the same `DbBackend` object
    `main.py` resolved once, shared with C++/Java). `sqlite3` uses `?`,
    `psycopg` uses `%s`.
- **Decision needed:** `DbBackend` has no placeholder method today. Options:
  - (a) add `DbBackend.param_placeholder()` (`?` for sqlite, `%s` for
    postgres). Additive; C++/Java ignore it.
  - (b) keep it inside the Python adapter as a name → placeholder map.

  Recommendation (a): the dialect knowledge then lives in one place.
  C++/Java goldens must stay byte-identical either way.
- **Out of scope:** DAO generation (task 2a).
- **Tests:** unit tests over an in-memory `sqlite3` connection for every
  scalar kind + enum. The placeholder chosen per backend is asserted.
