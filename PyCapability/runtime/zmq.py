"""ZMQ capability handshake, client side (Python port of
``ZmqCapabilityAdapter/runtime/harpia_zmq_capability.h``,
message-versioning S5).

Hand-written, copied into a generated project as
``harpia_runtime.capability.zmq``::

    types = negotiate(ctx, "tcp://peer:5560", 2.0, on_legacy_peer=...)

A fresh REQ socket per call (``RCVTIMEO`` = ``timeout_s``, ``linger=0`` so an
unanswered request never blocks teardown) sends a serialized
``capabilities_Request`` and reads one ``capabilities_Response``. ZMQ's
asynchronous connect means a send to an endpoint with nothing bound simply
queues; the receive timing out is the signal. Any failure is the named
"legacy peer" outcome: ``on_legacy_peer()`` once, ``None``. The server side
is the generated ``capabilities_<roothash>_zmq.py`` ``CapabilitiesResponder``.
"""
from collections.abc import Callable
from typing import Any

import zmq
from google.protobuf.message import DecodeError

from harpia_generated.protofiles.capabilities_service_pb2 import (
    capabilities_Request,
    capabilities_Response,
)


def _noop() -> None:
    return None


def negotiate(ctx: "zmq.Context[Any]", endpoint: str, timeout_s: float,
              on_legacy_peer: Callable[[], None] = _noop) -> set[str] | None:
    """The peer's advertised message-type names, or ``None`` (legacy peer)."""
    req = ctx.socket(zmq.REQ)
    try:
        req.setsockopt(zmq.RCVTIMEO, int(timeout_s * 1000))
        req.setsockopt(zmq.LINGER, 0)
        req.connect(endpoint)
        req.send(capabilities_Request().SerializeToString())
        reply = req.recv()
        response = capabilities_Response()
        response.ParseFromString(reply)
    except (zmq.ZMQError, DecodeError):
        on_legacy_peer()
        return None
    finally:
        req.close(linger=0)
    return set(response.message_types)
