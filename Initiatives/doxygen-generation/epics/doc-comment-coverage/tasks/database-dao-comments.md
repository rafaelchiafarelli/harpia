## Database DAO doc comments

- **Depends on:** F6 (shipped).
- **Expected covered by, per sub-item — check each independently:**
  - `CrudlAdapter` (the `ID_*` pitfall below) — the db-encryption epic
    (`../../../../medical_devices/epics/db-encryption/`),
    whose `create()`/`update()` DAO wiring is exactly where this comment
    belongs.
  - `SqlAdapter`, `DbIoAdapter` — the db-encryption & db-segregation epics share `Database/`
    generator files
    (`../../../../medical_devices/epics/db-segregation/`).
  - `RestAdapter`, `SoapAdapter`, `GrpcServiceAdapter` — the transport-authn epic
    (`../../../../medical_devices/epics/transport-authn/README.md`),
    which touches "generated gate code" across all three transports.
  - `WsdlAdapter` — **no clearly expected owner among current
    medical_devices epics.** Flag this again if still true when picked
    up; do it here regardless.
- **Deliverable:**
  - `CrudlAdapter`'s `create()` doc comment carrying the `ID_*` pitfall:
    the primary key is caller-assigned, never DB-auto-generated
    (`../../../../doxygen-generation.md` §4 row, source: `USAGE.md` §11).
  - A baseline class-level doc comment (no specific pitfall row yet) on
    `SqlAdapter`, `GrpcServiceAdapter`, `DbIoAdapter`, `RestAdapter`,
    `SoapAdapter`, `WsdlAdapter` — what the class does and how a consumer
    is meant to call it.
  - If this session's own read of any of these six surfaces a real
    consumer-relevant pitfall (not just "no pitfall found yet"), add a row
    to `../../../../doxygen-generation.md` §4 in the same session
    (living-reference instruction).
- **Out of scope:** `ZmqAdapter` (task 6).
- **Tests:**
  - Golden snapshot: `CrudlAdapter.create()` comment text.
  - Presence check (non-empty, non-generic doc comment) for each of the
    other six adapters.
