"""Client side of bearer sessions: obtain a token, then attach it.

Hand-written, copied into a generated project as
``harpia_runtime.session_client`` with :mod:`harpia_runtime.session`. Works
against a C++ or a Python server (same routes, same metadata names)::

    ctx = http_client_context(MtlsFiles(ca, cert, key))
    token = http_session_token("https://station:8443", ctx)
    urllib.request.Request(url, headers=bearer_header(token))
    stub.push(msg, metadata=bearer_metadata(token))

    # or over gRPC, from heartBeat (needs a server that sees the client cert):
    token = grpc_session_token(stub.heartBeat, users_HeartBeat())
"""
import json
import ssl
import urllib.error
import urllib.request
from typing import Any

#: gRPC request metadata asking ``heartBeat`` for a session token
ISSUE_SESSION_METADATA = "harpia-issue-session"
#: gRPC trailing metadata carrying the issued token
SESSION_TOKEN_METADATA = "harpia-session-token"


class SessionUnavailable(Exception):
    """The server did not issue a token (no / unmapped certificate, sessions
    not configured, or no token in the answer)."""


def http_session_token(base_url: str, context: ssl.SSLContext,
                       timeout: float = 10.0) -> str:
    """``POST <base_url>/session`` over mTLS and return the token
    (``base_url`` is the server's REST base, e.g. ``https://host:8443``)."""
    req = urllib.request.Request(base_url.rstrip("/") + "/session", data=b"",
                                 method="POST")
    try:
        with urllib.request.urlopen(req, context=context, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SessionUnavailable(f"session refused: HTTP {e.code}") from None
    except ValueError:
        raise SessionUnavailable("session answer is not JSON") from None
    token = body.get("token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise SessionUnavailable("no token in the session answer")
    return token


def grpc_session_token(heartbeat: Any, request: Any, timeout: float = 10.0) -> str:
    """Call a stub's ``heartBeat`` (pass ``stub.heartBeat`` and a
    ``<name>_HeartBeat``) asking for a token; return it from the trailing
    metadata."""
    _, call = heartbeat.with_call(request, metadata=((ISSUE_SESSION_METADATA, "1"),),
                                  timeout=timeout)
    for key, value in call.trailing_metadata() or ():
        if key == SESSION_TOKEN_METADATA:
            return str(value if isinstance(value, str) else value.decode("utf-8"))
    raise SessionUnavailable("heartBeat returned no session token")


def bearer_header(token: str) -> dict[str, str]:
    """HTTP headers presenting ``token``."""
    return {"Authorization": "Bearer " + token}


def bearer_metadata(token: str) -> tuple[tuple[str, str], ...]:
    """gRPC call metadata presenting ``token``."""
    return (("authorization", "Bearer " + token),)
