"""Helpers for the generated per-message test suite (``python/tests/``).

Hand-written, copied into a generated project as ``harpia_runtime.testing``
by ``PyTestAdapter`` (python-target / py-tests). The generated
``tests/test_<name>_<hash>.py`` modules are thin; the reflection lives here:

- :func:`sample` fills **every** field of a message deterministically with
  the C++ ``TestAdapter._value`` rules -- text ``"<field>_<variant>"``,
  enum ``1`` (the first value when 1 isn't one), floating ``2.5`` / ``3.5``,
  64-bit ``7`` / ``8``, anything else ``1`` -- for variant ``"a"`` or
  ``"b"``. Composed fields are filled recursively (embedded, foreign-key and
  repeated children alike), repeated fields and maps get two entries (map
  keys / values per ``TestAdapter._map_key`` / ``_map_val``), and every
  nested ``ID_<hash>`` gets a distinct value so FK children are distinct
  rows;
- :func:`check_field_access` proves every field survives set → get;
- :func:`create_tables` creates a DAO's table and the tables it reaches;
- :func:`persisted_view` is what a DAO stores for a message (its columns,
  FK children's own views, and the map / repeated / composed child tables),
  the comparison a CRUDL round trip checks;
- py-tests task 2, the HTTP bodies: :func:`serve` stands the generated REST /
  SOAP registrations up on a plain in-process server on an ephemeral port
  (like the C++ tests' Crow app -- not the mTLS ``HttpServer``),
  :func:`request` is a small client, :func:`soap_envelope` /
  :func:`probe_text` build what the checks send and look for.
"""
import contextlib
import http.client
from collections.abc import Callable, Iterator, Sequence
from typing import Any, TypeVar

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import Message

from harpia_runtime.db.dao import Connection, Dao, _owner, column_value, dao_class
from harpia_runtime.db.pool import ConnectionPool
from harpia_runtime.http.router import Request, Router, Server

M = TypeVar("M", bound=Message)

_ID_PREFIX = "ID_"
_HIDDEN = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")
_INT32 = FieldDescriptor.CPPTYPE_INT32
_FLOATS = (FieldDescriptor.CPPTYPE_DOUBLE, FieldDescriptor.CPPTYPE_FLOAT)
_INT64S = (FieldDescriptor.CPPTYPE_INT64, FieldDescriptor.CPPTYPE_UINT64)


def _scalar(f: FieldDescriptor, variant: str, salt: str = "") -> Any:
    t = f.cpp_type
    if t == FieldDescriptor.CPPTYPE_STRING:
        text = f"{f.name.lower()}_{variant}{salt}"
        return text.encode() if f.type == FieldDescriptor.TYPE_BYTES else text
    if t == FieldDescriptor.CPPTYPE_ENUM:
        numbers = [v.number for v in f.enum_type.values]
        return 1 if 1 in numbers else numbers[0]
    if t in _FLOATS:
        return 2.5 if variant == "a" else 3.5
    if t in _INT64S:
        return 7 if variant == "a" else 8
    if t == FieldDescriptor.CPPTYPE_BOOL:
        return True
    return 1


def _map_key(f: FieldDescriptor, i: int) -> Any:
    return f"k{i}" if f.cpp_type == FieldDescriptor.CPPTYPE_STRING else i


def _map_val(f: FieldDescriptor, i: int) -> Any:
    if f.cpp_type == FieldDescriptor.CPPTYPE_STRING:
        return f"v{i}"
    if f.cpp_type in _FLOATS:
        return i + 0.5
    if f.cpp_type == FieldDescriptor.CPPTYPE_BOOL:
        return True
    if f.cpp_type == FieldDescriptor.CPPTYPE_ENUM:
        return _scalar(f, "a")
    return i * 10


def _fill(msg: Message, variant: str, ids: list[int], seen: tuple[Descriptor, ...],
          top: bool) -> None:
    d = msg.DESCRIPTOR
    if d in seen or len(seen) > 4:
        return
    seen = (*seen, d)
    for f in d.fields:
        if f.name.startswith(_ID_PREFIX) and f.cpp_type == _INT32:
            if not top:
                ids[0] += 1
                setattr(msg, f.name, ids[0])
            continue
        if f.message_type is not None and f.message_type.GetOptions().map_entry:
            kf = f.message_type.fields_by_name["key"]
            vf = f.message_type.fields_by_name["value"]
            container = getattr(msg, f.name)
            for i in (1, 2):
                if vf.message_type is not None:
                    _fill(container[_map_key(kf, i)], variant, ids, seen, False)
                else:
                    container[_map_key(kf, i)] = _map_val(vf, i)
        elif f.label == FieldDescriptor.LABEL_REPEATED:
            container = getattr(msg, f.name)
            for i in (1, 2):
                if f.message_type is not None:
                    _fill(container.add(), variant, ids, seen, False)
                else:
                    container.append(_scalar(f, variant, str(i)))
        elif f.message_type is not None:
            child = getattr(msg, f.name)
            child.SetInParent()
            _fill(child, variant, ids, seen, False)
        else:
            setattr(msg, f.name, _scalar(f, variant))


def sample(cls: type[M], variant: str = "a", pk: int = 1,
           id_base: int = 1000) -> M:
    """A ``cls`` with every field set (see the module docstring); its own
    ``ID_<hash>`` is ``pk``, nested ones count up from ``id_base``."""
    msg = cls()
    _fill(msg, variant, [id_base], (), True)
    for f in msg.DESCRIPTOR.fields:
        if f.name.startswith(_ID_PREFIX) and f.cpp_type == _INT32:
            setattr(msg, f.name, pk)
    return msg


def check_field_access(cls: type[Message]) -> None:
    """Every field of a fresh ``cls`` reads back what was set (raises
    ``AssertionError`` naming the field otherwise)."""
    full = sample(cls)
    for f in cls.DESCRIPTOR.fields:
        msg = cls()
        value = getattr(full, f.name)
        if f.label == FieldDescriptor.LABEL_REPEATED:
            if f.message_type is not None and f.message_type.GetOptions().map_entry:
                getattr(msg, f.name).MergeFrom(value)
            else:
                getattr(msg, f.name).extend(value)
        elif f.message_type is not None:
            getattr(msg, f.name).CopyFrom(value)
        else:
            setattr(msg, f.name, value)
        assert getattr(msg, f.name) == value, f.name


def create_tables(conn: Connection, dao_cls: type[Dao[Any]]) -> None:
    """Create ``dao_cls``'s table and every table it reaches through foreign
    keys (only those: two messages may share one table name with different
    columns -- the registry's ``user_table`` note)."""
    seen: set[type[Dao[Any]]] = set()

    def visit(cls: type[Dao[Any]]) -> None:
        if cls in seen:
            return
        seen.add(cls)
        for ref in [c.fk for c in cls.COLUMNS] + [c.fk for c in cls.CHILDREN]:
            if ref is not None:
                visit(dao_class(ref))
        cls(conn).create_table()
    visit(dao_cls)


def persisted_view(dao_cls: type[Dao[Any]], msg: Message) -> dict[str, Any]:
    """What ``dao_cls`` stores for ``msg``: ``{column: value}`` (an FK column
    → the child's own view, ``None`` when absent) plus one entry per child
    table."""
    view: dict[str, Any] = {}
    for col in dao_cls.COLUMNS:
        if col.fk is None:
            view[col.name] = column_value(msg, col)
            continue
        owner, field = _owner(msg, col.path, False), col.path[-1]
        view[col.name] = (persisted_view(dao_class(col.fk), getattr(owner, field))
                          if owner.HasField(field) else None)
    for child in dao_cls.CHILDREN:
        items = getattr(_owner(msg, child.path, False), child.path[-1])
        key = "/".join(child.path)
        if child.kind == "map":
            view[key] = [(k, items[k]) for k in sorted(items)]
        elif child.kind == "composed":
            view[key] = [[column_value(item, c) for c in child.columns]
                         for item in items]
        elif child.fk is not None:
            view[key] = [persisted_view(dao_class(child.fk), item) for item in items]
        else:
            view[key] = list(items)
    return view


#: a generated ``register(router, pool, base)`` (REST or SOAP module)
Register = Callable[[Router, ConnectionPool, str], None]


@contextlib.contextmanager
def serve(pool: ConnectionPool, rest: Sequence[Register] = (),
          soap: Sequence[Register] = (), rest_base: str = "/api/v1",
          soap_base: str = "/soap") -> Iterator[int]:
    """Serve ``rest`` / ``soap`` registrations on ``127.0.0.1`` (plain HTTP,
    ephemeral port); yields the port."""
    router = Router()
    for register in rest:
        register(router, pool, rest_base)
    for register in soap:
        register(router, pool, soap_base)
    server = Server(router)
    server.start()
    try:
        yield server.port
    finally:
        server.stop()


def request(port: int, method: str, path: str, body: str | bytes | None = None,
            headers: dict[str, str] | None = None,
            timeout: float = 10.0) -> tuple[int, str]:
    """One HTTP request to ``127.0.0.1:port``: ``(status, body)``."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        res = conn.getresponse()
        return res.status, res.read().decode("utf-8", "replace")
    finally:
        conn.close()


def soap_envelope(body: str, header: str = "") -> str:
    """A SOAP 1.1 request envelope (``header`` is the inner Header XML)."""
    head = f"<soap:Header>{header}</soap:Header>" if header else ""
    return ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f"{head}<soap:Body>{body}</soap:Body></soap:Envelope>")


def probe_text(cls: type[Message]) -> str | None:
    """The :func:`sample` value of ``cls``'s first non-hidden top-level text
    field (what a served body must contain), or ``None``."""
    for f in cls.DESCRIPTOR.fields:
        if (f.type == FieldDescriptor.TYPE_STRING
                and f.label != FieldDescriptor.LABEL_REPEATED
                and not f.name.startswith(_HIDDEN)):
            return str(_scalar(f, "a"))
    return None


def fake_request(headers: dict[str, str] | None = None) -> Request:
    """A bare :class:`~harpia_runtime.http.router.Request` for calling a
    generated access gate directly (no server)."""
    return Request("GET", "/", {}, {k.lower(): v for k, v in (headers or {}).items()})
