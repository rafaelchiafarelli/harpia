"""One ``to_string`` / ``from_string`` for JSON, XML and YAML, with ``phi``
redaction (port of ``SerializeAdapter/runtime/harpia_serialize.h``).

- A message whose type tree has no ``phi`` field goes straight to the
  engines (``harpia_runtime.json`` / ``xml`` / ``yaml``): byte-identical to
  calling them directly.
- A message whose tree has a ``phi`` field (recursively, cycle-guarded)
  renders through one redacting walk that prints ``[REDACTED]`` for each
  ``phi`` value: quoted in JSON/YAML, bare in XML. The walk is a deliberate
  port of the C++ one, quirks included: it prints proto3 default scalars,
  YAML strings use JSON escaping, and JSON map keys are escaped twice.
- Redacted text is a lossy view: :func:`from_string` of redacted JSON fails;
  of redacted XML/YAML it leaves ``phi`` fields at their defaults.
"""
import enum
from typing import Any

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import Message

from harpia_generated.serialize.phi_registry import is_phi
from harpia_runtime import json as _json
from harpia_runtime import xml as _xml
from harpia_runtime import yaml as _yaml
from harpia_runtime.redaction import PLACEHOLDER, redaction_enabled, should_redact
from harpia_runtime.reflect import (
    FD,
    has_presence,
    is_map,
    is_repeated,
    scalar_text,
    string_text,
)


class Format(enum.Enum):
    """A text format :func:`to_string` / :func:`from_string` speak."""

    JSON = 0
    XML = 1
    YAML = 2


def format_name(fmt: Format) -> str:
    """``"json"``, ``"xml"`` or ``"yaml"``."""
    return fmt.name.lower()


def _tree_has_phi(d: Descriptor, seen: list[Descriptor]) -> bool:
    if any(s.full_name == d.full_name for s in seen):
        return False
    seen.append(d)
    for f in d.fields:
        if is_phi(d.name, f.name):
            return True
        if f.cpp_type == FD.CPPTYPE_MESSAGE and _tree_has_phi(f.message_type, seen):
            return True
    return False


def tree_has_phi(d: Descriptor) -> bool:
    """Whether ``d`` or any message type it reaches has a ``phi`` field."""
    return _tree_has_phi(d, [])


def _json_escape(text: str) -> str:
    out = []
    for c in text:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20:
            out.append(f"\\u00{ord(c):02x}")
        else:
            out.append(c)
    return "".join(out)


def _pad(n: int) -> str:
    return " " * max(n, 0)


def _scalar(f: FieldDescriptor, v: Any, fmt: Format) -> str:
    if f.cpp_type == FD.CPPTYPE_ENUM:
        name = scalar_text(f, v)
        return name if fmt == Format.XML else '"' + name + '"'
    if f.cpp_type == FD.CPPTYPE_STRING:
        s = string_text(v)
        return _xml.escape(s) if fmt == Format.XML else '"' + _json_escape(s) + '"'
    return scalar_text(f, v)


def _placeholder(fmt: Format) -> str:
    return PLACEHOLDER if fmt == Format.XML else '"' + PLACEHOLDER + '"'


def _walk_map(msg: Message, f: FieldDescriptor, fmt: Format, indent: int,
              out: list[str]) -> None:
    key = f.name
    container = getattr(msg, key)
    kf = f.message_type.fields_by_name["key"]
    vf = f.message_type.fields_by_name["value"]
    if fmt == Format.JSON:
        out.append('"' + _json_escape(key) + '":{')
        for k, entry_key in enumerate(container):
            if k:
                out.append(",")
            kbuf = _scalar(kf, entry_key, fmt)
            if kf.cpp_type == FD.CPPTYPE_STRING and len(kbuf) >= 2:
                kbuf = kbuf[1:-1]
            out.append('"' + _json_escape(kbuf) + '":')
            value = container[entry_key]
            if vf.cpp_type == FD.CPPTYPE_MESSAGE:
                _walk_message(value, fmt, indent, out)
            else:
                out.append(_scalar(vf, value, fmt))
        out.append("}")
        return
    if fmt == Format.XML:
        for entry_key in container:
            out.append("<" + key + "><key>" + _scalar(kf, entry_key, fmt)
                       + "</key><value>")
            value = container[entry_key]
            if vf.cpp_type == FD.CPPTYPE_MESSAGE:
                _walk_message(value, fmt, indent, out)
            else:
                out.append(_scalar(vf, value, fmt))
            out.append("</value></" + key + ">")
        return
    out.append(_pad(indent) + key + ":")
    if len(container) == 0:
        out.append(" {}\n")
        return
    out.append("\n")
    for entry_key in container:
        out.append(_pad(indent + 2) + _scalar(kf, entry_key, fmt) + ":")
        value = container[entry_key]
        if vf.cpp_type == FD.CPPTYPE_MESSAGE:
            block: list[str] = []
            _walk_message(value, fmt, indent + 4, block)
            if not block:
                out.append(" {}\n")
            else:
                out.append("\n")
                out.extend(block)
        else:
            out.append(" " + _scalar(vf, value, fmt) + "\n")


def _walk_field(msg: Message, f: FieldDescriptor, fmt: Format, indent: int,
                out: list[str]) -> None:
    key = f.name
    redact = should_redact(msg.DESCRIPTOR.name, key)
    if is_map(f) and not redact:
        _walk_map(msg, f, fmt, indent, out)
        return
    is_msg = f.cpp_type == FD.CPPTYPE_MESSAGE
    if fmt == Format.JSON:
        out.append('"' + _json_escape(key) + '":')
        if redact:
            out.append(_placeholder(fmt))
        elif is_repeated(f):
            out.append("[")
            for k, item in enumerate(getattr(msg, key)):
                if k:
                    out.append(",")
                if is_msg:
                    _walk_message(item, fmt, indent, out)
                else:
                    out.append(_scalar(f, item, fmt))
            out.append("]")
        elif is_msg:
            _walk_message(getattr(msg, key), fmt, indent, out)
        else:
            out.append(_scalar(f, getattr(msg, key), fmt))
        return
    if fmt == Format.XML:
        if redact:
            out.append("<" + key + ">" + _placeholder(fmt) + "</" + key + ">")
            return
        items = list(getattr(msg, key)) if is_repeated(f) else [getattr(msg, key)]
        for item in items:
            out.append("<" + key + ">")
            if is_msg:
                _walk_message(item, fmt, indent, out)
            else:
                out.append(_scalar(f, item, fmt))
            out.append("</" + key + ">")
        return
    out.append(_pad(indent) + key + ":")
    if redact:
        out.append(" " + _placeholder(fmt) + "\n")
        return
    if is_repeated(f):
        items = getattr(msg, key)
        if len(items) == 0:
            out.append(" []\n")
            return
        out.append("\n")
        for item in items:
            if is_msg:
                block: list[str] = []
                _walk_message(item, fmt, indent + 4, block)
                text = "".join(block)
                if not text:
                    out.append(_pad(indent + 2) + "- {}\n")
                else:
                    strip = min(len(text), indent + 4)
                    out.append(_pad(indent + 2) + "- " + text[strip:])
            else:
                out.append(_pad(indent + 2) + "- " + _scalar(f, item, fmt) + "\n")
    elif is_msg:
        sub: list[str] = []
        _walk_message(getattr(msg, key), fmt, indent + 2, sub)
        if not sub:
            out.append(" {}\n")
        else:
            out.append("\n")
            out.extend(sub)
    else:
        out.append(" " + _scalar(f, getattr(msg, key), fmt) + "\n")


def _visible(msg: Message, f: FieldDescriptor) -> bool:
    return is_repeated(f) or not has_presence(f) or msg.HasField(f.name)


def _walk_message(msg: Message, fmt: Format, indent: int, out: list[str]) -> None:
    fields = [f for f in msg.DESCRIPTOR.fields if _visible(msg, f)]
    if fmt == Format.JSON:
        out.append("{")
        for k, f in enumerate(fields):
            if k:
                out.append(",")
            _walk_field(msg, f, fmt, indent, out)
        out.append("}")
        return
    for f in fields:
        _walk_field(msg, f, fmt, indent, out)


def redacted_to_string(msg: Message, fmt: Format) -> str:
    """The redacting walk itself (what :func:`to_string` uses for phi trees)."""
    out: list[str] = []
    if fmt == Format.XML:
        root = msg.DESCRIPTOR.name
        out.append("<" + root + ">")
        _walk_message(msg, fmt, 0, out)
        out.append("</" + root + ">")
        return "".join(out)
    _walk_message(msg, fmt, 0, out)
    text = "".join(out)
    if fmt == Format.YAML and not text:
        return "{}\n"
    return text


def to_string(msg: Message, fmt: Format) -> str:
    """Serialize ``msg`` to ``fmt``, redacting ``phi`` values while enabled."""
    if redaction_enabled() and tree_has_phi(msg.DESCRIPTOR):
        return redacted_to_string(msg, fmt)
    if fmt == Format.XML:
        return _xml.to_xml(msg)
    if fmt == Format.YAML:
        return _yaml.to_yaml(msg)
    return _json.to_json(msg)


def from_string(text: str, msg: Message, fmt: Format) -> bool:
    """Parse ``text`` (in ``fmt``) into ``msg`` through the matching engine."""
    if fmt == Format.XML:
        return _xml.from_xml(text, msg)
    if fmt == Format.YAML:
        return _yaml.from_yaml(text, msg)
    return _json.from_json(text, msg)
