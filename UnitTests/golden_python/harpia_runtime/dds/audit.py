"""phi-over-DDS publish audit (py-dds task 4; the Python side of the C++
``DdsAdapter`` ``{audit_*}`` publisher slots).

Hand-written, copied into a generated project as ``harpia_runtime.dds.audit``
(with the audit sink) only when some ``dds`` message has a ``phi`` field --
as C++ copies ``harpia_audit_sink.h`` only then. That message's generated
publisher subclasses :class:`AuditedPublisher`: it takes ``audit_sink``
(default :func:`~harpia_runtime.compliance.audit_sink.default_audit_sink`)
and every ``publish()`` records exactly one value-free event **after** the
write -- ``("phi_publish", <message name>, <comma-joined phi field names>)``,
the C++ subject and detail. The subscriber records nothing (no
``phi_receive``, as C++). A message without ``phi`` keeps the plain
:class:`~harpia_runtime.dds.transport.Publisher` (no audit parameter).
"""
from typing import ClassVar

from cyclonedds.domain import DomainParticipant

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink
from harpia_runtime.dds.transport import M, Publisher


class AuditedPublisher(Publisher[M]):
    """A :class:`~harpia_runtime.dds.transport.Publisher` of a message with
    ``phi`` fields."""

    #: the message's ``phi`` field names (the audit detail, never values)
    PHI_FIELDS: ClassVar[tuple[str, ...]]

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None,
                 audit_sink: AuditSink | None = None) -> None:
        super().__init__(participant, topic_name)
        self.audit_sink = audit_sink or default_audit_sink()

    def publish(self, msg: M) -> bool:
        """Write ``msg``, then record one ``phi_publish`` event."""
        if not super().publish(msg):
            return False
        self.audit_sink.record("phi_publish", self.NAME, ",".join(self.PHI_FIELDS))
        return True
