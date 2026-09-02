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
| [zmq-lifecycle](zmq-lifecycle-done/) | ZMQ CURVE security (shipped, verify only) + full `stream` lifecycle | **all 3 tasks done** (was 4). `stream-control` → `<name>_stream` setup/read/stop + stop-deadline watchdog; `data-connection-reclamation` → dead-connection sweep on `reclaim_after_ms`, synchronous in read/stop/dtor; `windows-build-verification` → CURVE demo built + run on MSVC 2022/vcpkg, fixed 2 Windows-only CMake bugs (`Assets/CMakeLists.txt`). The old task 3 `authentication-layer` (ZAP allowlist) was **folded into transport-authn** 2026-08-29 |
| [transport-authn](transport-authn-done/) | mTLS transport (gRPC/REST/SOAP) + RBAC / AuthN / AuthZ + **ZMQ CURVE ZAP allowlist** (absorbed from zmq-lifecycle 2026-08-29) | **done** (all 6 tasks + 2 follow-ons; acceptance gate green — full suite 462 passed / 4 skipped in Docker; `tasks` merged into the `transport-authn` epic branch). `ComplianceReport/` note → `process-artifacts-done/tasks/transport-authn-note.md` (fold into `requirements.py` deferred to a process-artifacts task — no `hardened_transport`-scoped `applies_to` yet, same carve-out `dds-transport-note.md` took). 6 tasks scoped (`cert-provisioning`, `mtls-grpc`, `mtls-rest-soap`, `rbac`, `token-sessions`, `full-acceptance-gate-note`); the ZAP allowlist was scoped into its own task (`zmq-zap-allowlist`) once task 4's identity store was real. Credential gate located: `Database/templates/{rest,soap,grpc_service}.h.tmpl` + emitters `Database/{RestAdapter,SoapAdapter,GrpcServiceAdapter}.py`. Implementation: tasks 1–4 **done**. `cert-provisioning` → `Assets/cmake/mtls_provision.sh` + `-DUSE_MTLS`. `mtls-grpc` → generated `grpc/grpc_server_bringup.h` (`harpia::grpc_transport::GrpcServer`, `harpia_grpc_mtls.h`). `mtls-rest-soap` → generated `http/http_server_bringup.h` (`harpia::http_transport::HttpServer`, one `crow::SimpleApp` w/ REST under `rest_base` + SOAP under `soap_base`, `harpia_http_mtls.h` `asio::ssl::context` with `verify_fail_if_no_peer_cert`); also fixed a latent `is_valid_json` ODR clash in `JsonAdapter`. `rbac` → the per-route/RPC gate now has two generation-time variants (`Database/auth_gate.py`, one impl per project, keyed on `transport_hardening_required`): the flat `X-User`/`X-Pswd` (SOAP `<credentials>`, gRPC metadata) credential unchanged for non-hardened profiles, and `admin`/`main`/`guest` RBAC for hardened — keyed on the verified client-cert subject CN (crow patched for `crow::request::client_cert_cn`; gRPC via `ServerContext::auth_context()`), resolved to a role via the `HARPIA_RBAC_MAP` file (**store shape pinned: startup-read deployment config, not schema, not compiled-in**), fixed matrix in copied-verbatim `Compliance/runtime/harpia_rbac.h` (admin=all, main=all-but-remove, guest=read/list/stream, heartBeat open), differentiated 401/UNAUTHENTICATED (no identity) vs 403/PERMISSION_DENIED (wrong role), one `AuditSink` `rbac_denied` record per denial (value-free). `test_rbac.py` covers the matrix + audit + live 401/403/200 across gRPC/REST/SOAP; `test_stage11/12/13` pinned to a low-risk profile for the flat-gate path. Two task-4 follow-ons also **done**: `rbac-generated-tests` (TestAdapter emits RBAC-aware `<name>_test.cpp` under a hardened profile — matrix via `harpia::rbac::permitted` + fail-closed 401 HTTP asserts; `test_stage14` runs the hardened profile + a low-risk build for the flat bodies) and `zmq-zap-allowlist` (the absorbed CURVE ZAP client-key allowlist: hardened `CURVE_SERVER` ctors call `::harpia::zap::ensure_running(ctx)` → a ZAP handler on `inproc://zeromq.zap.01` checks each client key against the `HARPIA_ZMQ_ALLOWLIST` file — **same startup-read-config shape as `HARPIA_RBAC_MAP`** — deny-all with no file, one `AuditSink` `zap_denied` per rejection; `ZmqAdapter/runtime/harpia_zap.h`, `Assets/cmake/zmq_zap_provision.sh`, `test_zmq_zap.py`; `test_stage13_zmq` pinned low-risk). All three bring-ups fail-safe (throw / `static_assert`) and gated by `transport_hardening_required(compliance)` + the F5 seam. `token-sessions` → bearer tokens layered on the RBAC gate (`Compliance/runtime/harpia_session.h`, copied next to `harpia_rbac.h`): HMAC-SHA256 (self-contained SHA-256, pure-std) over CN + role + expiry + `jti`; presented as `Authorization: Bearer` / `authorization` metadata in place of re-deriving identity from the cert; a presented-but-invalid token is 401/UNAUTHENTICATED, never a cert fall-through; `HARPIA_SESSION_{KEY,TTL,REVOCATIONS}` deployment config (same shape as `HARPIA_RBAC_MAP`); issuance via `POST <base>/session` (REST/SOAP) / `heartBeat` + `harpia-issue-session` metadata (gRPC); one value-free `session_denied` audit record per non-ok verify; `test_sessions.py`. `full-acceptance-gate-note` → certified the gate + filed the note (no new mechanism). Remaining follow-up: TestAdapter emits no gRPC `_test.cpp`, so the generated gRPC surface has no RBAC self-test. |
| [events-callbacks](events-callbacks-done/) | `event[cached/not-cached]`, detached-thread callback dispatch | **done** (task 1 → `Callback/` module + `EventChannel<T>` + CRUDL `publish()` on create/update; task 2 → detached-thread dispatch + callback exception isolation; task 3 → OnChange `AuditSink` for `phi` (`phi_event_dispatch` / `phi_event_onchange`) + headline round-trip; `ComplianceReport/` note in `process-artifacts-done/tasks/events-callbacks-phi-audit-note.md`) |
| [process-artifacts](process-artifacts-done/) | SBOM, traceability matrix, jurisdiction-selected doc templates, `ComplianceReport/` module | **done** (`sbom-emission` → CycloneDX SBOM; `traceability-matrix` → `requirements.py` catalog + `traceability.{json,md}`, 3 `*-note.md` folded in; `jurisdiction-template-selection` → `compliance_report[.<jur>].md` shells, same evidence) |
| [static-fuzz-ci](static-fuzz-ci/) | static / fuzz analysis CI | not started (scoping doc only) |
| [versioning](versioning-done/) | versioning / git integration — folded into `process-artifacts`' `ComplianceReport/` output | **done** (2/2 tasks). `Util/gitstate.py::collect_git_state()` shells out to the `git` binary for six fields (commit / ref / dirty / describe / origin_url / parent_commit = merge-base with `origin/HEAD`); every field guarded, git-absent → all `"unknown"`, never a raise. `git` added to the Docker image. `ComplianceReport._git_properties()` emits them as six `harpia:git_*` entries in `bom.json` `metadata.properties` (after the `harpia:*` context pairs); `dirty` → `"true"`/`"false"`. `_collect_compliancereport` pins them to fixed sentinels for the golden (like `metadata.timestamp`). `HARPIA_TOOL_VERSION` `0.1.0`→`0.2.0`; one `VERSION-LINEAGE` `(project)` row in `requirements.py`. Docker: 459 passed, 4 skipped. |
| [dds-transport](dds-transport-done/) | DDS transport adapter (ASTM F2761 / OpenICE-class bedside bus) | **done** (tasks 1–5). `dds` modifier (AST flag, clean `.proto`); Cyclone DDS 0.10.5 + `ddscxx` vendored + built in the Docker image (`-DENABLE_SECURITY=ON`); `DdsAdapter/` emits per-message publisher/subscriber with the §4 QoS mapping (`critical`→RELIABLE/KEEP_ALL, else BEST_EFFORT/KEEP_LAST(1)); DDS-Security wiring via the F5 `CryptoBackend` seam (fail-safe `secured_participant`, strict governance, per-schema permissions, throwaway-PKI provisioning probe) — seam extended with `transport_security()` / `transport_hardening_required()`; `phi`-over-DDS `AuditSink` path (one value-free `phi_publish` per publish). `ComplianceReport/` note → `process-artifacts-done/tasks/dds-transport-note.md` (fold into `requirements.py` deferred to a process-artifacts task — needs a `dds`-scoped `applies_to`). `deadline[ms]` QoS still carved out pending domain expert. |
| [sdc-biceps](sdc-biceps-done/) | IEEE 11073 SDC / BICEPS bindings (scoping + WS-Discovery responder only) | **done** (3/3 tasks). `ws-discovery-test-harness` → `UnitTests/wsdiscovery_harness.py` (stdlib-only WS-DD 2009 probe/resolve client). `ws-discovery-responder` → new additive `SdcAdapter/` module + hand-written `SdcAdapter/runtime/harpia_wsdiscovery.h` (C++17 responder, tinyxml2, POSIX multicast listener on `239.255.255.250:3702`, Windows-inert); per table-bearing message a `<name>_<hash>_sdc.h` participant descriptor + `<name>_<hash>.wsdd.xml` static sidecar; **fixed generic `dpws:Device` type + `https://harpia.dev/sdc/scope/<project>/<message>` scope URI — no new `.harpia` modifier this pass**; `XAddrs` → the existing Stage 11 SOAP endpoint (`Database/SoapAdapter.py` / `WsdlAdapter.py` read-only, untouched); one `SdcAdapter(...).Process()` call in `main.py` after `WsdlAdapter`; `golden/sdc/` + `test_golden.py::test_sdc`; `test_wsdiscovery_responder.py` (compiled `handle_datagram` assertions + live discover → open SOAP). `metric-alert-context-design-doc` → `sdc-biceps-done/sdc_biceps_design.md` (BICEPS Metric/Alert/Context mapping analysis: `event ≈ Metric` / `critical event ≈ Alert` / `Context ≈ no-grammar-yet` as a **hypothesis** needing a domain-expert pass — V1–V7 validation list, 7 gaps, no grammar change). Docker: 429 passed, 4 skipped. Full BICEPS state machine / MDS·VMD·Channel model / any `SdcAdapter/` codegen past the responder = a follow-on epic gated on the design doc's open questions. |
| [fhir-facade](fhir-facade-done/) | HL7 FHIR façade (design doc done; one worked example remaining) | **done** (1/1 task). Design doc complete (façade beside the adapters, `FhirAdapter/` reads compiled message + explicit mapping annotation, `phi`→`meta.security`, static terminology binding — no codegen this pass). `heartrate-observation-worked-example` → `fhir-facade-done/worked-example/`: `HeartRateReading` (`phi int heart_rate; string device_id`) hand-mapped to a conformant FHIR **R4** `Observation` — LOINC 8867-4 + UCUM `/min`, `category` vital-signs, `phi`→whole-resource `meta.security` R (FHIR has no field-level confidentiality), `device_id`→`Observation.device` by identifier (no split/contained `Device`), no invented `subject` (recorded as a gap). Vendored `fhir.schema.json` (R4, CC0) + `mapping-notes.md` + `UnitTests/test_fhir_observation_example.py` (13 tests, stdlib-only; independently cross-checked against the full R4 schema). Docker: 442 passed, 4 skipped. Generated `FhirAdapter/` / grammar / `Bundle`·`Reference` logic / `CapabilityStatement` / identity-linkage DSL + the design-doc open questions (LGPD counsel, SMART scopes, break-the-glass) = a follow-on implementation epic, not started. |

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
- **zmq-lifecycle** is fully done (all 3 tasks) and needed nothing from
  transport-authn. The one real transport-authn ordering dependency that
  lived here — the ZAP client-key allowlist — is now a transport-authn
  deliverable (absorbed 2026-08-29): scope it after that epic's credential
  model exists.
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
