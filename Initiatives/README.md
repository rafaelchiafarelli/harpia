# Initiatives index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

## How to work an `epics/` folder — READ THIS FIRST

The full process — the Initiative → Epic → Task → Contract hierarchy, the
matching branch hierarchy, the per-task implementation loop, and the
stop-and-flag rules — lives in the **`harpia-workflow` skill**
(`.claude/skills/harpia-workflow/SKILL.md`). Read it first. The
repo-specific points that skill doesn't cover:

- **Layout.** `initiatives/<initiative>/epics/<epic>/tasks/<n>-<task>.md`.
  Task files carry a numeric prefix restarting at `1` per epic — that
  number is the implementation order and the branch name. The done marker
  is a `-done` **filename** suffix (`git mv` at land time), never a
  `**Status:**` line inside the file. Cross-epic execution order lives in
  each initiative's `epics/README.md`.
- **Branches.** `feature/medical_devices/<epic>/<n>-<task>` off `dev`, one
  branch per task, merged `--no-ff` back into `dev` a task at a time, then
  `git push origin dev`. When tasks genuinely build on each other, branch
  the next off the previous task's branch (so the code is present) but
  still merge one at a time. Never merge or push `main`.
- **The plan docs must agree with this workflow.** `medical_devices/
  harpia_medical_master_plan.md`, `sensitive-data-implementation-roadmap.md`,
  and `harpia_sensitive_data_design_rules.md` are the frozen scoping
  reference — don't edit them to record progress (status lives in
  `epics/`) — but they use the same Initiative/Epic/Task vocabulary as
  the skill, and are kept in sync with it if the skill changes.
- **Per task, in order:** implement → regenerate goldens
  (`HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest UnitTests/test_golden.py
  UnitTests/test_golden_java.py`) and **review the diff** → full suite
  green in Docker (invocation in whatever `NEXT_SESSION.md` exists) →
  commit the implementation → `git mv` the task file to its `-done` name
  in a second commit on the same branch → merge `--no-ff` into `dev` →
  push → branch the next task off `dev`. Land additive where possible (no
  generator change, no golden movement) unless the task says otherwise.
- **A new `phi`/`critical` fixture goes in `HarpiaTest/Include/*.harpia`,
  not `test.harpia`** — only the root file's text feeds the pinned `HASH`
  constants in `UnitTests/*.py`, so an Include-file edit moves golden
  *content* for the touched messages but leaves every `HASH = "…"` alone.
  `.harpia` comments are lexed like code: letters/digits/spaces and
  `. , ( ) { } [ ] ; = < > + - * /` only — a `:` / `'` / `"` / `_` /
  backtick anywhere in a `//` comment hard-errors the whole file.

| Doc | Status |
|---|---|
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | **In progress.** Foundation F1–F6 shipped (plumbing stubs, merged to `dev`, epic removed — see `epics/foundation-handoff.md`). Sensitive-data behavior (`phi` + `critical`) built on `dev` via one branch per task, merged in slices. **Done: critical-delivery** — the `critical` delivery-guarantee axis the master plan assumed already existed (modifier + `harpia_delivery.h` runtime + `ZmqAdapter` wiring + a real-socket send/receive integration test). **Done: key-management** (`KeyProvider`, KEK/DEK envelope, rotation, crypto-shred, zeroize + audit, KMS reference adapter). **Done: schema-evolution** — repeated-scalar / map / repeated-composed child-table migration in `migrate_<table>()`. **Done: db-encryption** — `phi` columns envelope-encrypted on the DAO write path / decrypted on read via `KeyProvider` (`Crypto/runtime/harpia_encrypted_column.h`, `CrudlAdapter`), one `AuditSink.record()` per `phi` CRUDL op, `project.harpia.yaml` at the repo root, KEK-rotation + backend-swap proofs closed. **Done: db-segregation** — `Database/DbRegistryAdapter.py` emits one project-wide `generated/cpp/db/harpia_db_registry.h`: a `constexpr` registry of every table tagged PUBLIC/PRIVATE with an owner project name (`project.harpia.yaml` → `project:`, new `ComplianceContext.project`), plus `db_access_check()` refusing a PRIVATE table cross-project while keeping PUBLIC ones reachable; purely additive. All merged to `dev` (through `44ceec7`, 2026-08-27). **In progress: serialization** — tasks 1–3 `-done` (new `YamlAdapter/`; new `SerializeAdapter/` — one `harpia::serialize::to_string(msg, Format)` façade over the three unchanged engines, JSON/XML byte-identical; uniform `phi` redaction to `[REDACTED]` by default in all three formats via `harpia_redaction.h` + generated `harpia_phi_registry.h`, fully-`phi` fixture `lab_result`, non-`phi` output unchanged); `audited-unredacted-flag` next, then `full-round-trip-and-note`. The [roadmap](medical_devices/sensitive-data-implementation-roadmap.md) is the frozen plan; `epics/` carries live status. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** The fixture cleanup (`pope`/`king`/`queenBee` folded into `queen`) shipped 2026-08-24 (`f247b6c`). The `worked-examples` epic — one small runnable example per generated feature (gRPC, SOAP, XML, ZMQ, capability negotiation, credential-gated access) + an index — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | **Folded into Foundation's F6 + Ground Rule 6, 2026-08-23** — shipped and merged to `dev` (the Foundation epic was then removed, see `medical_devices/epics/foundation-handoff.md`); no longer a deferred epic. This file lives on as a living pitfall-table reference every epic appends to as it builds. Not medical-devices-specific despite living in that plan's Foundation — the rule applies repo-wide. The `doc-comment-coverage` epic is the fallback owner for doc-comments no other epic lands opportunistically. |

Finished plans are removed from this index once done — the shipped
behavior is documented in the code's own `CLAUDE.md`/architecture docs,
not preserved here. (Postgres backend and crash/interrupt recovery were
both here; both shipped and are now covered by `Database/CLAUDE.md` /
`Util/CLAUDE.md` respectively — crash/interrupt recovery's
content-compared atomic-write mechanism, see `Util/CLAUDE.md`.
`message-versioning.md` — stable wire field numbers, JSON/XML
parse-boundary hardening, and a capability handshake across all four
transports — shipped 2026-08-22/23 and was removed 2026-08-23; its
design rationale is now distributed across `Message/CLAUDE.md`,
`Capability/CLAUDE.md`, and the three `*CapabilityAdapter/CLAUDE.md`
files it fed. The one unrelated finding it surfaced — a `third_party/asio`
vendoring gap — wasn't part of the plan and was resolved 2026-08-23 by
re-vendoring the missing headers (see `HttpCapabilityAdapter/CLAUDE.md`).
`multi-language-targets/`
(Java as a full generation target, symmetric with C++, plus the
motivating on-device Android consumption verification) shipped in full —
all 27 of its tasks — 2026-08-25 and was removed the same day; its design rationale
is now distributed across `GradleAdapter/CLAUDE.md` (build-time codegen
decision), `JavaJsonAdapter/CLAUDE.md`/`JavaXmlAdapter/CLAUDE.md` (full
protobuf runtime vs. `javalite` decision), `JavaZmqAdapter/CLAUDE.md`
(JeroMQ/CURVE), `Database/CLAUDE.md` (why a cross-language `DbBackend`
seam is still deliberately undesigned), and
`HarpiaTest/app_example/android_consumer/README.md` (the Android verification account,
including the one real ART-incompatibility bug it found).)

## Backlog

Open items not yet big enough for their own scoping doc. Add to this list
piecemeal as items get scoped or come up — no need to do it all at once.

- **Python as language #3** (after Java, which shipped 2026-08-25 — see
  the "Finished plans" note above). Selection history: Python was the
  original per-stage-cost recommendation (2026-08-11), but a concrete
  business need — an existing Android fleet wanting harpia-generated Java
  code — overrode that in a 2026-08-22 addendum; Python was never
  dropped, just deferred. Also note (`Database/CLAUDE.md`): a
  cross-language `DbBackend`-style seam was deliberately left undesigned
  after Java, the same way `Database/backends/`'s own dialect seam waited
  for Postgres as a second case — Python would be the third language data
  point, likely the trigger to finally design one. Multi-session sized,
  don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no multi-tier RBAC (single
  flat credential everywhere).
