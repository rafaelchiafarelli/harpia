// harpia AuditSink -- abstract interface for compliance/audit event
// recording (Foundation F3), hand-written, not generated. Interface + no-op
// stub only: real (tamper-evident) implementations are Track A (DB) and
// Track C (transport)'s job, independently, once each track starts --
// see Initiatives/medical_devices/harpia_medical_master_plan.md.
//
// Injection point for generated code: a generated class that needs to audit
// (a DAO doing a CRUDL op on a `phi` field, a KeyProvider doing a key
// operation, a transport sending/receiving a `critical` message) takes an
// `AuditSink&` in its constructor, defaulting to a shared NoOpAuditSink
// instance so existing/untagged projects are unaffected byte-for-byte:
//
//   class some_dao {
//   public:
//       explicit some_dao(harpia::compliance::AuditSink& audit =
//                              harpia::compliance::default_audit_sink())
//           : audit_(audit) {}
//       void create(...) {
//           // ... do the write ...
//           audit_.record("phi_write", "some_dao.some_field");
//       }
//   private:
//       harpia::compliance::AuditSink& audit_;
//   };
//
// Rule 5 (harpia_sensitive_data_design_rules.md): audit logging captures
// that an event happened and identifying metadata, NEVER the sensitive
// value itself -- enforced structurally here: record()'s signature has no
// parameter that could carry a field's actual value, only names/ids.
#ifndef HARPIA_COMPLIANCE_AUDIT_SINK_H
#define HARPIA_COMPLIANCE_AUDIT_SINK_H

#include <string>

namespace harpia {
namespace compliance {

class AuditSink {
public:
    virtual ~AuditSink() = default;

    // operation: what happened, in the CALLER's own domain vocabulary (e.g.
    // "phi_read", "phi_write", "key_rotate", "message_sent",
    // "queue_rotated", "mailbox_overwritten") -- Foundation deliberately
    // does not own a closed enum of these. Each downstream track (DB, keys,
    // transports, events) adds whatever operation names its own domain
    // needs without ever having to modify this Foundation-owned interface.
    // subject: identifying metadata only -- a message/field name, a
    // patient or device id -- never the field's actual value.
    // detail: optional additional non-sensitive context (e.g. an outcome).
    virtual void record(const std::string& operation,
                        const std::string& subject,
                        const std::string& detail = "") = 0;
};

// The only implementation that exists until a downstream track builds a
// real (tamper-evident) sink. Zero side effects -- every untagged/
// non-medical-device-grade project keeps today's behavior exactly.
class NoOpAuditSink : public AuditSink {
public:
    void record(const std::string& /*operation*/,
               const std::string& /*subject*/,
               const std::string& /*detail*/ = "") override {}
};

// Shared default instance so generated constructors can default an
// `AuditSink&` parameter without allocating (see the injection-point
// example above). Meyers-singleton for safe static-init order across
// translation units.
inline AuditSink& default_audit_sink() {
    static NoOpAuditSink instance;
    return instance;
}

}  // namespace compliance
}  // namespace harpia

#endif  // HARPIA_COMPLIANCE_AUDIT_SINK_H
