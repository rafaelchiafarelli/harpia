"""The ``stream`` consumer lifecycle (Python port of the C++
``<name>_stream`` in ``ZmqAdapter/templates/stream.tmpl``, process.md 13.2).

Hand-written, copied into a generated project as
``harpia_runtime.zmq_stream`` when a ``stream`` message exists; each such
message gets a generated ``<name>_stream`` subclass of :class:`Stream`.

A SUB-socket consumer with an explicit lifecycle:

- :meth:`Stream.setup` returns :attr:`StreamStatus.INVALID` and opens
  nothing for a config :func:`stream_config_valid` rejects;
- :meth:`Stream.read` is always timed (``RCVTIMEO``): ``OK`` + message,
  ``TIMEOUT``, ``STOPPED`` after :meth:`Stream.stop`, or ``INVALID``
  (before setup, after a teardown below, or for an undecodable frame);
- :meth:`Stream.stop` is idempotent and returns ``STOPPED``;
- two **synchronous** teardowns (no timer thread), checked inside
  ``read()`` / ``stop()``, each closing the socket and latching
  ``INVALID``: *reclamation* after ``reclaim_after_ms`` with no inbound
  frame at all (checked first), and the *watchdog* after
  ``stop_deadline_ms`` with no usable message. A stream fed garbage keeps
  reclamation away but still trips the watchdog.

Sockets close with ``linger=0`` (also on ``__exit__`` / collection).
Deadlines use :func:`time.monotonic`. Not thread-safe (caller-synchronized).
"""
import enum
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Any, ClassVar, Generic, TypeVar

import zmq
from google.protobuf.message import DecodeError, Message

from harpia_runtime.zmq import CurveClientKeys, _apply_client

M = TypeVar("M", bound=Message)


class StreamStatus(enum.Enum):
    """Outcome of a stream lifecycle call."""

    OK = "ok"
    INVALID = "invalid"
    TIMEOUT = "timeout"
    STOPPED = "stopped"


@dataclass(frozen=True)
class StreamConfig:
    """Passed to :meth:`Stream.setup`; durations in milliseconds."""

    #: ``tcp://`` | ``ipc://`` | ``inproc://``
    endpoint: str
    #: SUB filter (``""`` = every message)
    topic: str = ""
    #: default per-read timeout; ``read(timeout_ms)`` overrides it
    read_timeout_ms: int = 1000
    #: no usable message for this long → the watchdog kills the stream
    stop_deadline_ms: int = 30000
    #: no inbound frame at all for this long → the connection is reclaimed
    reclaim_after_ms: int = 60000
    #: per-read record cap (process.md: the known maximum number of records)
    max_records: int = 10000


def stream_config_valid(c: StreamConfig) -> bool:
    """The C++ checks: an endpoint with a ``tcp://`` / ``ipc://`` /
    ``inproc://`` scheme, positive read timeout and stop deadline, and a
    non-zero record cap."""
    if not c.endpoint.startswith(("tcp://", "ipc://", "inproc://")):
        return False
    return c.read_timeout_ms > 0 and c.stop_deadline_ms > 0 and c.max_records != 0


@dataclass(frozen=True)
class ReadResult(Generic[M]):
    """``msg`` is set only when ``status`` is ``OK``."""

    status: StreamStatus
    msg: M | None = None


def _elapsed_ms(since: float) -> float:
    return (time.monotonic() - since) * 1000.0


class Stream(Generic[M]):
    """The lifecycle consumer of one ``stream`` message type."""

    #: the message type read from the wire (set by the generated subclass)
    MESSAGE: ClassVar[type[Message]]

    def __init__(self, ctx: zmq.Context[Any]) -> None:
        self._ctx = ctx
        self._socket: zmq.Socket[bytes] | None = None
        self._config = StreamConfig("")
        self._state = StreamStatus.INVALID  # unusable until setup() succeeds
        self._last_read_ok = 0.0
        self._last_activity = 0.0

    def setup(self, config: StreamConfig,
              curve: CurveClientKeys | None = None) -> StreamStatus:
        """Open the SUB connection (``INVALID`` for a bad config)."""
        if not stream_config_valid(config):
            return StreamStatus.INVALID
        self._kill()
        self._config = config
        sock: zmq.Socket[bytes] = self._ctx.socket(zmq.SUB)
        _apply_client(sock, curve)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, config.read_timeout_ms)
        sock.connect(config.endpoint)
        sock.setsockopt(zmq.SUBSCRIBE, config.topic.encode())
        self._socket = sock
        self._state = StreamStatus.OK
        self._last_read_ok = self._last_activity = time.monotonic()
        return StreamStatus.OK

    def read(self, timeout_ms: int | None = None) -> ReadResult[M]:
        """A timed read; never blocks past the timeout."""
        if self._state is StreamStatus.STOPPED:
            return ReadResult(StreamStatus.STOPPED)
        if self._state is not StreamStatus.OK or self._socket is None:
            return ReadResult(StreamStatus.INVALID)
        if self._reclaim_if_dead():
            return ReadResult(StreamStatus.INVALID)
        if _elapsed_ms(self._last_read_ok) >= self._config.stop_deadline_ms:
            self._kill()
            self._state = StreamStatus.INVALID
            return ReadResult(StreamStatus.INVALID)
        wait = self._config.read_timeout_ms if timeout_ms is None else timeout_ms
        self._socket.setsockopt(zmq.RCVTIMEO, max(wait, 1))
        try:
            frame = self._socket.recv()
        except zmq.Again:
            return ReadResult(StreamStatus.TIMEOUT)
        self._last_activity = time.monotonic()  # any frame is liveness
        msg = self.MESSAGE()
        try:
            msg.ParseFromString(frame)
        except DecodeError:
            return ReadResult(StreamStatus.INVALID)
        self._last_read_ok = time.monotonic()
        return ReadResult(StreamStatus.OK, msg)  # type: ignore[arg-type]

    def stop(self) -> StreamStatus:
        """Close the connection; idempotent, always ``STOPPED``."""
        self._reclaim_if_dead()
        self._kill()
        if self._state is not StreamStatus.INVALID:
            self._state = StreamStatus.STOPPED
        return StreamStatus.STOPPED

    def state(self) -> StreamStatus:
        """The latched lifecycle state."""
        return self._state

    def config(self) -> StreamConfig:
        """The config of the last successful :meth:`setup`."""
        return self._config

    @property
    def socket(self) -> zmq.Socket[bytes] | None:
        """The SUB socket while open."""
        return self._socket

    def _reclaim_if_dead(self) -> bool:
        if (self._socket is not None and self._state is StreamStatus.OK
                and _elapsed_ms(self._last_activity) >= self._config.reclaim_after_ms):
            self._kill()
            self._state = StreamStatus.INVALID
            return True
        return False

    def _kill(self) -> None:
        if self._socket is not None:
            self._socket.close(linger=0)
            self._socket = None

    def __enter__(self) -> "Stream[M]":
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, tb: TracebackType | None) -> None:
        self.stop()

    def __del__(self) -> None:
        if getattr(self, "_socket", None) is not None:
            self._reclaim_if_dead()
            self._kill()
