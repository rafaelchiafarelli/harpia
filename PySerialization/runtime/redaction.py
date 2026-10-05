"""``phi`` redaction for serialized output (port of ``harpia_redaction.h``).

Every ``phi`` field prints as :data:`PLACEHOLDER` through
``harpia_runtime.serialize.to_string`` while redaction is enabled (the
default). Turning it off is an audited operation: use
``harpia_runtime.redaction_audit.allow_phi_print`` rather than calling
:func:`set_redaction_enabled` directly.
"""
from harpia_generated.serialize.phi_registry import is_phi

#: what a ``phi`` value prints as while redaction is on
PLACEHOLDER = "[REDACTED]"

_enabled = True


def redaction_enabled() -> bool:
    """Whether ``phi`` values are currently redacted (process-wide)."""
    return _enabled


def set_redaction_enabled(on: bool) -> None:
    """Turn redaction on or off for the whole process (not audited)."""
    global _enabled
    _enabled = on


def should_redact(message: str, field: str) -> bool:
    """Whether ``message.field`` prints as the placeholder right now."""
    return _enabled and is_phi(message, field)
