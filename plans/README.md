# Plans index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

| Doc | Status |
|---|---|
| [postgres-migration.md](postgres-migration.md) | Done — SOCI + PostgreSQL backend shipped (db-agnostic slices 0-6) |
| [multi-language-targets.md](multi-language-targets.md) | Scoped, not started — Python recommended as target #2 |
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | Scoped, not started — compliance profile for regulated deployments |
| [message-versioning.md](message-versioning.md) | Scoped, not started — stable wire field numbers + version handshake so mismatched-schema peers degrade instead of silently corrupting data |
| [crash-interrupt-recovery.md](crash-interrupt-recovery.md) | Done — atomic writes in `Util.util`, no registry/marker machinery needed |

## Backlog

Open items not yet big enough for their own scoping doc. Moved here from
`NEXT_SESSION.md`, which is a short-lived handoff note (what just happened,
what to check first) rather than a place to accumulate a durable backlog.
Add to this list piecemeal as items get scoped or come up — no need to do it
all at once.

- **Python as language #2** — see `multi-language-targets.md` for the scoped
  recommendation. Multi-session sized, don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no Doxygen generation, no
  multi-tier RBAC (single flat credential everywhere).
