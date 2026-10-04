"""ZMQ transport for any harpia message (Python port of the C++
``zmq/<name>_<hash>_zmq.h`` sockets; one shared runtime, as the Java target
does).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.zmq``. A generated
``harpia_generated/zmq/<name>_<hash>_zmq.py`` exposes factories
(``new_sender`` / ``new_receiver`` / ``new_publisher`` /
``new_subscriber``) for the roles its modifiers ask for.

Wire format, identical to C++: **one frame holding the message's
``SerializeToString()``**, no envelope, so C++ and Python peers interoperate.

- :class:`Sender` -- PUSH (``connect``) or PUB (``bind``). Each send copies
  the message, stamps its ``ORIGINATOR*`` field (found by name prefix) with
  the sender's origin id, and sends it.
- :class:`Receiver` -- PULL (``bind``) or SUB (``connect`` + subscribe to
  everything). Parses one frame into a fresh message.

Calls block, as in C++ (no ``NOBLOCK``). Like a C++ socket, one instance
is not thread-safe.
"""
import itertools
import os
import secrets
from typing import Any, Generic, TypeVar

import zmq
from google.protobuf.message import DecodeError, Message

M = TypeVar("M", bound=Message)

_COUNTER = itertools.count()


def runtime_origin_id() -> str:
    """A runtime-unique sender id for many-to-* messages: ``<pid>-<n>-<hex>``
    (process id, per-process counter, 64 random bits), the C++ shape."""
    return f"{os.getpid()}-{next(_COUNTER)}-{secrets.randbits(64):x}"


def _origin_field(descriptor: Any) -> str | None:
    for field in descriptor.fields:
        if field.name.startswith("ORIGINATOR"):
            return str(field.name)
    return None


class Sender(Generic[M]):
    """A PUSH (``pub=False``, connects) or PUB (``pub=True``, binds) socket
    that stamps the origin id and sends one serialized frame per message."""

    def __init__(self, ctx: zmq.Context[Any], endpoint: str, origin: str,
                 *, pub: bool = False) -> None:
        self._origin = origin
        self._socket: zmq.Socket[bytes] = ctx.socket(zmq.PUB if pub else zmq.PUSH)
        if pub:
            self._socket.bind(endpoint)
        else:
            self._socket.connect(endpoint)

    @property
    def origin(self) -> str:
        """The id stamped into every sent message's ``ORIGINATOR*`` field."""
        return self._origin

    @property
    def socket(self) -> zmq.Socket[bytes]:
        """The underlying socket (for options, polling, closing)."""
        return self._socket

    def send(self, msg: M) -> bool:
        """Stamp a copy of ``msg`` and send it; ``False`` if not sent."""
        stamped = type(msg)()
        stamped.CopyFrom(msg)
        field = _origin_field(stamped.DESCRIPTOR)
        if field is not None:
            setattr(stamped, field, self._origin)
        try:
            self._socket.send(stamped.SerializeToString())
        except zmq.Again:
            return False
        return True

    #: PUB-side spelling of :meth:`send`, as in C++ ``publish``
    publish = send

    def close(self) -> None:
        """Close the socket (``linger=0``: never block on unsent frames)."""
        self._socket.close(linger=0)


class Receiver(Generic[M]):
    """A PULL (``sub=False``, binds) or SUB (``sub=True``, connects and
    subscribes to everything) socket yielding one message per frame."""

    def __init__(self, ctx: zmq.Context[Any], endpoint: str, message_type: type[M],
                 *, sub: bool = False) -> None:
        self._type = message_type
        self._socket: zmq.Socket[bytes] = ctx.socket(zmq.SUB if sub else zmq.PULL)
        if sub:
            self._socket.connect(endpoint)
            self._socket.setsockopt(zmq.SUBSCRIBE, b"")
        else:
            self._socket.bind(endpoint)

    @property
    def socket(self) -> zmq.Socket[bytes]:
        """The underlying socket (for options, polling, closing)."""
        return self._socket

    def recv(self) -> M | None:
        """Block for one frame; the parsed message, or ``None`` when no
        frame arrived (a receive timeout) or it doesn't parse."""
        try:
            frame = self._socket.recv()
        except zmq.Again:
            return None
        msg = self._type()
        try:
            msg.ParseFromString(frame)
        except DecodeError:
            return None
        return msg

    #: SUB-side spelling of :meth:`recv`, as in C++ ``receive``
    receive = recv

    def close(self) -> None:
        """Close the socket (``linger=0``)."""
        self._socket.close(linger=0)
