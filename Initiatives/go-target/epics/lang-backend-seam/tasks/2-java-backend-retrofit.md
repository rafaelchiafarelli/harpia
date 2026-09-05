## `java` backend wrapping the existing Java pipeline, unmodified

- **Depends on:** task 1 (the registry shape to register into).
- **Deliverable:** a `java` backend that wraps `main.py`'s existing Java
  block verbatim — `GradleAdapter`, `JavaJsonAdapter`, `JavaDbAdapter`,
  `JavaCrudlAdapter`, `JavaXmlAdapter`, `JavaRestAdapter`, `JavaSoapAdapter`,
  `JavaZmqAdapter`, `JavaTestAdapter`, in their existing order, with their
  existing constructor arguments (`messages`, `dest`, `compliance`, and
  `backend=dbBackend` for `JavaCrudlAdapter`). No adapter's own code changes.
  The backend object receives `dbBackend` as a parameter (per
  `epics/README.md`'s "watch for" — it must not re-resolve it independently
  of the `cpp` backend's).
- **Out of scope:** switching `main.py`'s actual call site (task 3), any
  feature change to any `Java*` adapter.
- **Tests:** none new — this task's correctness is entirely proven by task
  3's regreen (nothing calls this backend until `main.py` is switched).
