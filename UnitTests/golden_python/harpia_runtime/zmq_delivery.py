"""The queued sender of a ``critical`` message type (the Python side of the
C++ ``sender_critical.tmpl``).

Hand-written, copied into a generated project as
``harpia_runtime.zmq_delivery`` when a ``critical`` transport-bearing message
exists. :meth:`QueuedSender.send` / ``publish`` never touches the socket: it
stamps the serialized message into an :class:`~harpia_runtime.delivery.Envelope`
(CRC + monotonic ``seq`` from 1) and enqueues it in a
:class:`~harpia_runtime.delivery.BoundedQueue`. :meth:`QueuedSender.flush`
puts queued payloads on the wire oldest-first and stops at the first socket
failure, so a transient outage costs latency, not messages; an overflow
rotates the oldest entry with a ``queue_rotated`` audit.

**Only the payload goes on the wire** (one serialized-message frame, as for
any other sender); the envelope stays local, as in C++.
"""
from typing import Any, TypeVar

import zmq
from google.protobuf.message import EncodeError, Message

from harpia_runtime.compliance.audit_sink import AuditSink
from harpia_runtime.delivery import BoundedQueue, Envelope, PushOutcome
from harpia_runtime.zmq import CurveClientKeys, CurveServerKeys, Sender

M = TypeVar("M", bound=Message)


class QueuedSender(Sender[M]):
    """A :class:`~harpia_runtime.zmq.Sender` whose sends are queued."""

    def __init__(self, ctx: zmq.Context[Any], endpoint: str, origin: str,
                 *, pub: bool = False,
                 curve: CurveServerKeys | CurveClientKeys | None = None,
                 zap: bool = False, queue_capacity: int = 128,
                 audit_sink: AuditSink | None = None, subject: str = "") -> None:
        super().__init__(ctx, endpoint, origin, pub=pub, curve=curve, zap=zap)
        self._queue = BoundedQueue(queue_capacity, audit_sink,
                                   subject or "delivery_queue")
        self._next_seq = 1

    def send(self, msg: M) -> PushOutcome | None:  # type: ignore[override]
        """Stamp and enqueue ``msg``; ``None`` only if it can't serialize."""
        try:
            payload = self._stamped(msg).SerializeToString()
        except EncodeError:
            return None
        outcome = self._queue.push(Envelope.stamp(self._next_seq, payload))
        self._next_seq += 1
        return outcome

    #: PUB-side spelling of :meth:`send`
    publish = send  # type: ignore[assignment]

    def flush(self) -> int:
        """Send queued payloads oldest-first until the queue is empty or the
        socket fails; returns how many went on the wire."""
        sent = 0
        while (env := self._queue.peek()) is not None:
            try:
                self.socket.send(env.payload)
            except zmq.ZMQError:
                break
            self._queue.pop()
            sent += 1
        return sent

    def pending(self) -> int:
        """Envelopes waiting for :meth:`flush`."""
        return self._queue.size()

    def queue(self) -> BoundedQueue:
        """The underlying queue (rotations, last rotated seq, ...)."""
        return self._queue
