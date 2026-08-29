// harpia serialization -- audited opt-out from phi redaction
// (serialization epic, task 4 "audited unredacted-output flag").
//
// harpia_redaction.h owns the process-wide redaction toggle and keeps it ON
// by default: unredacted `phi` output in to_string() requires an explicit,
// non-default opt-out. THIS header is that opt-out, and it is deliberately
// the only sanctioned way to reach it -- every entry point here emits exactly
// one AuditSink record, so "someone turned phi redaction off" is never a
// silent event.
//
// Bare `set_redaction_enabled(false)` stays in harpia_redaction.h as the
// low-level mechanism (and the F.3 test seam); production and collaborator
// code opts out through `allow_phi_print()` so the audit trail is structural,
// not a convention.
//
// This is the one place SerializeAdapter's runtime depends on the Compliance
// module (Foundation F3 -- AuditSink). It is isolated in this header on
// purpose: harpia_redaction.h and the serialization facade stay Compliance-
// free, and a translation unit only takes on the dependency if it actually
// wants the audited opt-out.
#ifndef HARPIA_REDACTION_AUDIT_RUNTIME_H
#define HARPIA_REDACTION_AUDIT_RUNTIME_H

#include <string>

#include "serialize/harpia_redaction.h"
#include "compliance/harpia_audit_sink.h"

namespace harpia {
namespace redaction {

// Audit vocabulary. Caller-domain strings per the AuditSink contract --
// operation names and identifying context only, never a field's value.
inline constexpr const char* kOpUnredactedEnabled  = "phi_unredacted_output_enabled";
inline constexpr const char* kOpUnredactedDisabled = "phi_unredacted_output_disabled";
inline constexpr const char* kAuditSubject         = "serialize.redaction";

// Turn phi redaction OFF process-wide: `phi` values will render in cleartext
// in to_string() output until redaction is restored. Explicit, non-default,
// and audited -- exactly one record() call (before the toggle flips) carrying
// `reason`, a non-sensitive justification string, as its detail.
//
// `audit` defaults to the shared sink, the same convention every other
// audited seam in the generated tree uses (phi DAOs, key providers): the
// record() call is unconditional; wiring it to a real, durable sink is a
// deployment's choice. Passing a sink explicitly is how a caller captures
// the event locally (see the unit test).
inline void allow_phi_print(
    ::harpia::compliance::AuditSink& audit = ::harpia::compliance::default_audit_sink(),
    const std::string& reason = "") {
    audit.record(kOpUnredactedEnabled, kAuditSubject, reason);
    set_redaction_enabled(false);
}

// Restore the default (redaction ON). Also audited -- one record() after the
// toggle flips back -- so the window in which `phi` could be printed has both
// of its edges in the trail.
inline void restore_phi_redaction(
    ::harpia::compliance::AuditSink& audit = ::harpia::compliance::default_audit_sink()) {
    set_redaction_enabled(true);
    audit.record(kOpUnredactedDisabled, kAuditSubject);
}

}  // namespace redaction
}  // namespace harpia

#endif  // HARPIA_REDACTION_AUDIT_RUNTIME_H
