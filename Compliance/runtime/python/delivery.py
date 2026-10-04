"""Delivery-guarantee runtime for ``critical`` messages (Python port of
``Compliance/runtime/harpia_delivery.h``, design-rules Rule 4a).

Hand-written, copied into a generated project as ``harpia_runtime.delivery``
when a ``critical`` transport-bearing message exists.

- :class:`Envelope`: ``seq`` (monotonic, assigned at the origin), ``crc``
  (CRC-32 IEEE of the payload, the C++ polynomial ``0xEDB88320`` --
  :func:`zlib.crc32`), ``delivery_timestamp_ms`` and the ``payload``.
- :func:`check_on_arrival`: :class:`Arrival` ``OK`` / ``CRC_MISMATCH`` /
  ``SEQ_GAP`` / ``SEQ_REGRESSED``.
- :class:`BoundedQueue`: fixed capacity; a push into a full queue drops the
  oldest envelope, returns :attr:`PushOutcome.ROTATED_OLDEST` and records
  ``("queue_rotated", subject, "dropped_seq=<n>")`` -- never a silent drop.
- :class:`Mailbox`: latest value only; overwriting an unsent value returns
  :attr:`PutOutcome.OVERWROTE` and records ``mailbox_overwritten``.

Not thread-safe (caller-synchronized), as in C++.
"""
import collections
import enum
import zlib
from dataclasses import dataclass

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink


def crc32(data: bytes) -> int:
    """CRC-32 IEEE 802.3 (reflected ``0xEDB88320``), equal to the C++ one."""
    return zlib.crc32(data) & 0xFFFFFFFF


@dataclass(frozen=True)
class Envelope:
    """A payload stamped at its origin with a sequence number and CRC."""

    seq: int
    crc: int
    payload: bytes
    #: epoch milliseconds at the origin; 0 = unset
    delivery_timestamp_ms: int = 0

    @classmethod
    def stamp(cls, seq: int, payload: bytes,
              delivery_timestamp_ms: int = 0) -> "Envelope":
        """Stamp ``payload`` with ``seq`` and its CRC."""
        return cls(seq, crc32(payload), payload, delivery_timestamp_ms)

    def crc_ok(self) -> bool:
        """Does the payload still match the origin CRC?"""
        return crc32(self.payload) == self.crc


class Arrival(enum.Enum):
    """What :func:`check_on_arrival` found."""

    OK = "ok"
    CRC_MISMATCH = "crc_mismatch"
    SEQ_GAP = "seq_gap"
    SEQ_REGRESSED = "seq_regressed"


def check_on_arrival(env: Envelope, expected: int) -> Arrival:
    """Classify an arriving envelope against the next expected ``seq``."""
    if not env.crc_ok():
        return Arrival.CRC_MISMATCH
    if env.seq < expected:
        return Arrival.SEQ_REGRESSED
    if env.seq > expected:
        return Arrival.SEQ_GAP
    return Arrival.OK


class PushOutcome(enum.Enum):
    """Result of :meth:`BoundedQueue.push`."""

    ACCEPTED = "accepted"
    ROTATED_OLDEST = "rotated_oldest"


class BoundedQueue:
    """A FIFO of at most ``capacity`` envelopes that rotates out the oldest."""

    def __init__(self, capacity: int, audit_sink: AuditSink | None = None,
                 subject: str = "delivery_queue") -> None:
        self._capacity = capacity if capacity > 0 else 1
        self._buf: collections.deque[Envelope] = collections.deque()
        self._audit = audit_sink or default_audit_sink()
        self._subject = subject
        self._rotations = 0
        self._last_rotated_seq = 0

    def push(self, env: Envelope) -> PushOutcome:
        """Enqueue; on a full queue drop (and audit) the oldest first."""
        outcome = PushOutcome.ACCEPTED
        if len(self._buf) >= self._capacity:
            self._last_rotated_seq = self._buf.popleft().seq
            self._rotations += 1
            outcome = PushOutcome.ROTATED_OLDEST
            self._audit.record("queue_rotated", self._subject,
                               f"dropped_seq={self._last_rotated_seq}")
        self._buf.append(env)
        return outcome

    def pop(self) -> Envelope | None:
        """Remove and return the oldest envelope."""
        return self._buf.popleft() if self._buf else None

    def peek(self) -> Envelope | None:
        """The oldest envelope, left in place."""
        return self._buf[0] if self._buf else None

    def size(self) -> int:
        """Envelopes queued."""
        return len(self._buf)

    def capacity(self) -> int:
        """The bound (at least 1)."""
        return self._capacity

    def empty(self) -> bool:
        """``True`` when nothing is queued."""
        return not self._buf

    def rotations(self) -> int:
        """How many envelopes were rotated out in total."""
        return self._rotations

    def last_rotated_seq(self) -> int:
        """``seq`` of the most recently rotated-out envelope (0: none)."""
        return self._last_rotated_seq


class PutOutcome(enum.Enum):
    """Result of :meth:`Mailbox.put`."""

    STORED = "stored"
    OVERWROTE = "overwrote"


class Mailbox:
    """A single latest-value slot."""

    def __init__(self, audit_sink: AuditSink | None = None,
                 subject: str = "delivery_mailbox") -> None:
        self._pending: Envelope | None = None
        self._audit = audit_sink or default_audit_sink()
        self._subject = subject
        self._overwrites = 0
        self._last_overwritten_seq = 0

    def put(self, env: Envelope) -> PutOutcome:
        """Store ``env``; superseding an unsent value is audited."""
        outcome = PutOutcome.STORED
        if self._pending is not None:
            self._last_overwritten_seq = self._pending.seq
            self._overwrites += 1
            outcome = PutOutcome.OVERWROTE
            self._audit.record("mailbox_overwritten", self._subject,
                               f"superseded_seq={self._last_overwritten_seq}")
        self._pending = env
        return outcome

    def take(self) -> Envelope | None:
        """Remove and return the pending value."""
        env, self._pending = self._pending, None
        return env

    def has_pending(self) -> bool:
        """Is a value waiting?"""
        return self._pending is not None

    def overwrites(self) -> int:
        """How many unsent values were superseded."""
        return self._overwrites

    def last_overwritten_seq(self) -> int:
        """``seq`` of the most recently superseded value (0: none)."""
        return self._last_overwritten_seq
