"""Descriptor-walk helpers shared by the XML, YAML and ``to_string`` runtimes.

Ports of the small pieces the C++ runtimes share, so the Python output is
byte-identical:

- :func:`scalar_text` prints a scalar the way C++ ``std::to_string`` does
  (integers plain, ``float``/``double`` as ``"%f"``, ``bool`` as
  ``true``/``false``, enums by name).
- :func:`to_ll`, :func:`to_ull` and :func:`to_d` parse a number the way C
  ``strtoll`` / ``strtoull`` / ``strtod`` do: the longest valid prefix,
  ``0`` when there is none.
- :func:`has_presence` and :func:`is_map` mirror the ``FieldDescriptor``
  predicates.
"""
import re
from typing import Any

from google.protobuf.descriptor import EnumDescriptor, FieldDescriptor
from google.protobuf.message import Message

FD = FieldDescriptor

_INT_RE = re.compile(r"\s*([+-]?\d+)")
_FLOAT_RE = re.compile(
    r"\s*([+-]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|inf(?:inity)?|nan))",
    re.IGNORECASE)

_I32 = 1 << 32
_I64_MAX = (1 << 63) - 1
_U64 = 1 << 64

INTEGER_TYPES = (FD.CPPTYPE_INT32, FD.CPPTYPE_INT64,
                 FD.CPPTYPE_UINT32, FD.CPPTYPE_UINT64)


def is_map(f: FieldDescriptor) -> bool:
    """Whether ``f`` is a ``map<K, V>`` field."""
    return (f.cpp_type == FD.CPPTYPE_MESSAGE
            and bool(f.message_type.GetOptions().map_entry))


def is_repeated(f: FieldDescriptor) -> bool:
    """Whether ``f`` is a repeated (or map) field."""
    return bool(f.label == FD.LABEL_REPEATED)


def has_presence(f: FieldDescriptor) -> bool:
    """Whether a singular field tracks presence (message, oneof or
    ``optional``), like C++ ``FieldDescriptor::has_presence()``."""
    if is_repeated(f):
        return False
    if f.cpp_type == FD.CPPTYPE_MESSAGE or f.containing_oneof is not None:
        return True
    return bool(f.containing_type.file.syntax == "proto2")


def enum_name(enum_type: EnumDescriptor, number: int) -> str:
    """The value name C++ ``GetEnum(...)->name()`` prints for ``number``."""
    value = enum_type.values_by_number.get(number)
    if value is not None:
        return str(value.name)
    return f"UNKNOWN_ENUM_VALUE_{enum_type.name}_{number}"


def string_text(value: Any) -> str:
    """A ``string``/``bytes`` field value as text (bytes kept byte-exact)."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "surrogateescape")
    return str(value)


def scalar_text(f: FieldDescriptor, value: Any) -> str:
    """Print a non-message, non-string value as the C++ runtimes do."""
    t = f.cpp_type
    if t in (FD.CPPTYPE_DOUBLE, FD.CPPTYPE_FLOAT):
        return format(value, "f")  # == C "%f" (std::to_string)
    if t == FD.CPPTYPE_BOOL:
        return "true" if value else "false"
    if t == FD.CPPTYPE_ENUM:
        return enum_name(f.enum_type, int(value))
    return str(int(value))


def to_ll(text: str | None) -> int:
    """C ``strtoll(text, nullptr, 10)``: longest integer prefix, clamped."""
    if not text:
        return 0
    m = _INT_RE.match(text)
    if not m:
        return 0
    return max(-_I64_MAX - 1, min(_I64_MAX, int(m.group(1))))


def to_ull(text: str | None) -> int:
    """C ``strtoull(text, nullptr, 10)``: a leading ``-`` negates modulo 2**64."""
    if not text:
        return 0
    m = _INT_RE.match(text)
    if not m:
        return 0
    v = int(m.group(1))
    if v >= _U64 or v <= -_U64:
        return _U64 - 1
    return v % _U64


def to_d(text: str | None) -> float:
    """C ``strtod(text, nullptr)``: longest floating-point prefix."""
    if not text:
        return 0.0
    m = _FLOAT_RE.match(text)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0


def _wrap32(v: int, signed: bool) -> int:
    v %= _I32
    if signed and v >= _I32 // 2:
        v -= _I32
    return v


def parse_scalar(f: FieldDescriptor, text: str | None) -> Any:
    """Convert ``text`` to the value C++ would store in ``f`` (``None`` for an
    enum name/number the type doesn't have, which C++ skips)."""
    t = f.cpp_type
    if t == FD.CPPTYPE_INT32:
        return _wrap32(to_ll(text), True)
    if t == FD.CPPTYPE_INT64:
        return to_ll(text)
    if t == FD.CPPTYPE_UINT32:
        return _wrap32(to_ull(text), False)
    if t == FD.CPPTYPE_UINT64:
        return to_ull(text)
    if t in (FD.CPPTYPE_DOUBLE, FD.CPPTYPE_FLOAT):
        return to_d(text)
    if t == FD.CPPTYPE_BOOL:
        return text in ("true", "1")
    if t == FD.CPPTYPE_ENUM:
        if text is None:
            return None
        value = f.enum_type.values_by_name.get(text)
        if value is None:
            value = f.enum_type.values_by_number.get(_wrap32(to_ll(text), True))
        return None if value is None else value.number
    s = text or ""
    return s.encode("utf-8", "surrogateescape") if f.type == FD.TYPE_BYTES else s


def set_scalar(msg: Message, f: FieldDescriptor, value: Any) -> None:
    """Set (singular) or append (repeated) a parsed scalar value."""
    if is_repeated(f):
        getattr(msg, f.name).append(value)
    else:
        setattr(msg, f.name, value)
