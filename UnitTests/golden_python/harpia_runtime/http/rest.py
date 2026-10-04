"""REST CRUD over a generated DAO (the Python side of the C++
``rest/<name>_<hash>_rest.h``).

Hand-written, copied into a generated project as
``harpia_runtime.http.rest``. A generated
``harpia_generated/rest/<name>_<hash>_rest.py`` calls :func:`register_crud`
with its DAO, message type, pagination default and access gate. Routes and
answers match C++, so one client works against either server:

=================================  ======================================
``GET    <base>/<name>``           200 list (``?limit=&offset=``; JSON
                                   ``[...]`` or XML ``<list>...</list>``)
``GET    <base>/<name>/<id>``      200 message, 404 when missing
``POST   <base>/<name>``           201; 400 unparsable body; 500 DB error
``PUT    <base>/<name>/<id>``      204 (as C++: also when no row matched);
                                   400 / 500
``DELETE <base>/<name>/<id>``      204 (as C++: also when no row matched)
=================================  ======================================

A body is XML when ``Content-Type`` mentions ``xml``, else JSON; a response
is XML when ``Accept`` mentions ``xml``. The list is paginated when
``limit`` (or the message's ``pagination[size]`` default) is positive.
The gate runs first (its ``Response`` is returned as-is); then each request
borrows one pooled connection: exhausted pool → 503 ``db pool exhausted``,
reconnect failure → 503 ``db reconnect failed``, any other error → 500.
"""
from collections.abc import Callable
from typing import Any

from google.protobuf.message import Message

from harpia_runtime.db.pool import ConnectionPool, PoolExhausted, PoolReconnectFailed
from harpia_runtime.http.router import (
    Request,
    Response,
    Router,
    body_is_xml,
    text,
    wants_xml,
)
from harpia_runtime.json import from_json, to_json
from harpia_runtime.xml import from_xml, to_xml

#: returns ``None`` to let the request through, or the refusal to send;
#: called with the request and the CRUDL operation name
Gate = Callable[[Request, str], Response | None]


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _serialize(req: Request, msg: Message) -> Response:
    if wants_xml(req):
        return Response(200, to_xml(msg).encode(), "application/xml")
    return Response(200, to_json(msg).encode(), "application/json")


def _parse(req: Request, msg: Message) -> bool:
    try:
        body = req.body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return from_xml(body, msg) if body_is_xml(req) else from_json(body, msg)


def register_crud(router: Router, pool: ConnectionPool, base: str, name: str,
                  dao_class: Any, message_type: type[Message], gate: Gate,
                  default_limit: int = 0) -> None:
    """Register the five CRUD routes of ``name`` under ``base``."""
    col = f"{base}/{name}"
    item = col + "/<id>"

    def guarded(op: str, run: Callable[[Request, Any], Response]
                ) -> Callable[[Request], Response]:
        def handler(req: Request) -> Response:
            refusal = gate(req, op)
            if refusal is not None:
                return refusal
            try:
                with pool.borrow() as conn:
                    return run(req, dao_class(conn))
            except PoolExhausted:
                return text(503, "db pool exhausted")
            except PoolReconnectFailed:
                return text(503, "db reconnect failed")
            except Exception:
                return text(500)
        return handler

    def list_rows(req: Request, dao: Any) -> Response:
        limit = _int(req.query.get("limit", ""), default_limit)
        if limit > 0:
            rows = dao.list(max(_int(req.query.get("offset", ""), 0), 0), limit)
        else:
            rows = dao.list()
        if wants_xml(req):
            body = "<list>" + "".join(to_xml(r) for r in rows) + "</list>"
            return Response(200, body.encode(), "application/xml")
        body = "[" + ",".join(to_json(r) for r in rows) + "]"
        return Response(200, body.encode(), "application/json")

    def read(req: Request, dao: Any) -> Response:
        msg = message_type()
        if not dao.read(req.params["id"], msg):
            return text(404)
        return _serialize(req, msg)

    def create(req: Request, dao: Any) -> Response:
        msg = message_type()
        if not _parse(req, msg):
            return text(400)
        dao.create(msg)
        return text(201)

    def update(req: Request, dao: Any) -> Response:
        msg = message_type()
        if not _parse(req, msg):
            return text(400)
        dao.update(msg)
        return text(204)

    def remove(req: Request, dao: Any) -> Response:
        dao.remove(req.params["id"])
        return text(204)

    router.add("GET", col, guarded("list", list_rows))
    router.add("GET", item, guarded("read", read))
    router.add("POST", col, guarded("create", create))
    router.add("PUT", item, guarded("update", update))
    router.add("DELETE", item, guarded("remove", remove))


def flat_gate(user: str, password: str) -> Gate:
    """The flat generated credential: ``X-User`` / ``X-Pswd`` must equal the
    message name / hash, else 401 (the C++ non-hardened gate)."""

    def gate(req: Request, op: str) -> Response | None:
        if req.header("X-User") == user and req.header("X-Pswd") == password:
            return None
        return text(401)
    return gate
