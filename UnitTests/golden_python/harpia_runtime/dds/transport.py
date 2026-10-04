"""DDS publish/subscribe of harpia messages over the shared
:class:`~harpia_runtime.dds.frame.Frame` topic type (the Python side of the
C++ ``dds/<name>_<hash>_dds.h`` ``<name>_publisher`` / ``<name>_subscriber``).

Hand-written, copied into a generated project as
``harpia_runtime.dds.transport``. A generated
``harpia_generated/dds/<name>_<hash>_dds.py`` subclasses :class:`Publisher`
and :class:`Subscriber` with its message class, name and topic:

- ``publish(msg)`` serializes the protobuf and writes
  ``Frame(message_type=<name>, payload=<bytes>)`` to the topic (default: the
  message name) -- the same frame a C++ publisher writes, so either side
  reads the other;
- ``receive(timeout)`` takes **one** sample (oldest first, so repeated calls
  drain a batch in order), waiting up to ``timeout`` seconds for one, and
  parses it; ``None`` when nothing arrived or the payload did not parse
  (the sample is consumed either way, as in C++).

QoS (py-dds task 2) is the C++ mapping (design-rules §4), chosen per message
at generation time from ``critical`` (the generated class sets
``CRITICAL``): a ``critical`` message is ordered and complete --
``Reliable(10 s)`` + ``KeepAll`` + ``ResourceLimits(max_samples=QUEUE_DEPTH)``
(128, the ZMQ queue capacity) -- and anything else is latest-value-only --
``BestEffort`` + ``KeepLast(1)``. The reader mirrors the writer, so a C++
writer of the same message matches a Python reader and vice versa.
``Durability`` stays ``Volatile`` (C++'s open question; not decided here).

Each instance owns its ``DomainParticipant`` (domain 0) unless one is passed
in; share one participant between endpoints of a process when you have
many. ``matched_subscribers()`` / ``matched_publishers()`` report the
current match count (as the C++ classes). The synchronous API is safe to
call from one thread per endpoint.
"""
from typing import ClassVar, Generic, TypeVar, cast

from cyclonedds.core import (
    InstanceState,
    Listener,
    ReadCondition,
    SampleState,
    ViewState,
    WaitSet,
)
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.qos import Policy, Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.util import duration
from google.protobuf.message import DecodeError, Message

from harpia_runtime.dds.frame import Frame

M = TypeVar("M", bound=Message)

#: the default ``critical`` history bound (C++ ``DdsAdapter.QUEUE_DEPTH``)
QUEUE_DEPTH = 128


def critical_qos(depth: int = QUEUE_DEPTH) -> Qos:
    """§4a ordered/complete: reliable, keep-all, at most ``depth`` samples."""
    return Qos(Policy.Reliability.Reliable(duration(seconds=10)),
               Policy.History.KeepAll,
               Policy.ResourceLimits(max_samples=depth, max_instances=-1,
                                     max_samples_per_instance=-1))


def latest_qos() -> Qos:
    """§4b latest-value-only: best-effort, keep-last(1)."""
    return Qos(Policy.Reliability.BestEffort, Policy.History.KeepLast(1))


class _Endpoint(Generic[M]):
    #: the protobuf message class
    MESSAGE: ClassVar[type[Message]]
    #: the harpia message name (the frame key and the default topic)
    NAME: ClassVar[str]
    #: the message is ``critical`` (selects the QoS profile)
    CRITICAL: ClassVar[bool] = False
    #: history bound of a ``critical`` message
    QUEUE_DEPTH: ClassVar[int] = QUEUE_DEPTH

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None) -> None:
        self.participant = (participant if participant is not None
                            else DomainParticipant())
        self.topic: Topic[Frame] = Topic(self.participant, topic_name or self.NAME,
                                         Frame)
        self._matched = 0

    def _on_matched(self, entity: object, status: object) -> None:
        self._matched = int(getattr(status, "current_count", 0))

    @classmethod
    def writer_qos(cls) -> Qos:
        """The writer QoS for this message (see the module docstring)."""
        return critical_qos(cls.QUEUE_DEPTH) if cls.CRITICAL else latest_qos()

    @classmethod
    def reader_qos(cls) -> Qos:
        """The reader QoS -- mirrors the writer."""
        return cls.writer_qos()


class Publisher(_Endpoint[M]):
    """Writes ``M`` messages as frames."""

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None) -> None:
        super().__init__(participant, topic_name)
        self.writer: DataWriter[Frame] = DataWriter(
            self.participant, self.topic, qos=self.writer_qos(),
            # cyclonedds' Listener constructor is untyped
            listener=Listener(  # type: ignore[no-untyped-call]
                on_publication_matched=self._on_matched))

    def matched_subscribers(self) -> int:
        """Readers currently matched."""
        return self._matched

    def publish(self, msg: M) -> bool:
        """Serialize ``msg`` and write it; ``False`` if it doesn't serialize."""
        try:
            payload = msg.SerializeToString()
        except Exception:
            return False
        self.writer.write(Frame(message_type=self.NAME, payload=payload))
        return True


class Subscriber(_Endpoint[M]):
    """Takes frames and parses them as ``M``."""

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None) -> None:
        super().__init__(participant, topic_name)
        self.reader: DataReader[Frame] = DataReader(
            self.participant, self.topic, qos=self.reader_qos(),
            listener=Listener(  # type: ignore[no-untyped-call]
                on_subscription_matched=self._on_matched))
        self._waitset = WaitSet(self.participant)
        self._waitset.attach(ReadCondition(
            self.reader, SampleState.Any | ViewState.Any | InstanceState.Any))

    def matched_publishers(self) -> int:
        """Writers currently matched."""
        return self._matched

    def receive(self, timeout: float = 0.0) -> M | None:
        """The oldest available message, waiting up to ``timeout`` seconds."""
        samples = self.reader.take(N=1)
        if not samples and timeout > 0:
            self._waitset.wait(duration(seconds=timeout))
            samples = self.reader.take(N=1)
        for frame in samples:
            info = getattr(frame, "sample_info", None)
            if info is not None and not info.valid_data:
                continue
            msg = self.MESSAGE()
            try:
                msg.ParseFromString(bytes(frame.payload))
            except DecodeError:
                return None
            return cast(M, msg)
        return None
