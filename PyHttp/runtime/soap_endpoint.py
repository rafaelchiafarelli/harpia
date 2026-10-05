"""SOAP-over-HTTP endpoint over a generated DAO (the Python side of the C++
``soap/<name>_<hash>_soap.h``).

Hand-written, copied into a generated project as
``harpia_runtime.http.soap_endpoint``. One route, ``POST <base>/<name>``,
answering ``text/xml`` with the C++ envelopes and status codes:

1. unparsable envelope (or one with a DTD) → 400, empty body;
2. the *early* gate (flat: ``<credentials><user/><pswd/></credentials>`` in
   the SOAP Header) → 401 with a ``Client.Authentication`` Fault;
3. no operation element in the Body → 400;
4. the *operation* gate (hardened variants, later tasks);
5. pooled connection: exhausted / reconnect failure → 503 + Fault;
6. dispatch on the operation's local name -- ``get`` (``<id>``;
   ``getResponse`` or a "not found" Fault), ``set`` / ``update`` (the
   message element; ``<ok>true|false</ok>``, 400 when it doesn't decode),
   ``delete`` (``<id>``); anything else → an "unknown operation" Fault.
   Faults other than authentication are **200**, as in C++.

As in C++, ``update`` / ``delete`` answer ``<ok>true</ok>`` unless the
database errors (also when no row matched); ``get`` of a row that can't be
read is "not found".
"""
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from google.protobuf.message import Message

from harpia_runtime.db.pool import ConnectionPool, PoolExhausted, PoolReconnectFailed
from harpia_runtime.http.router import Request, Response, Router
from harpia_runtime.soap import (
    child_text,
    envelope,
    fault,
    find_child,
    find_operation,
    parse_envelope,
)
from harpia_runtime.xml import from_xml_element, to_xml

#: an early gate sees the request and the parsed envelope root
EarlyGate = Callable[[Request, ET.Element], Response | None]
#: an operation gate also sees the operation name
OpGate = Callable[[Request, ET.Element, str], Response | None]

_ATOLL = re.compile(r"\s*([+-]?\d+)")


def xml_reply(status: int, body: str) -> Response:
    """A ``text/xml`` SOAP envelope around ``body``."""
    return Response(status, envelope(body).encode(), "text/xml")


def _id(op: ET.Element) -> int:
    el = op.find("id")
    m = _ATOLL.match((el.text or "") if el is not None else "")
    return int(m.group(1)) if m else 0


def _decode(op: ET.Element, message_type: type[Message]) -> Message | None:
    if len(op) == 0:
        return None
    msg = message_type()
    try:
        return msg if from_xml_element(op[0], msg) else None
    except Exception:
        return None


def register_soap(router: Router, pool: ConnectionPool, base: str, name: str,
                  dao_class: Any, message_type: type[Message],
                  early_gate: EarlyGate | None = None,
                  op_gate: OpGate | None = None) -> None:
    """Register ``POST <base>/<name>``."""

    def handler(req: Request) -> Response:
        root = parse_envelope(req.body)
        if root is None:
            return Response(400)
        if early_gate is not None and (refusal := early_gate(req, root)) is not None:
            return refusal
        soap_req = find_operation(root)
        if soap_req is None:
            return Response(400)
        if op_gate is not None and (
                refusal := op_gate(req, root, soap_req.operation)) is not None:
            return refusal
        try:
            with pool.borrow() as conn:
                return dispatch(soap_req.operation, soap_req.op, dao_class(conn))
        except PoolExhausted:
            return xml_reply(503, fault("db pool exhausted"))
        except PoolReconnectFailed:
            return xml_reply(503, fault("db reconnect failed"))

    def ok(op_name: str, run: Callable[[], object]) -> Response:
        try:
            result = run()
            good = result is not False
        except Exception:
            good = False
        flag = "true" if good else "false"
        return xml_reply(200, f"<{op_name}Response><ok>{flag}</ok></{op_name}Response>")

    def dispatch(operation: str, op: ET.Element, dao: Any) -> Response:
        if operation == "get":
            msg = message_type()
            try:
                found = dao.read(_id(op), msg)
            except Exception:
                found = False
            if not found:
                return xml_reply(200, fault("not found"))
            return xml_reply(200, "<getResponse>" + to_xml(msg) + "</getResponse>")
        if operation in ("set", "update"):
            decoded = _decode(op, message_type)
            if decoded is None:
                return Response(400)
            if operation == "set":
                return ok("set", lambda: dao.create(decoded))
            return ok("update", lambda: (dao.update(decoded), True)[1])
        if operation == "delete":
            return ok("delete", lambda: (dao.remove(_id(op)), True)[1])
        return xml_reply(200, fault("unknown operation"))

    router.add("POST", f"{base}/{name}", handler)


def flat_soap_gate(user: str, password: str) -> EarlyGate:
    """The flat generated credential in the SOAP Header (C++ ``authorized_``)."""

    def gate(req: Request, root: ET.Element) -> Response | None:
        cred = find_child(find_child(root, "Header"), "credentials")
        if cred is not None and child_text(cred, "user") == user \
                and child_text(cred, "pswd") == password:
            return None
        return xml_reply(401, fault("unauthorized", "Client.Authentication"))
    return gate
