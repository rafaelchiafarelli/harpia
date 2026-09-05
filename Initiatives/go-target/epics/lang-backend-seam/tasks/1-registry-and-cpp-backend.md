## LangBackend registry + a `cpp` backend wrapping the existing pipeline

- **Depends on:** nothing.
- **Deliverable:**
  - A `LangBackend` registry mirroring `Database/backends`'s shape (a
    `get_lang_backend(name)` returning an object with a uniform entry
    point — read `Database/backends/__init__.py`'s `get_backend` pattern
    before designing this, match its "explicit name / alias resolution /
    unknown-name hard error" shape, `Database.backends.get_backend`'s own
    `CLAUDE.md`-documented contract).
  - A `cpp` backend registered as the **default** (`HARPIA_GEN_LANG` unset
    or `"cpp"`) that wraps `main.py`'s existing, unconditional pipeline
    (stages 6/7/9/10/11/12/13/14 etc. — everything that runs today
    regardless of `HARPIA_GEN_LANG`) with **zero behavior change**.
  - `main.py` itself is NOT yet switched to call through the registry in
    this task — that's task 3, after `java` also exists as a backend (task
    2), so the switch happens once, atomically, rather than twice.
- **Out of scope:** the `java` backend (task 2), touching `main.py`'s actual
  call sites (task 3).
- **Tests:** no behavior to test yet at the `main.py` level (nothing calls
  this new registry yet) — cover the registry itself directly (name
  resolution, unknown-name error, `cpp` resolves to the right object) with a
  small pure-Python unit test, same shape as `Database.backends.get_backend`'s
  own tests.
