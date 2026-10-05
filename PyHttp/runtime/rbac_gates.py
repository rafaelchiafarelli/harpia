"""The RBAC access gates of the generated REST / SOAP / gRPC bindings (the
Python side of the C++ ``authz_<name>`` / RBAC ``auth_guard_op`` /
``rbac_check`` fills of ``Database/auth_gate.py``).

Hand-written, copied into a generated project as ``harpia_runtime.rbac_gates``
when at least one message gets the RBAC gate
(``Database.auth_gate.effective_rbac``: a ``protected`` message, or any
message not tagged ``open`` under a hardened profile). Each factory takes the
message name (the audit subject) and returns the gate type its transport
expects:

- :func:`rest_rbac_gate` → a :data:`harpia_runtime.http.rest.Gate`;
- :func:`soap_rbac_gate` → an
  :data:`harpia_runtime.http.soap_endpoint.OpGate` (it runs *after* the
  operation is parsed: ``get`` → read, ``set`` → create, ``update``,
  ``delete`` → remove; an unknown operation is not gated and gets the
  endpoint's "unknown operation" Fault, as in C++);
- :func:`grpc_rbac_gate` → a :data:`harpia_runtime.grpc_service.Gate`
  (``heartBeat`` is never gated).

The identity is a valid bearer session token's CN (``Authorization: Bearer``
header / ``authorization`` call metadata, :mod:`harpia_runtime.session`) or,
absent one, the verified mTLS client certificate's subject CN
(:func:`harpia_runtime.tls.cn_from_peercert` /
:func:`~harpia_runtime.tls.grpc_peer_cn`). A token that is presented but does
not verify is refused -- 401 / ``Client.Authentication`` Fault ``invalid
session token`` / ``UNAUTHENTICATED "invalid session token"`` -- and never
falls through to the certificate. :func:`harpia_runtime.rbac.decide` maps the
CN to a role and records one ``rbac_denied`` audit event per denial. Answers,
as C++:

==================  ==========================  ===========================
decision            REST / SOAP                 gRPC
==================  ==========================  ===========================
no identity         401 (SOAP: ``Client.        ``UNAUTHENTICATED
                    Authentication`` Fault      "unauthenticated"``
                    ``unauthenticated``)
wrong / no role     403 (Fault ``forbidden``)   ``PERMISSION_DENIED
                                                "forbidden"``
==================  ==========================  ===========================

Token issuance (:func:`register_session_routes`, :func:`issue_on_heartbeat`)
is the C++ ``register_session()`` / ``heartBeat`` one: only to a caller whose
certificate CN the transport verified; HTTP refuses an unmapped CN (403),
gRPC issues to any verified CN (its role may be ``none``), as C++.

**Python gRPC limitation:** in mixed mode (``CLIENT_CERT_REQUIRED = False``)
grpcio never requests a client certificate, so a gRPC caller presenting only
a certificate is anonymous there and an RBAC-gated RPC answers
``UNAUTHENTICATED`` (fail-closed), and ``heartBeat`` cannot issue tokens. A
bearer token obtained over HTTPS (``POST /session``, where the certificate is
verified) is accepted over gRPC in any mode.
"""
import json
import xml.etree.ElementTree as ET

import grpc

from harpia_runtime.compliance.audit_sink import AuditSink
from harpia_runtime.grpc_service import Gate as GrpcGate
from harpia_runtime.grpc_service import metadata
from harpia_runtime.http.rest import Gate as RestGate
from harpia_runtime.http.router import Request, Response, Router, text
from harpia_runtime.http.soap_endpoint import OpGate, xml_reply
from harpia_runtime.rbac import Decision, Operation, Role, decide, role_map
from harpia_runtime.session import Verdict, from_authorization, issue
from harpia_runtime.session_client import ISSUE_SESSION_METADATA, SESSION_TOKEN_METADATA
from harpia_runtime.soap import fault
from harpia_runtime.tls import cn_from_peercert, grpc_peer_cn

#: SOAP operation name → RBAC operation (others are not gated)
SOAP_OPERATIONS = {
    "get": Operation.read,
    "set": Operation.create,
    "update": Operation.update,
    "delete": Operation.remove,
}


def http_peer_cn(req: Request) -> str:
    """The verified client certificate's CN of an HTTP request, or ``""``."""
    return cn_from_peercert(req.peer.get("cert"))


def _identity(authorization: str, peer_cn: str) -> str | None:
    """The CN to gate on: the bearer token's when one verifies, else the
    certificate's; ``None`` when a token was presented and did not verify."""
    bearer = from_authorization(authorization)
    if not bearer.present:
        return peer_cn
    return bearer.cn if bearer.verdict is Verdict.ok else None


def rest_rbac_gate(subject: str, sink: AuditSink | None = None) -> RestGate:
    """RBAC for ``subject``'s REST routes (ops ``list`` / ``read`` /
    ``create`` / ``update`` / ``remove``): 401 / 403 with an empty body."""

    def gate(req: Request, op: str) -> Response | None:
        cn = _identity(req.header("Authorization"), http_peer_cn(req))
        if cn is None:
            return text(401)
        decision = decide(cn, Operation(op), subject, sink)
        if decision is Decision.allow:
            return None
        return text(401 if decision is Decision.unauthenticated else 403)
    return gate


def soap_rbac_gate(subject: str, sink: AuditSink | None = None) -> OpGate:
    """RBAC for ``subject``'s SOAP operations: a 401 / 403
    ``Client.Authentication`` Fault (``unauthenticated`` / ``forbidden``)."""

    def gate(req: Request, root: ET.Element, operation: str) -> Response | None:
        cn = _identity(req.header("Authorization"), http_peer_cn(req))
        if cn is None:
            return xml_reply(401, fault("invalid session token",
                                        "Client.Authentication"))
        op = SOAP_OPERATIONS.get(operation)
        if op is None:
            return None
        decision = decide(cn, op, subject, sink)
        if decision is Decision.allow:
            return None
        status = 401 if decision is Decision.unauthenticated else 403
        return xml_reply(status, fault(decision.value, "Client.Authentication"))
    return gate


def grpc_rbac_gate(subject: str, sink: AuditSink | None = None) -> GrpcGate:
    """RBAC for ``subject``'s gRPC RPCs (ops ``create`` / ``read`` /
    ``stream``)."""

    def gate(context: grpc.ServicerContext,
             op: str) -> tuple[grpc.StatusCode, str] | None:
        cn = _identity(metadata(context, "authorization") or "", grpc_peer_cn(context))
        if cn is None:
            return grpc.StatusCode.UNAUTHENTICATED, "invalid session token"
        decision = decide(cn, Operation(op), subject, sink)
        if decision is Decision.allow:
            return None
        if decision is Decision.unauthenticated:
            return grpc.StatusCode.UNAUTHENTICATED, "unauthenticated"
        return grpc.StatusCode.PERMISSION_DENIED, "forbidden"
    return gate


def issue_on_heartbeat(context: grpc.ServicerContext) -> None:
    """gRPC token issuance (the C++ RBAC ``heartBeat`` prologue): with
    ``harpia-issue-session`` request metadata and a verified client
    certificate, attach a token for its CN (and mapped role, ``none``
    included) as ``harpia-session-token`` trailing metadata. Never gates."""
    if metadata(context, ISSUE_SESSION_METADATA) is None:
        return
    cn = grpc_peer_cn(context)
    if not cn:
        return
    token = issue(cn, role_map().role_for(cn).value)
    if token:
        context.set_trailing_metadata(((SESSION_TOKEN_METADATA, token),))


def register_session_routes(router: Router, rest_base: str = "",
                            soap_base: str = "/soap") -> None:
    """``POST <rest_base>/session`` → ``{"token":"…","token_type":"Bearer"}``
    and ``POST <soap_base>/session`` → ``<sessionToken>…</sessionToken>``
    for a caller whose client certificate the transport verified (C++
    ``register_session``): no certificate → 401, unmapped CN → 403, sessions
    not configured → 503 (SOAP: a Fault without faultcode)."""

    def mint(req: Request) -> tuple[int, str]:
        cn = http_peer_cn(req)
        if not cn:
            return 401, "no client certificate"
        role = role_map().role_for(cn)
        if role is Role.none:
            return 403, "identity not authorized"
        token = issue(cn, role.value)
        if not token:
            return 503, "sessions not configured"
        return 200, token

    def rest(req: Request) -> Response:
        status, value = mint(req)
        if status != 200:
            return Response(status)
        body = '{"token":' + json.dumps(value) + ',"token_type":"Bearer"}'
        return Response(200, body.encode(), "application/json")

    def soap(req: Request) -> Response:
        status, value = mint(req)
        if status != 200:
            return xml_reply(status, fault(value))
        return xml_reply(200, "<sessionToken>" + value + "</sessionToken>")

    router.add("POST", rest_base + "/session", rest)
    router.add("POST", soap_base + "/session", soap)
