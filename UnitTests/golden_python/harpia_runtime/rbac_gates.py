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

The identity is the verified mTLS client certificate's subject CN
(:func:`harpia_runtime.tls.cn_from_peercert` /
:func:`~harpia_runtime.tls.grpc_peer_cn`); :func:`harpia_runtime.rbac.decide`
maps it to a role and records one ``rbac_denied`` audit event per denial.
Answers, as C++:

==================  ==========================  ===========================
decision            REST / SOAP                 gRPC
==================  ==========================  ===========================
no identity         401 (SOAP: ``Client.        ``UNAUTHENTICATED
                    Authentication`` Fault      "unauthenticated"``
                    ``unauthenticated``)
wrong / no role     403 (Fault ``forbidden``)   ``PERMISSION_DENIED
                                                "forbidden"``
==================  ==========================  ===========================

**Python gRPC limitation:** in mixed mode (``CLIENT_CERT_REQUIRED = False``)
grpcio never requests a client certificate, so every gRPC caller is
anonymous there and an RBAC-gated RPC answers ``UNAUTHENTICATED`` -- it fails
closed. Run the gRPC server with client certificates required to serve RBAC
messages over gRPC.
"""
import xml.etree.ElementTree as ET

import grpc

from harpia_runtime.compliance.audit_sink import AuditSink
from harpia_runtime.grpc_service import Gate as GrpcGate
from harpia_runtime.http.rest import Gate as RestGate
from harpia_runtime.http.router import Request, Response, text
from harpia_runtime.http.soap_endpoint import OpGate, xml_reply
from harpia_runtime.rbac import Decision, Operation, decide
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


def rest_rbac_gate(subject: str, sink: AuditSink | None = None) -> RestGate:
    """RBAC for ``subject``'s REST routes (ops ``list`` / ``read`` /
    ``create`` / ``update`` / ``remove``): 401 / 403 with an empty body."""

    def gate(req: Request, op: str) -> Response | None:
        decision = decide(http_peer_cn(req), Operation(op), subject, sink)
        if decision is Decision.allow:
            return None
        return text(401 if decision is Decision.unauthenticated else 403)
    return gate


def soap_rbac_gate(subject: str, sink: AuditSink | None = None) -> OpGate:
    """RBAC for ``subject``'s SOAP operations: a 401 / 403
    ``Client.Authentication`` Fault (``unauthenticated`` / ``forbidden``)."""

    def gate(req: Request, root: ET.Element, operation: str) -> Response | None:
        op = SOAP_OPERATIONS.get(operation)
        if op is None:
            return None
        decision = decide(http_peer_cn(req), op, subject, sink)
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
        decision = decide(grpc_peer_cn(context), Operation(op), subject, sink)
        if decision is Decision.allow:
            return None
        if decision is Decision.unauthenticated:
            return grpc.StatusCode.UNAUTHENTICATED, "unauthenticated"
        return grpc.StatusCode.PERMISSION_DENIED, "forbidden"
    return gate
