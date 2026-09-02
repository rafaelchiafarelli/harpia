// harpia Stage 10 phi-redaction control (hand-written, not generated).
//
// Track F / Session F.3. The unified serialization path
// (harpia_serialize.h) renders every `phi` field -- in JSON, XML and YAML
// alike -- as `kPlaceholder` by default. This header is the one place that
// decision lives:
//
//   * which fields are `phi`  -> the generated serialize/harpia_phi_registry.h
//   * whether redaction is on -> redaction_enabled() (default TRUE)
//
// Opting OUT of redaction is an explicit, audited action: call
// harpia::redaction::allow_phi_print(AuditSink&) from the sibling header
// harpia_redaction_audit.h (serialization epic, task 4). It records the event
// then calls set_redaction_enabled(false). The bare setter below stays as the
// low-level mechanism and the F.3 test seam.
#ifndef HARPIA_REDACTION_RUNTIME_H
#define HARPIA_REDACTION_RUNTIME_H

#include <string_view>

#include "serialize/harpia_phi_registry.h"

namespace harpia {
namespace redaction {

// what a `phi` value is replaced with. Fixed, recognizable, value-free.
inline constexpr const char* kPlaceholder = "[REDACTED]";

// process-wide toggle. Default ON -- redaction is the safe default (a caller
// must opt OUT, and F.4 makes opting out an audited event). Not thread-safe
// (caller-synchronized, same as the rest of these runtimes).
inline bool& detail_enabled() {
    static bool enabled = true;
    return enabled;
}

inline bool redaction_enabled() { return detail_enabled(); }
inline void set_redaction_enabled(bool on) { detail_enabled() = on; }

// should this (message, field) be redacted right now?
inline bool should_redact(std::string_view message, std::string_view field) {
    return redaction_enabled() &&
           ::harpia::serialize::phi::is_phi(message, field);
}

}  // namespace redaction
}  // namespace harpia

#endif  // HARPIA_REDACTION_RUNTIME_H
