"""gRPC capability handshake, client side (Python port of
``GrpcCapabilityAdapter/runtime/harpia_capability.h``, message-versioning S5).

Hand-written, copied into a generated project as
``harpia_runtime.capability.grpc``::

    types = negotiate(channel, 2.0, on_legacy_peer=lambda: ...)
    if types is not None:
        ...  # the peer's real, current message-type set

Any non-OK outcome -- the peer never registered ``capabilities_Service``
(``UNIMPLEMENTED``), didn't answer within ``timeout_s``
(``DEADLINE_EXCEEDED``), or any other transport failure -- is the same named
"legacy peer" outcome: ``on_legacy_peer()`` runs exactly once and the result
is ``None``, never an empty set and never a hang. The server side is the
generated ``harpia_generated/capability/capabilities_<roothash>_grpc.py``.
"""
from collections.abc import Callable

import grpc

from harpia_generated.protofiles import capabilities_service_pb2 as pb2
from harpia_generated.protofiles import capabilities_service_pb2_grpc as pb2_grpc


def _noop() -> None:
    return None


def negotiate(channel: grpc.Channel, timeout_s: float,
              on_legacy_peer: Callable[[], None] = _noop) -> set[str] | None:
    """The peer's advertised message-type names, or ``None`` (legacy peer)."""
    # protoc's grpc plugin emits untyped code
    stub = pb2_grpc.capabilities_ServiceStub(channel)  # type: ignore[no-untyped-call]
    try:
        response = stub.GetCapabilities(pb2.capabilities_Request(), timeout=timeout_s)
    except grpc.RpcError:
        on_legacy_peer()
        return None
    return set(response.message_types)
