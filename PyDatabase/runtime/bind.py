"""DB-API 2.0 bind/extract for one scalar or enum field.

The Python counterpart of the C++ DAO's typed locals and the Java target's
``JdbcBind``: one function each way, dispatching on
``FieldDescriptor.cpp_type``. Python attribute names are the exact
``.proto`` field names, so nothing is derived from the column name.

The column mapping matches the C++ target (``Database/model.py``): integers,
``bool`` and enums are stored as integers (an enum as its number), ``float``
and ``double`` as a floating-point column, ``string`` as text. A SQL
``NULL`` reads back as the field's default value, like the C++ DAO's
indicator check -- except for an ``optional`` field (explicit presence):
unset binds ``NULL`` and a ``NULL`` leaves it unset, so presence survives
the database (db-optional-presence-DEFECT, the C++ rule).
"""
from typing import Any

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

FD = FieldDescriptor

_INTS = (FD.CPPTYPE_INT32, FD.CPPTYPE_INT64, FD.CPPTYPE_UINT32,
         FD.CPPTYPE_UINT64, FD.CPPTYPE_ENUM)


def _field(msg: Message, field_name: str) -> FieldDescriptor:
    f: FieldDescriptor = msg.DESCRIPTOR.fields_by_name[field_name]
    if f.cpp_type == FD.CPPTYPE_MESSAGE or f.label == FD.LABEL_REPEATED:
        raise TypeError(
            f"{msg.DESCRIPTOR.name}.{field_name} is not a scalar/enum field")
    return f


def to_db(f: FieldDescriptor, value: Any) -> Any:
    """Convert one value of scalar/enum field ``f`` (a single element for a
    repeated field or a map key/value) to its DB-API parameter."""
    if f.cpp_type in _INTS or f.cpp_type == FD.CPPTYPE_BOOL:
        return int(value)
    if f.cpp_type in (FD.CPPTYPE_FLOAT, FD.CPPTYPE_DOUBLE):
        return float(value)
    return value


def from_db(f: FieldDescriptor, row_value: Any) -> Any:
    """Convert a fetched column value back to a value of field ``f``
    (``None`` → the field's default)."""
    if row_value is None:
        return f.default_value
    if f.cpp_type in _INTS:
        return int(row_value)
    if f.cpp_type == FD.CPPTYPE_BOOL:
        return bool(row_value)
    if f.cpp_type in (FD.CPPTYPE_FLOAT, FD.CPPTYPE_DOUBLE):
        return float(row_value)
    if f.type == FD.TYPE_BYTES:
        return bytes(row_value)
    return str(row_value)


def has_presence(f: FieldDescriptor) -> bool:
    """``f`` tracks presence (a proto3 ``optional`` scalar). Read with
    ``getattr``: the pinned ``types-protobuf`` stubs don't declare it."""
    return bool(getattr(f, "has_presence", False))


def is_unset_optional(msg: Message, f: FieldDescriptor) -> bool:
    """``f`` has explicit presence (``optional``) and ``msg`` doesn't set it."""
    return has_presence(f) and not msg.HasField(f.name)


def bind_value(msg: Message, field_name: str) -> Any:
    """The DB-API parameter for ``msg.<field_name>``.

    Returns:
        ``int`` for integer, ``bool`` and enum fields, ``float`` for
        ``float``/``double``, ``str`` for ``string`` (``bytes`` for
        ``bytes``); ``None`` (SQL ``NULL``) for an unset ``optional``.
    """
    f = _field(msg, field_name)
    if is_unset_optional(msg, f):
        return None
    return to_db(f, getattr(msg, field_name))


def extract_value(row_value: Any, msg: Message, field_name: str) -> None:
    """Set ``msg.<field_name>`` from a fetched column value (``None`` → the
    field's default; for an ``optional`` field, ``None`` leaves it as it is,
    i.e. unset on a fresh message)."""
    f = _field(msg, field_name)
    if row_value is None and has_presence(f):
        return
    setattr(msg, field_name, from_db(f, row_value))
