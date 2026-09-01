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
"""


class Req:
    __slots__ = ("id", "rule_ref", "applies_to", "text", "mechanism", "test_refs")

    def __init__(self, id, rule_ref, applies_to, text, mechanism, test_refs):
        self.id = id
        self.rule_ref = rule_ref
        self.applies_to = applies_to
        self.text = text
        self.mechanism = mechanism
        self.test_refs = list(test_refs)


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
        ["test_sbom_emission.py::test_", "test_golden.py::test_compliancereport"]),

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
        ["test_stage10_serialize.py::test_unredacted_flag_reveals_value_and_emits_audit_record"]),

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
         "test_stage10_serialize.py::test_phi_message_round_trips_redacted_through_all_three_formats"]),

    Req("R1-ENC", "design-rules Rule 1", "phi_field_table",
        "A phi field persisted to the database is stored field-level "
        "envelope-encrypted; an unrecoverable value degrades to 0/\"\" (Rule 5), "
        "never a throw.",
        "EncryptedColumn (Crypto/runtime/harpia_encrypted_column.h): DEK -> seal -> "
        "wrap DEK with the active KEK via the key-management KeyProvider -> enc:v1: "
        "framed hex. CrudlAdapter wires a KeyProvider& into the phi-bearing DAO: "
        "encrypt on create/update, decrypt on read/list.",
        ["test_stage8_db.py::test_a1_", "test_stage8_db.py::test_a2_"]),

    Req("R5-AUDIT-DB", "design-rules Rule 5", "phi_field_table",
        "Every CRUDL operation touching a phi column emits exactly one AuditSink "
        "record; subject = table, detail = phi column names -- never a value. A "
        "not-found read audits nothing.",
        "CrudlAdapter phi_create / phi_read / phi_update / phi_delete / phi_list "
        "record() calls on the DAO's injected AuditSink&.",
        ["test_stage8_db.py::test_a3_"]),

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
         "test_zmq_critical_delivery.py::test_"]),

    Req("R3-INTEGRITY", "design-rules Rule 3", "critical_message",
        "Integrity is computed once at the origin (Envelope CRC + sequence number) "
        "and verified only at genuine trust-boundary crossings: Ok / CrcMismatch / "
        "SeqGap / SeqRegressed.",
        "harpia_delivery.h: Envelope::stamp() at the origin, crc_ok() + "
        "check_on_arrival() at the boundary.",
        ["test_delivery_runtime.py::test_",
         "test_critical_delivery_roundtrip.py::test_"]),
]

REQUIREMENTS_BY_ID = {r.id: r for r in REQUIREMENTS}
