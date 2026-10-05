"""Audited opt-out from ``phi`` redaction (port of
``harpia_redaction_audit.h``).

The only module of the serialization runtime that depends on the compliance
runtime: switching redaction off records who asked and why, and switching it
back on records that too. No value is ever passed to the sink.
"""
from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink
from harpia_runtime.redaction import set_redaction_enabled

OP_UNREDACTED_ENABLED = "phi_unredacted_output_enabled"
OP_UNREDACTED_DISABLED = "phi_unredacted_output_disabled"
AUDIT_SUBJECT = "serialize.redaction"


def allow_phi_print(sink: AuditSink | None = None, reason: str = "") -> None:
    """Record ``phi_unredacted_output_enabled``, then disable redaction.

    Args:
        sink: Where to record (default: ``default_audit_sink()``).
        reason: Why unredacted output is needed (no field values).
    """
    (sink or default_audit_sink()).record(OP_UNREDACTED_ENABLED, AUDIT_SUBJECT,
                                          reason)
    set_redaction_enabled(False)


def restore_phi_redaction(sink: AuditSink | None = None) -> None:
    """Re-enable redaction, then record ``phi_unredacted_output_disabled``."""
    set_redaction_enabled(True)
    (sink or default_audit_sink()).record(OP_UNREDACTED_DISABLED, AUDIT_SUBJECT)
