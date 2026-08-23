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
| [multi-language-targets.md](multi-language-targets.md) | Scoped, not started — Python recommended as target #2 *in the abstract*; superseded in practice by `java-target.md`, see its §8 addendum |
| [java-target.md](java-target.md) | Scoped, not started — Java picked ahead of Python for a concrete reason (existing Android fleet); full symmetric target, Android is the consumer of a subset (see its §7) |
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | Scoped, not started — compliance profile for regulated deployments |
| [message-versioning.md](message-versioning.md) | **Shipped 2026-08-22/23** — stable wire field numbers, JSON/XML parse-boundary hardening, and a capability handshake across all four transports (gRPC/REST/SOAP/ZMQ) so mismatched-schema peers degrade instead of silently corrupting data. Kept here (not yet moved to "finished") pending its own two open questions (§9) and an unrelated `third_party/asio` vendoring gap the work surfaced (see the doc's §13) |
| [doxygen-generation.md](doxygen-generation.md) | Scoped, not started — per-message/per-field usage docs and pitfalls emitted into the generated headers, not just cosmetic comments |

Finished plans are removed from this index once done — the shipped
behavior is documented in the code's own `CLAUDE.md`/architecture docs,
not preserved here. (Postgres backend and crash/interrupt recovery were
both here; both shipped and are now covered by `Database/CLAUDE.md` /
`util/CLAUDE.md` and `harpia.architecture.md` respectively.)

## Backlog

Open items not yet big enough for their own scoping doc. Moved here from
`NEXT_SESSION.md`, which is a short-lived handoff note (what just happened,
what to check first) rather than a place to accumulate a durable backlog.
Add to this list piecemeal as items get scoped or come up — no need to do it
all at once.

- **Python as language #2** — see `multi-language-targets.md` for the scoped
  recommendation. Multi-session sized, don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no multi-tier RBAC (single
  flat credential everywhere).
