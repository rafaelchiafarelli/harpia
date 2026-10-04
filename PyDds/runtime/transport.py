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

Each instance owns its ``DomainParticipant`` (domain 0) unless one is passed
in; share one participant between endpoints of a process when you have
many. The synchronous API is safe to call from one thread per endpoint.
"""
from typing import ClassVar, Generic, TypeVar, cast

from cyclonedds.core import (
    InstanceState,
    ReadCondition,
    SampleState,
    ViewState,
    WaitSet,
)
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.qos import Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.util import duration
from google.protobuf.message import DecodeError, Message

from harpia_runtime.dds.frame import Frame

M = TypeVar("M", bound=Message)


class _Endpoint(Generic[M]):
    #: the protobuf message class
    MESSAGE: ClassVar[type[Message]]
    #: the harpia message name (the frame key and the default topic)
    NAME: ClassVar[str]

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None) -> None:
        self.participant = (participant if participant is not None
                            else DomainParticipant())
        self.topic: Topic[Frame] = Topic(self.participant, topic_name or self.NAME,
                                         Frame)

    @classmethod
    def writer_qos(cls) -> Qos | None:
        """Writer QoS (``None``: Cyclone's defaults)."""
        return None

    @classmethod
    def reader_qos(cls) -> Qos | None:
        """Reader QoS (``None``: Cyclone's defaults)."""
        return None


class Publisher(_Endpoint[M]):
    """Writes ``M`` messages as frames."""

    def __init__(self, participant: DomainParticipant | None = None,
                 topic_name: str | None = None) -> None:
        super().__init__(participant, topic_name)
        self.writer: DataWriter[Frame] = DataWriter(self.participant, self.topic,
                                                   qos=self.writer_qos())

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
        self.reader: DataReader[Frame] = DataReader(self.participant, self.topic,
                                                   qos=self.reader_qos())
        self._waitset = WaitSet(self.participant)
        self._waitset.attach(ReadCondition(
            self.reader, SampleState.Any | ViewState.Any | InstanceState.Any))

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
