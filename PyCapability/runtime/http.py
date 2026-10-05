"""HTTP capability handshake, client side (Python port of
``HttpCapabilityAdapter/runtime/harpia_http_capability.h``,
message-versioning S5).

Hand-written, copied into a generated project as
``harpia_runtime.capability.http``::

    types = negotiate("10.0.0.5", 8080, "/api/v1", 2.0, on_legacy_peer=...)

``GET <base>/capabilities`` over a fresh plain-HTTP connection (``http.client``)
with ``timeout_s`` applied to the connect and to every read. Any failure --
refused, timed out, a non-200 status (a peer that predates the route), or a
body that isn't a ``capabilities_Response`` in protobuf JSON -- is the named
"legacy peer" outcome: ``on_legacy_peer()`` once, ``None``. The server side
is the generated ``capabilities_<roothash>_http.py`` route, registered by
``HttpServer``.
"""
import http.client
from collections.abc import Callable

from harpia_generated.protofiles.capabilities_service_pb2 import capabilities_Response
from harpia_runtime.json import from_json


def _noop() -> None:
    return None


def negotiate(host: str, port: int, base: str, timeout_s: float,
              on_legacy_peer: Callable[[], None] = _noop) -> set[str] | None:
    """The peer's advertised message-type names, or ``None`` (legacy peer)."""
    conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        conn.request("GET", base + "/capabilities", headers={"Connection": "close"})
        res = conn.getresponse()
        body = res.read()
        status = res.status
    except (OSError, http.client.HTTPException):
        on_legacy_peer()
        return None
    finally:
        conn.close()
    response = capabilities_Response()
    try:
        ok = status == 200 and from_json(body.decode("utf-8"), response)
    except UnicodeDecodeError:
        ok = False
    if not ok:
        on_legacy_peer()
        return None
    return set(response.message_types)
