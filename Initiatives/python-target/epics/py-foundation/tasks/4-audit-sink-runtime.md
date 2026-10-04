## `AuditSink` runtime (Python port of Foundation F3)

- **Depends on:** task 2.
- **Contract:** `harpia_runtime/compliance/audit_sink.py`, a port of
  `Compliance/runtime/harpia_audit_sink.h`. It provides:
  - an `AuditSink` ABC whose `record(operation: str, subject: str,
    detail: str = "") -> None` signature **structurally cannot carry a
    field value** (Rule 5);
  - `NoOpAuditSink`;
  - `default_audit_sink()`, a process-wide singleton. A generated
    constructor defaults its `audit_sink` parameter to this.

  Copied by the `python` backend whenever any later runtime needs it. A
  `Compliance/audit_common.py`-style path constant lives next to the
  source so callers don't hardcode the path.
- **Why here and not in a later epic:** serialization (2), crypto (3),
  transports (5), zmq (6), events (7) and dds (9) all record into it.
  Putting it in whichever came first would make that epic a hidden
  dependency of the others.
- **Out of scope:** any real (tamper-evident) sink. The C++ target has
  none either.
- **Tests:** unit tests (pure Python, always run). `record` keyword names
  match C++; `default_audit_sink()` is identical across calls; a
  subclass's recorded tuples are exactly what was passed; the file passes
  the task 3 gate.
