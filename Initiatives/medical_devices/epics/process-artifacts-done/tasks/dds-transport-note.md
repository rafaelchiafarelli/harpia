## `ComplianceReport/` note for the dds-transport epic (DDS transport + DDS-Security + `phi` audit)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module
  exists).
- **Origin:** raised by the dds-transport epic (`../../dds-transport/`), its
  final task (`full-acceptance-gate-note`). `alarm_event` / `vitals_publication`
  carry `phi` fields and cross the DDS bus, so the epic's work is
  `phi`-adjacent per the effort's definition of done (master plan §4) and
  owes a traceability note — but `ComplianceReport/` is this epic's module,
  not the dds-transport epic's, so the note is written here (same as
  `critical-delivery-note.md` / `phi-db-encryption-note.md` /
  `serialization-redaction-note.md`).
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  dds-transport epic — what changed, why, and which tests cover it — as raw
  material for the traceability matrix:

  - **`dds` transport-selection modifier (task 1).** A message-type-level
    `dds` modifier (same slot as `event`/`stream`/`push`/`pull` and
    `critical`), landed as an AST flag only (`Message.is_dds`) — it never
    touches the emitted `.proto` (byte-identical to the same message without
    it), the same routing-flag guarantee `phi` / `critical` hold. Marks a
    message for publish onto / subscribe from an ASTM F2761 / OpenICE-class
    DDS bus, independent of ZMQ/gRPC reachability.
  - **`DdsAdapter/` + §4 QoS mapping (tasks 2a, 2b).** Eclipse Cyclone DDS
    0.10.5 + its `ddscxx` C++ binding are vendored (`third_party/cyclonedds
    {,-cxx}/`) and built once into the Docker toolchain image with
    `-DENABLE_SECURITY=ON -DENABLE_SSL=ON` (hybrid vendoring, same posture as
    protobuf/gRPC/ZeroMQ/SOCI). `DdsAdapter` emits, per `dds` message, a
    header-only publisher/subscriber over one opaque keyed frame type
    (`harpia_dds::Frame` = `@key string message_type; sequence<octet>
    payload`, the payload being the *same* serialized-protobuf bytes ZMQ/gRPC
    move) plus the shared frame IDL + its CMake scaffolding. The
    delivery-guarantee split (`harpia_sensitive_data_design_rules.md` §4) is
    mapped onto DDS QoS at the schema level, never inferred at runtime:
    `critical` → §4a ordered/complete (`Reliability::Reliable` +
    `History::KeepAll` + bounded `ResourceLimits`, `QUEUE_DEPTH=128` mirroring
    the ZMQ path's `BoundedQueue`); non-`critical` → §4b latest-value-only
    (`Reliability::BestEffort` + `History::KeepLast(1)`). Reader QoS mirrors
    the writer. `DURABILITY` stays `VOLATILE` (late-joiner catch-up is a
    per-use-case open question, not defaulted on). A `deadline[ms]` QoS knob
    is carved out pending a domain-expert pass.
  - **DDS-Security wiring via the F5 `CryptoBackend` seam (task 3).**
    Whenever the schema has any `dds` message, `DdsAdapter` also ships
    `dds/harpia_dds_security.h` (a hand-written secured-`DomainParticipant`
    helper over the Cyclone builtin DDS-Security authentication /
    access-control / cryptographic plugins — `libdds_security_{auth,ac,
    crypto}.so` — configured via an inline `CYCLONEDDS_URI` `<Security>`
    block, since `ddscxx` 0.10.5 has no C++ `Property` QoS policy) and a
    `dds/security/` directory: a static `governance.xml` with the fail-safe
    posture (`allow_unauthenticated_participants=false`, join/read/write
    access control on for every topic — master plan §0a), a per-project
    `permissions.xml` (publish + subscribe allowed on exactly this schema's
    `dds` topic names, `<default>DENY</default>`), and
    `dds_security_selection.json` recording the F5 selection. The helper is
    **fail-safe**: `secured_participant()` throws `SecurityRefused` when the
    PKI is incomplete — never a silent plaintext participant. The F5 seam was
    extended for this: `CryptoBackend.transport_security()` (the
    which-module descriptor: `cmake_package` / `openssl_provider` / `fips`)
    and the module-level `transport_hardening_required(compliance)` predicate
    (`risk_class == CLASS_C` or `topology == CLOUD_CONNECTED`, §0a — the same
    rule `get_backend()` keys its FIPS default off, so DDS-Security and the
    transport-authn epic's future mTLS can't diverge on *when* hardening is
    mandatory). A throwaway-PKI provisioning probe
    (`Assets/cmake/dds_security_provision.sh`, the DDS-Security analogue of
    `Assets/cmake/curve_keygen_probe.cpp`) mints a demo CA + identity and
    S/MIME-signs the governance/permissions; `-DUSE_DDS_SECURITY=ON` runs it
    at configure time and writes `harpia_dds_security_files.h`.
  - **`phi` field `AuditSink` path over DDS (task 4).** A `dds` message
    carrying ≥1 `phi` field gets a publisher holding an
    `::harpia::compliance::AuditSink&` (trailing defaulted ctor param, so a
    non-`phi` `dds` transport is byte-identical to the pre-task-4 output),
    and every `publish()` records exactly one value-free entry — operation
    `"phi_publish"`, subject = the DDS topic name, detail = the comma-joined
    `phi` field *names*, never a value (design-rules Rule 5). Same call
    pattern the db-encryption epic established for the DB path
    (`phi_create` / `phi_read` / …): the transport changes, the audit
    obligation does not. Scoped to the publish side; the subscriber is
    untouched. `harpia_audit_sink.h` is copied next to the generated
    headers.
  - **Additive, not a replacement (task 5 acceptance gate).** `dds` is a
    third selectable transport alongside gRPC and ZMQ — the existing
    ZMQ/gRPC/REST/SOAP demo and round-trip tests are unaffected. Full suite
    green in Docker: **390 passed, 4 skipped**.
  - **Tests:** `UnitTests/test_dds_modifier.py` (task 1 — AST flag, clean
    `.proto`), `UnitTests/test_dds_vendor_spike.py` (task 2a — the vendored
    stack is real/linkable, both QoS profiles construct, the DDS-Security
    property API round-trips), `UnitTests/test_dds_qos_mapping.py` +
    `UnitTests/test_dds_demo.py` (task 2b — structural §4 mapping + a
    build-and-run proof the semantics differ under a transient receiver gap),
    `UnitTests/test_dds_security.py` (task 3 — structural: runtime shipped
    verbatim + fail-safe, strict governance, per-schema permissions with
    default-DENY, F5 selection recorded and flips with compliance/backend; +
    a gated fork demo where a plain unauthenticated peer receives nothing
    while a secured peer receives the stream), `UnitTests/test_dds_phi_audit.py`
    (task 4 — structural: one value-free `phi_publish` record per publish,
    subscriber untouched, no-`phi` message byte-identical; + a gated build
    that asserts N records and the value never reaching the sink),
    `UnitTests/test_crypto_backend.py` (F5 seam extension:
    `transport_security()` / `transport_hardening_required()`),
    `UnitTests/test_golden.py::test_dds_adapters` (the `dds/` snapshot,
    including `harpia_dds_security.h` + `security/`).

- **Fold into `ComplianceReport/requirements.py`:** deferred to a
  **process-artifacts** task, not done here. The current matrix builder
  (`ComplianceReport/ComplianceReport.py::_traceability_rows`) has
  `applies_to` values `phi_field` / `phi_field_table` / `critical_message` /
  `project` only — none of which is scoped to "a `phi` field on a `dds`
  message" or "a `dds` message type". Adding `phi_publish` / DDS-Security /
  DDS-QoS rows correctly needs a new `applies_to` plus a change to
  `_traceability_rows()` (which also moves the `compliancereport/` golden) —
  that is the process-artifacts epic's module and its call, exactly the
  reason `ComplianceReport/` notes are filed as process-artifacts tasks
  (`epics/README.md` DoD rule 6). This file is the raw material for that
  task.

- **Tests:** covered by the matrix spot-check once the fold-in task above
  runs (one row per annotated construct).

---
## Epic context — process-artifacts

**Contract.** SBOM (CycloneDX/SPDX), a traceability matrix, jurisdiction-selected
doc templates (fda/eu_mdr/anvisa), and the `ComplianceReport/` module every
`phi`-adjacent epic writes a one-paragraph note into. This is the one place
`jurisdiction[]` actually drives different output. Needs `ComplianceContext` from
Foundation. Terminal artifact — feeds the regulatory submission, not another epic
(except versioning, which extends the `ComplianceReport/` output once
sbom-emission has merged).

**Files.** New `ComplianceReport/` module.

**Watch for.** Before considering this epic done: check the `ComplianceReport/`
notes from db-encryption, transport-authn, events-callbacks / serialization, and
dds-transport actually landed — the matrix is only as complete as those notes.
