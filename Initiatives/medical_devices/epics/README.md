# medical_devices — epics

Live status and execution order for the `medical_devices` initiative. The
frozen scoping docs are one level up (`../harpia_medical_master_plan.md`,
`../sensitive-data-implementation-roadmap.md`,
`../harpia_sensitive_data_design_rules.md`); this folder carries what is
actually being built, one epic per folder, one task per file under each
epic's `tasks/`.

Foundation (the `ComplianceContext` object, the `phi` field tag, the
`AuditSink` stub, the `CryptoBackend` seam, the regression baseline, the
Doxygen infrastructure) shipped first and was removed as its own epic —
`foundation-handoff.md` is the reference for what it left behind.

## Epics

| Epic | Scope | Status |
|---|---|---|
| [key-management](key-management/) | pluggable `KeyProvider`, envelope encryption, rotation, crypto-shredding | **done** |
| [schema-evolution](schema-evolution/) | child-table (map / repeated / repeated-composed) DB schema migration | **done** |
| [db-encryption](db-encryption/) | field-level encryption for `phi` columns + audit-on-access wiring | **done** |
| [db-segregation](db-segregation/) | public/private DB segregation, project-scoped access check | **done** |
| [critical-delivery](critical-delivery/) | `critical` message modifier + delivery-guarantee runtime + first transport wiring | **done** |
| [serialization](serialization/) | YAML adapter, unified `toString`, `phi` redaction + audited unredacted-output flag | **done** (tasks 1–5; `ComplianceReport/` note folded into `ComplianceReport/requirements.py` by the traceability-matrix task) |
| [zmq-lifecycle](zmq-lifecycle/) | ZMQ CURVE security (shipped, verify only) + full `stream[#]` lifecycle | not started |
| [transport-authn](transport-authn/) | mTLS transport (gRPC/REST/SOAP) + RBAC / AuthN / AuthZ | not started (scoping doc only) |
| [events-callbacks](events-callbacks/) | `event[cached/not-cached]`, detached-thread callback dispatch | not started |
| [process-artifacts](process-artifacts/) | SBOM, traceability matrix, jurisdiction-selected doc templates, `ComplianceReport/` module | **done** (`sbom-emission` → CycloneDX SBOM; `traceability-matrix` → `requirements.py` catalog + `traceability.{json,md}`, 3 `*-note.md` folded in; `jurisdiction-template-selection` → `compliance_report[.<jur>].md` shells, same evidence) |
| [static-fuzz-ci](static-fuzz-ci/) | static / fuzz analysis CI | not started (scoping doc only) |
| [versioning](versioning/) | versioning / git integration — folded into `process-artifacts`' `ComplianceReport/` output | not started (scoping doc only) |
| [dds-transport](dds-transport/) | DDS transport adapter (ASTM F2761 / OpenICE-class bedside bus) | **in progress** (tasks 1 + 2a + 2b done — `dds` modifier; Cyclone DDS 0.10.5 + `ddscxx` vendored + built in the Docker image; `DdsAdapter/` emits per-message publisher/subscriber with the §4 QoS mapping (`critical`→RELIABLE/KEEP_ALL, else BEST_EFFORT/KEEP_LAST(1)), build-verified demo shows the semantics differ under a transient gap. 3 (DDS-Security), 4 (`phi` audit over DDS), 5 (acceptance gate + note) open. `deadline[ms]` QoS carved out pending domain expert) |
| [sdc-biceps](sdc-biceps/) | IEEE 11073 SDC / BICEPS bindings (scoping + WS-Discovery responder only) | not started (scoping doc only) |
| [fhir-facade](fhir-facade/) | HL7 FHIR façade (design doc done; one worked example remaining) | not started (scoping doc only) |

## Execution order

```
critical-delivery: modifier -> delivery runtime -> ZMQ wiring -> send/receive test
                                                                       |
key-management  --+                                                     |
schema-evolution -+--> db-encryption --> db-segregation                 |
                                                                       |
serialization  (needs the phi field tag only, independent)             |
                                                                       v
                                    both headline integration tests green
```

- **key-management ∥ schema-evolution** share no files and have no
  functional dependency — run them as two separate session-lines from
  the start (schema-evolution needs nothing from Foundation).
- **db-encryption** cannot start until every task in *both*
  key-management and schema-evolution is merged.
- **db-segregation** starts immediately after db-encryption, on the same
  session-line — it shares the `Database/` generator files db-encryption
  just modified; don't hand it to a fresh session.
- **serialization** needs only the `phi` field tag; run it any time.
- **transport-authn before zmq-lifecycle**, same session-line — no file
  dependency, but transport-authn sets the credential / session model the
  rest of the comm layer should stay consistent with.
- **process-artifacts before versioning** — versioning was folded into
  process-artifacts' `ComplianceReport/` output; merge at least
  `process-artifacts`' first task before picking up versioning.
- **dds-transport -> sdc-biceps -> fhir-facade**, same session-line —
  no hard dependency, but each leans on the one before as a worked
  precedent for tying a new transport / vocabulary binding into the
  schema-level `phi` / `critical` modifiers.
- `project.harpia.yaml` (the checked-in repo-root compliance config)
  landed with **db-encryption** — the first code that branches on
  `ComplianceContext` values at generation time. Not earlier: adding it
  ahead of any consumer risks silent test interference.
- If one of key-management / schema-evolution finishes first, don't
  idle — pick up a no-dependency task from `process-artifacts` or
  `static-fuzz-ci` as filler.

## Definition of done

Applies to every task, every epic. Stricter than "nothing old broke".

1. **Unit tests** for the construct / behavior that task introduces —
   its own slice, not the whole epic's suite.
2. **Integration test** covering the end-to-end path for any task that
   closes one (an actual mTLS handshake + RBAC-gated request over the
   wire; an actual DDS publish/subscribe exchange under the specified
   QoS; a `critical` message surviving a simulated transport outage).
3. **The two headline sensitive-data integration tests:**
   - **`critical` send/receive** (critical-delivery, final task) — a
     `critical` message survives a simulated transient outage (held in
     the bounded queue, replayed in order on reconnect, rotation audited
     on overflow) while a non-`critical` message on the same path is
     allowed to drop.
   - **`phi` send/receive** (db-encryption's acceptance-gates task +
     serialization's round-trip task) — a `phi` field round-trips
     persist -> process restart -> read: decrypted value matches, a raw
     SQL query bypassing the DAO shows ciphertext, exactly one
     `AuditSink` record per DAO op touching the field; and
     `toString` / JSON / XML / YAML redact `phi` by default, the
     unredacted flag itself emitting an audit record.
4. **Full regression baseline still passes** — run the whole suite in
   Docker before every commit (invocation in `NEXT_SESSION.md`).
5. `UnitTests/test_golden.py` (+ `test_golden_java.py`) regenerated and
   the diff reviewed for any task that moves generated output.
6. A one-paragraph traceability note into `ComplianceReport/` for any
   work touching `phi`-adjacent code — filed as a **process-artifacts**
   task, since `ComplianceReport/` is that epic's module.
7. **Doxygen doc-comments** (Ground Rule 6): any task that touches a
   consumer-facing template / adapter emits or updates accurate
   Doxygen-syntax doc-comments for what it touched, in the same session —
   not deferred. Add a row to
   `../../doxygen-generation/doxygen-generation.md` §4 if the work
   surfaces a pitfall not already listed.

## Watch for

- **`.harpia` comments are lexed like code.** Backtick, apostrophe, `:`,
  `!`, `?`, `#`, `@`, `%`, `^`, `~` all hit `MISMATCH` and hard-error the
  whole file *even inside a `//` comment*. Stick to letters / digits /
  `. , ( ) { } [ ] ; = < > + - * /` and spaces.
- A new `phi` / `critical` fixture goes in `HarpiaTest/Include/*.harpia`,
  not `test.harpia` — only the root file's text feeds the pinned `HASH`
  constants in `UnitTests/*.py`, so an Include-file edit moves golden
  *content* for the touched messages but leaves every `HASH = "…"` alone.
  Regenerate (`HARPIA_UPDATE_GOLDEN=1`) and review.
- `patient_vitals` (mixed `phi`) and `alarm_event` (`critical` +
  `phi` field) already live in `HarpiaTest/Include/file3.harpia` —
  extend those rather than forking parallel fixtures.
- The delivery runtime is **not thread-safe** (caller-synchronized, same
  contract as `harpia_capability_dispatch.h`). A background flush thread
  is a future decision, not assumed.
- transport-authn's session / login mechanism did not exist when the
  capability handshake was built — `HttpCapabilityAdapter` has a
  standalone mechanism that could later be reconciled with a real
  session model (opportunity, not obligation).
