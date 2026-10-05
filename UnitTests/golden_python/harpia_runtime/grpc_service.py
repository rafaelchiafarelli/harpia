"""CRUDL gRPC servicer over a generated DAO (the Python side of the C++
``grpc/<name>_<hash>_grpc.h``).

Hand-written, copied into a generated project as
``harpia_runtime.grpc_service``. A generated ``<name>_Service`` subclasses
:class:`CrudServicer` and is registered with the protoc-generated
``add_<name>_ServiceServicer_to_server`` (same ``.proto``, so C++ clients
call it unchanged). RPCs, as in C++:

- ``push`` → ``dao.create``; answers ``errorCode`` ``0 "ok"`` or
  ``1 "create failed"`` (status OK either way);
- ``pullByID`` → ``dao.read``; ``NOT_FOUND "not found"`` when missing;
- ``streamSrc`` → ``dao.list`` (paged by the request's ``offset`` /
  ``limit`` when ``limit > 0``); the rows are read and the connection is
  given back **before** they are streamed; ``INTERNAL "list failed"`` on a
  database error;
- ``heartBeat`` → echo; never gated. When the class sets
  ``HEARTBEAT_HOOK`` (RBAC-gated messages: session-token issuance, see
  :func:`harpia_runtime.rbac_gates.issue_on_heartbeat`) it runs first.

Each data RPC runs the access gate first, then borrows one pooled
connection: exhausted → ``RESOURCE_EXHAUSTED "db pool exhausted"``,
reconnect failure → ``UNAVAILABLE "db reconnect failed"``.
"""
from collections.abc import Callable, Iterator
from typing import Any, ClassVar

import grpc
from google.protobuf.message import Message

from harpia_runtime.db.pool import ConnectionPool, PoolExhausted, PoolReconnectFailed

#: ``None`` lets the call through; otherwise ``(code, details)`` to abort with
Gate = Callable[[grpc.ServicerContext, str], tuple[grpc.StatusCode, str] | None]


def metadata(context: grpc.ServicerContext, key: str) -> str | None:
    """The first value of call metadata ``key`` (lower-case), or ``None``."""
    for k, v in context.invocation_metadata():
        if k == key:
            return v if isinstance(v, str) else v.decode("utf-8", "replace")
    return None


def flat_gate(user: str, password: str) -> Gate:
    """The flat generated credential: ``x-user`` / ``x-pswd`` metadata equal
    to the message name / hash, else ``UNAUTHENTICATED "unauthorized"``."""

    def gate(context: grpc.ServicerContext,
             op: str) -> tuple[grpc.StatusCode, str] | None:
        if (metadata(context, "x-user") == user
                and metadata(context, "x-pswd") == password):
            return None
        return grpc.StatusCode.UNAUTHENTICATED, "unauthorized"
    return gate


class CrudServicer:
    """The four RPCs of a ``<name>_Service`` (see the module docstring)."""

    #: the generated DAO class
    DAO: ClassVar[Any]
    #: the ``<name>_Message`` wrapper (field ``msg``)
    WRAPPER: ClassVar[type[Message]]
    #: ``errorCode``
    ERROR_CODE: ClassVar[type[Message]]
    GATE: ClassVar[Gate]
    #: run by ``heartBeat`` before echoing (``None``: nothing)
    HEARTBEAT_HOOK: ClassVar[Callable[[grpc.ServicerContext], None] | None] = None

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def _guard(self, context: grpc.ServicerContext, op: str) -> None:
        refusal = type(self).GATE(context, op)
        if refusal is not None:
            context.abort(*refusal)

    def _with_dao(self, context: grpc.ServicerContext,
                  run: Callable[[Any], Any]) -> Any:
        try:
            with self.pool.borrow() as conn:
                return run(self.DAO(conn))
        except PoolExhausted:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "db pool exhausted")
        except PoolReconnectFailed:
            context.abort(grpc.StatusCode.UNAVAILABLE, "db reconnect failed")

    def push(self, request: Any, context: grpc.ServicerContext) -> Message:
        """Create the row carried in ``request.msg``."""
        self._guard(context, "create")

        def create(dao: Any) -> bool:
            try:
                return bool(dao.create(request.msg))
            except Exception:
                return False
        ok = self._with_dao(context, create)
        return self.ERROR_CODE(code=0 if ok else 1,
                               message="ok" if ok else "create failed")

    def pullByID(self, request: Any, context: grpc.ServicerContext) -> Message:  # noqa: N802
        """Read the row ``request.id``."""
        self._guard(context, "read")
        response = self.WRAPPER()

        def read(dao: Any) -> bool:
            try:
                return bool(dao.read(request.id, response.msg))  # type: ignore[attr-defined]
            except Exception:
                return False
        if not self._with_dao(context, read):
            context.abort(grpc.StatusCode.NOT_FOUND, "not found")
        return response

    def streamSrc(self, request: Any,  # noqa: N802
                  context: grpc.ServicerContext) -> Iterator[Message]:
        """Stream every row (or one page)."""
        self._guard(context, "stream")

        def rows(dao: Any) -> list[Any] | None:
            try:
                if request.limit > 0:
                    return list(dao.list(request.offset, request.limit))
                return list(dao.list())
            except Exception:
                return None
        listed = self._with_dao(context, rows)  # connection back before streaming
        if listed is None:
            context.abort(grpc.StatusCode.INTERNAL, "list failed")
        for row in listed:
            out = self.WRAPPER()
            out.msg.CopyFrom(row)  # type: ignore[attr-defined]
            yield out

    def heartBeat(self, request: Message, context: grpc.ServicerContext) -> Message:  # noqa: N802
        """Echo (never gated)."""
        hook = type(self).HEARTBEAT_HOOK
        if hook is not None:
            hook(context)
        return request
