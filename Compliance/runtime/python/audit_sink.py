"""Compliance audit-event recording (Python port of Foundation F3,
``Compliance/runtime/harpia_audit_sink.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.compliance.audit_sink`` whenever a runtime needs it.

Injection point for generated code: a class that needs to audit (a DAO doing
a CRUDL op on a ``phi`` field, a key provider doing a key operation, a
transport sending a ``critical`` message) takes an ``audit_sink`` constructor
argument that defaults to :func:`default_audit_sink`, so untagged projects
behave exactly as before::

    class SomeDao:
        def __init__(self, audit_sink: AuditSink | None = None) -> None:
            self._audit = audit_sink or default_audit_sink()

        def create(self, msg: Msg) -> None:
            ...  # do the write
            self._audit.record("phi_write", "some_dao.some_field")

Rule 5 (sensitive-data design rules): an audit record captures *that* an
event happened plus identifying metadata, never the sensitive value itself.
:meth:`AuditSink.record` only takes names and ids, so a field value has no
parameter to travel in. The keyword names match the C++ interface.
"""
from abc import ABC, abstractmethod


class AuditSink(ABC):
    """Where compliance/audit events go. Subclass to keep them somewhere."""

    @abstractmethod
    def record(self, operation: str, subject: str, detail: str = "") -> None:
        """Record one audit event.

        Args:
            operation: What happened, in the caller's own vocabulary (for
                example ``"phi_read"``, ``"key_rotate"``,
                ``"queue_rotated"``). There is deliberately no closed enum:
                each feature adds the names its domain needs.
            subject: Identifying metadata only (a message or field name, a
                patient or device id), never a field's value.
            detail: Optional extra non-sensitive context, such as an
                outcome.
        """


class NoOpAuditSink(AuditSink):
    """The default sink: records nothing and has no side effects."""

    def record(self, operation: str, subject: str, detail: str = "") -> None:
        """Discard the event."""
        return None


_DEFAULT_SINK = NoOpAuditSink()


def default_audit_sink() -> AuditSink:
    """Return the process-wide default sink (the same object on every call).

    Generated constructors default their ``audit_sink`` argument to this.
    """
    return _DEFAULT_SINK
