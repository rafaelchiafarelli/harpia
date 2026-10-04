"""DB-API 2.0 bind/extract for one scalar or enum field.

The Python counterpart of the C++ DAO's typed locals and the Java target's
``JdbcBind``: one function each way, dispatching on
``FieldDescriptor.cpp_type``. Python attribute names are the exact
``.proto`` field names, so nothing is derived from the column name.

The column mapping matches the C++ target (``Database/model.py``): integers,
``bool`` and enums are stored as integers (an enum as its number), ``float``
and ``double`` as a floating-point column, ``string`` as text. A SQL
``NULL`` reads back as the field's default value, like the C++ DAO's
indicator check.
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


def bind_value(msg: Message, field_name: str) -> Any:
    """The DB-API parameter for ``msg.<field_name>``.

    Returns:
        ``int`` for integer, ``bool`` and enum fields, ``float`` for
        ``float``/``double``, ``str`` for ``string`` (``bytes`` for
        ``bytes``).
    """
    f = _field(msg, field_name)
    value = getattr(msg, field_name)
    if f.cpp_type in _INTS or f.cpp_type == FD.CPPTYPE_BOOL:
        return int(value)
    if f.cpp_type in (FD.CPPTYPE_FLOAT, FD.CPPTYPE_DOUBLE):
        return float(value)
    return value


def extract_value(row_value: Any, msg: Message, field_name: str) -> None:
    """Set ``msg.<field_name>`` from a fetched column value (``None`` → the
    field's default)."""
    f = _field(msg, field_name)
    if row_value is None:
        setattr(msg, field_name, f.default_value)
    elif f.cpp_type in _INTS:
        setattr(msg, field_name, int(row_value))
    elif f.cpp_type == FD.CPPTYPE_BOOL:
        setattr(msg, field_name, bool(row_value))
    elif f.cpp_type in (FD.CPPTYPE_FLOAT, FD.CPPTYPE_DOUBLE):
        setattr(msg, field_name, float(row_value))
    elif f.type == FD.TYPE_BYTES:
        setattr(msg, field_name, bytes(row_value))
    else:
        setattr(msg, field_name, str(row_value))
