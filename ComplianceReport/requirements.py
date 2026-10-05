"""Compliance requirements catalog -- the fixed set of obligations the
traceability matrix (process-artifacts task 2) maps to code and to test
evidence.

Seeded from `harpia_sensitive_data_design_rules.md` (Rules 0 / 1 / 3 / 4a /
5 / 6a) and from the folded-in `ComplianceReport/` notes of the
serialization, db-encryption and critical-delivery epics. A future
note-producing task adds an entry here, not a prose `*-note.md` file.

`applies_to`:
  "phi_field"        -- one row per `phi`-tagged field, any message
  "phi_field_table"  -- ... but only when that field's message is table-bearing
  "critical_message" -- one row per `critical` message type
  "project"          -- one fixed row, no schema construct

python-target / py-artifacts task 2: `py_mechanism` / `py_test_refs` are the
Python target's mechanism and evidence for the same requirement (a python
run's rows carry them as `python_mechanism` / `python_evidence`; a C++-only
run's rows are unchanged). A Python mechanism weaker than C++'s says so in
its text. `python_run_only` marks a requirement listed only in python runs
(the transport-security entries below: adding them to C++-only runs would
change existing C++ output -- see log item 42); such a row carries both
targets' evidence.
"""


class Req:
    __slots__ = ("id", "rule_ref", "applies_to", "text", "mechanism", "test_refs",
                 "py_mechanism", "py_test_refs", "python_run_only")

    def __init__(self, id, rule_ref, applies_to, text, mechanism, test_refs,
                 py_mechanism=None, py_test_refs=(), python_run_only=False):
        self.id = id
        self.rule_ref = rule_ref
        self.applies_to = applies_to
        self.text = text
        self.mechanism = mechanism
        self.test_refs = list(test_refs)
        self.py_mechanism = py_mechanism
        self.py_test_refs = list(py_test_refs)
        self.python_run_only = python_run_only


REQUIREMENTS = [
    Req("R0-AXES", "design-rules Rule 0", "project",
        "Confidentiality (phi) and criticality (critical) are independent axes, "
        "each declared on the schema and never inferred from a message instance; "
        "neither implies the other.",
        "Separate schema flags: variable.is_phi (Foundation F2) and "
        "Message.is_critical (sensitive-data roadmap phase 1a), parsed independently "
        "in Message/.",
        ["test_phi_modifier.py::test_", "test_critical_modifier.py::test_"]),

    Req("R6A-FLOOR", "design-rules Rule 6a", "project",
        "risk_class is a single project-wide hardening floor (IEC 62304 4.3 "
        "segregation rule); phi/critical machinery is opt-in above it, never a "
        "per-jurisdiction build fork.",
        "ComplianceContext{risk_class,topology,phi_handling,jurisdiction} parsed "
        "from project.harpia.yaml and threaded through every generator stage; "
        "surfaced in the SBOM metadata (harpia:risk_class / topology / phi_handling).",
        ["test_compliance.py::test_"]),

    Req("SBOM", "master plan -- process-artifacts", "project",
        "A CycloneDX SBOM of the generated project's runtime dependencies is "
        "emitted on every generation.",
        "ComplianceReport/ module -> generated/ComplianceReport/bom.json "
        "(CycloneDX 1.5); component versions resolved from third_party/*/VENDORED.md "
        "and the build toolchain, with an explicit 'unknown' fallback.",
        ["test_sbom_emission.py::test_", "test_golden.py::test_compliancereport"],
        py_mechanism="A python run also lists the generated Python package and its "
        "declared PyPI runtime dependencies (PyAdapter.dependencies, the constants "
        "that render pyproject.toml) as pypi: components.",
        py_test_refs=["test_sbom_emission.py::test_python_components_listed_and_schema_valid"]),

    Req("VERSION-LINEAGE", "master plan -- versioning", "project",
        "Every generation records the git fork-lineage of the schema project "
        "(commit, ref, dirty-tree, describe, origin, fork-point) as recoverable "
        "submission evidence; a project generated without git degrades to an "
        "explicit 'unknown', never a fabricated or missing record.",
        "Util/gitstate.collect_git_state() -> ComplianceReport._git_properties() "
        "-> six harpia:git_* entries in generated/ComplianceReport/bom.json "
        "metadata.properties; all-'unknown' when the git binary or repo is absent.",
        ["test_version_lineage.py::test_", "test_gitstate.py::test_",
         "test_golden.py::test_compliancereport"]),

    Req("R5-AUDIT-OPTOUT", "design-rules Rule 5", "project",
        "Disabling phi redaction for output is an explicit, non-default, audited "
        "action -- never silent.",
        "harpia_redaction_audit.h: allow_phi_print(AuditSink&, reason) emits one "
        "record(\"phi_unredacted_output_enabled\", \"serialize.redaction\", reason) "
        "then set_redaction_enabled(false); restore_phi_redaction() records the "
        "re-enable. Names/context only, never a value.",
        ["test_stage10_serialize.py::test_unredacted_flag_reveals_value_and_emits_audit_record"],
        py_mechanism="harpia_runtime.redaction_audit.allow_phi_print(sink, reason) / "
        "restore_phi_redaction(): one value-free record each, same operation names "
        "as C++.",
        py_test_refs=["test_py_serialize.py::test_"]),

    Req("R1-RED", "design-rules Rule 1", "phi_field",
        "A phi field renders as the fixed placeholder \"[REDACTED]\" by default in "
        "every toString format (JSON / XML / YAML); the field/key is never omitted "
        "and the real value never appears.",
        "harpia_serialize.h redacted reflection walk, gated by "
        "harpia::redaction::redaction_enabled() (default true) and the generated "
        "serialize/harpia_phi_registry.h (from variable.is_phi). The three per-format "
        "engines are untouched.",
        ["test_stage10_serialize.py::test_phi_fields_redacted_in_all_three_formats",
         "test_stage10_serialize.py::test_mixed_message_redacts_only_phi_fields",
         "test_stage10_serialize.py::test_phi_message_round_trips_redacted_through_all_three_formats"],
        py_mechanism="harpia_runtime.serialize.to_string redacted walk, gated by "
        "harpia_runtime.redaction.redaction_enabled() and the generated "
        "harpia_generated/serialize/phi_registry.py; byte-identical to C++ with "
        "redaction on and off.",
        py_test_refs=["test_py_serialize.py::test_"]),

    Req("R1-ENC", "design-rules Rule 1", "phi_field_table",
        "A phi field persisted to the database is stored field-level "
        "envelope-encrypted; an unrecoverable value degrades to 0/\"\" (Rule 5), "
        "never a throw.",
        "EncryptedColumn (Crypto/runtime/harpia_encrypted_column.h): DEK -> seal -> "
        "wrap DEK with the active KEK via the key-management KeyProvider -> enc:v1: "
        "framed hex. CrudlAdapter wires a KeyProvider& into the phi-bearing DAO: "
        "encrypt on create/update, decrypt on read/list.",
        ["test_stage8_db.py::test_a1_", "test_stage8_db.py::test_a2_"],
        py_mechanism="harpia_runtime.crypto.encrypted_column (enc:v1: framing, "
        "decrypts C++ values and vice versa over one key store) + the generated "
        "PhiDao subclasses. WEAKER THAN C++: key-material zeroization is "
        "best-effort -- a Dek's bytearray is wiped on close / __del__, but "
        "Python may keep immutable copies (bytes, the decrypted str) until garbage "
        "collection; C++ secure_zero wipes deterministically.",
        py_test_refs=["test_py_encrypted_column.py::test_", "test_py_db_phi.py::test_",
                      "test_py_key_provider.py::test_"]),

    Req("R5-AUDIT-DB", "design-rules Rule 5", "phi_field_table",
        "Every CRUDL operation touching a phi column emits exactly one AuditSink "
        "record; subject = table, detail = phi column names -- never a value. A "
        "not-found read audits nothing.",
        "CrudlAdapter phi_create / phi_read / phi_update / phi_delete / phi_list "
        "record() calls on the DAO's injected AuditSink&.",
        ["test_stage8_db.py::test_a3_"],
        py_mechanism="harpia_runtime.db.phi.PhiDao records phi_create / phi_read / "
        "phi_update / phi_delete / phi_list at the C++ points (not-found read "
        "silent), names only.",
        py_test_refs=["test_py_db_phi.py::test_"]),

    Req("R4A-ORDERED", "design-rules Rule 4a", "critical_message",
        "A critical message type gets ordered/complete delivery: held in a bounded "
        "queue during an outage, replayed in sequence on reconnect, oldest-drop on "
        "overflow is audited (never a silent loss). A non-critical message on the "
        "same path is allowed to drop.",
        "harpia_delivery.h BoundedQueue + Envelope; ZmqAdapter routes a critical "
        "message's publisher through the delivery queue (flush() / pending()); a "
        "\"queue_rotated\" AuditSink record on every overflow drop.",
        ["test_delivery_runtime.py::test_",
         "test_critical_delivery_roundtrip.py::test_",
         "test_zmq_critical_delivery.py::test_"],
        py_mechanism="harpia_runtime.delivery BoundedQueue + the generated critical "
        "QueuedSender (flush() / pending()), queue_rotated audited on overflow; a "
        "critical dds message is RELIABLE + KEEP_ALL + ResourceLimits.",
        py_test_refs=["test_py_delivery.py::test_", "test_py_dds.py::test_"]),

    Req("R3-INTEGRITY", "design-rules Rule 3", "critical_message",
        "Integrity is computed once at the origin (Envelope CRC + sequence number) "
        "and verified only at genuine trust-boundary crossings: Ok / CrcMismatch / "
        "SeqGap / SeqRegressed.",
        "harpia_delivery.h: Envelope::stamp() at the origin, crc_ok() + "
        "check_on_arrival() at the boundary.",
        ["test_delivery_runtime.py::test_",
         "test_critical_delivery_roundtrip.py::test_"],
        py_mechanism="harpia_runtime.delivery Envelope.stamp() / crc_ok() / "
        "check_on_arrival(); the CRC equals C++ detail::crc32.",
        py_test_refs=["test_py_delivery.py::test_"]),

    # -- transport security: listed in python runs only (log item 42) ------
    Req("TRANSPORT-MTLS-RBAC", "master plan -- transport-authn", "project",
        "Under a hardened profile (or for a protected message) the REST / SOAP / "
        "gRPC transports require mTLS and gate every data operation on the "
        "verified identity's admin / main / guest role; incomplete PKI is "
        "refused, never a plaintext fallback; every denial is audited without a "
        "value.",
        "harpia_http_mtls.h / harpia_grpc_mtls.h (SecurityRefused) + harpia_rbac.h "
        "decide() on the client-certificate CN, per message by "
        "Database.auth_gate.effective_rbac.",
        ["test_rbac.py::test_", "test_protected_open_modifiers.py::test_"],
        py_mechanism="harpia_runtime.tls (SecurityRefused) + harpia_runtime.rbac "
        "(same map file, decisions and audit text as C++) + harpia_runtime."
        "rbac_gates. WEAKER THAN C++ for gRPC mixed mode: grpcio cannot verify an "
        "optional client certificate, so in mixed mode a certificate-only gRPC "
        "caller is anonymous and RBAC RPCs fail closed (UNAUTHENTICATED); bearer "
        "tokens from HTTPS restore access.",
        py_test_refs=["test_py_mtls.py::test_", "test_py_rbac.py::test_"],
        python_run_only=True),

    Req("ZMQ-ZAP", "master plan -- transport-authn", "project",
        "Under a hardened profile a bind-side CURVE ZMQ socket admits only "
        "allowlisted client keys (ZAP); every refusal is audited.",
        "harpia_zap.h ZapHandler + AllowList on the ZAP endpoint, zap_denied "
        "records.",
        ["test_zmq_zap.py::test_"],
        py_mechanism="harpia_runtime.zap: a hand-written REP loop on the ZAP "
        "endpoint over the same allowlist file format.",
        py_test_refs=["test_py_zmq_curve.py::test_"],
        python_run_only=True),

    Req("SESSIONS", "master plan -- transport-authn", "project",
        "Bearer session tokens are signed, expiring and revocable; a presented "
        "but invalid token is refused and never falls back to the certificate.",
        "harpia_session.h issue() / verify() / from_authorization() layered on the "
        "RBAC gates; session_denied audited.",
        ["test_sessions.py::test_"],
        py_mechanism="harpia_runtime.session: byte-compatible tokens (C++ and "
        "Python verify each other's), the same gate rules.",
        py_test_refs=["test_py_sessions.py::test_"],
        python_run_only=True),

    Req("DDS-SECURITY", "master plan -- dds-transport", "project",
        "DDS participants are OMG DDS-Security participants (authentication, "
        "access control, encryption); an incomplete PKI is refused, never a "
        "plaintext participant.",
        "harpia_dds_security.h secured_participant() + the emitted "
        "governance / permissions documents.",
        ["test_dds_security.py::test_"],
        py_mechanism="harpia_runtime.dds.security.secured_participant(): the same "
        "Cyclone <Security> configuration; also refuses a domain that already "
        "exists unsecured in the process.",
        py_test_refs=["test_py_dds_security.py::test_"],
        python_run_only=True),
]

REQUIREMENTS_BY_ID = {r.id: r for r in REQUIREMENTS}
