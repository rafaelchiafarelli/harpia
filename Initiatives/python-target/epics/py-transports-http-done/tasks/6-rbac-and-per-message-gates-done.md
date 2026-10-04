## RBAC (admin/main/guest) + per-message `protected`/`open` gates on REST/SOAP/gRPC

- **Depends on:** task 5; `py-foundation` task 4.
- **Contract:**
  - `harpia_runtime/rbac.py`, a port of `Compliance/runtime/harpia_rbac.h`:
    - `Role`, `Operation`, and the fixed `permitted()` matrix
      (admin = all; main = all but remove; guest = read/list/stream;
      heartBeat open);
    - `RoleMap.from_env()`, which reads `HARPIA_RBAC_MAP` once at startup
      in the **same file format** as C++;
    - `decide(cn, op, subject, sink) -> Decision`, recording one value-free
      `rbac_denied` per non-allow.
  - Each generated route/servicer picks its gate per message with
    `Database.auth_gate.effective_rbac(msg, hardening_required)` (reused by
    import, not re-implemented):
    - flat gate (tasks 2–4) or RBAC gate on the verified CN;
    - no identity → 401 / `UNAUTHENTICATED`; wrong role → 403 /
      `PERMISSION_DENIED`;
    - SOAP's check runs after the operation is parsed.
- **Thread-safety note (C++ db-concurrency 1b audits the same thing):**
  `RoleMap` is read-only after load. State that in the docstring.
- **Bar:** for the same RBAC map file and certs, the Python and C++
  servers return identical decisions for every (role, op).
- **Out of scope:** sessions (task 7).
- **Tests:** generated-project tests mirroring `test_rbac.py`'s matrix
  over all three transports; mixed `protected`/`open` fixture
  (`test_protected_open_modifiers.py` shape); one `rbac_denied` audit per
  denial with no value.
