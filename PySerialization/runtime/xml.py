"""XML for any harpia message: a line-for-line port of the C++ runtime
``XmlAdapter/runtime/harpia_xml.h``, byte-identical output.

- The root element is the message **type name**; each field is an element
  named after the field.
- Presence: a field with real presence (a message, an ``optional`` scalar) is
  emitted only when set; an ordinary proto3 scalar is always emitted.
- Repeated fields repeat the element; a map entry is
  ``<field><key>..</key><value>..</value></field>``.
- Numbers print like C++ ``std::to_string`` (``%f`` for floats); enums by
  name; ``& < > " '`` are escaped.

Parsing (:func:`from_xml`) uses ``xml.etree.ElementTree`` and, like the C++
reader, **merges** into the message, skips unknown elements and parses
numbers with C ``strto*`` semantics. :func:`xsd` describes a message type.
"""
import xml.etree.ElementTree as ET
from typing import Any

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import Message

from harpia_runtime.reflect import (
    FD,
    has_presence,
    is_map,
    is_repeated,
    parse_scalar,
    scalar_text,
    set_scalar,
    string_text,
)

_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def escape(text: str) -> str:
    """Escape ``& < > " '`` exactly like C++ ``detail::escape``."""
    return "".join(_ESCAPES.get(c, c) for c in text)


def _value(f: FieldDescriptor, v: Any, out: list[str]) -> None:
    if f.cpp_type == FD.CPPTYPE_MESSAGE:
        _write_message(v, out)
    elif f.cpp_type == FD.CPPTYPE_STRING:
        out.append(escape(string_text(v)))
    else:
        out.append(scalar_text(f, v))


def _write_message(msg: Message, out: list[str]) -> None:
    for f in msg.DESCRIPTOR.fields:
        tag = f.name
        if is_map(f):
            kf = f.message_type.fields_by_name["key"]
            vf = f.message_type.fields_by_name["value"]
            container = getattr(msg, tag)
            for key in container:
                out.append("<" + tag + "><key>")
                _value(kf, key, out)
                out.append("</key><value>")
                _value(vf, container[key], out)
                out.append("</value></" + tag + ">")
        elif is_repeated(f):
            for item in getattr(msg, tag):
                out.append("<" + tag + ">")
                _value(f, item, out)
                out.append("</" + tag + ">")
        else:
            if has_presence(f) and not msg.HasField(tag):
                continue
            out.append("<" + tag + ">")
            _value(f, getattr(msg, tag), out)
            out.append("</" + tag + ">")


def to_xml(msg: Message) -> str:
    """Serialize ``msg`` to XML (root element = the message type name)."""
    root = msg.DESCRIPTOR.name
    out = ["<" + root + ">"]
    _write_message(msg, out)
    out.append("</" + root + ">")
    return "".join(out)


def _read_value(f: FieldDescriptor, node: ET.Element) -> Any:
    return parse_scalar(f, node.text)


def _read_message(node: ET.Element, msg: Message) -> bool:
    fields = msg.DESCRIPTOR.fields_by_name
    for child in node:
        f = fields.get(child.tag)
        if f is None:
            continue
        if is_map(f):
            kf = f.message_type.fields_by_name["key"]
            vf = f.message_type.fields_by_name["value"]
            k_node, v_node = child.find("key"), child.find("value")
            key = parse_scalar(kf, None if k_node is None else k_node.text)
            container = getattr(msg, f.name)
            if vf.cpp_type == FD.CPPTYPE_MESSAGE:
                target = container[key]
                target.Clear()
                if v_node is not None:
                    _read_message(v_node, target)
            else:
                value = parse_scalar(vf, None if v_node is None else v_node.text)
                container[key] = vf.default_value if value is None else value
        elif f.cpp_type == FD.CPPTYPE_MESSAGE:
            if is_repeated(f):
                _read_message(child, getattr(msg, f.name).add())
            else:
                sub = getattr(msg, f.name)
                sub.SetInParent()
                _read_message(child, sub)
        else:
            value = _read_value(f, child)
            if value is not None:
                set_scalar(msg, f, value)
    return True


def from_xml(text: str, msg: Message) -> bool:
    """Merge the XML document ``text`` into ``msg``.

    Returns:
        ``False`` if the document does not parse, ``True`` otherwise.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return False
    return _read_message(root, msg)


def from_xml_element(node: ET.Element | None, msg: Message) -> bool:
    """Merge an already-parsed element into ``msg`` (batch import, SOAP)."""
    if node is None:
        return False
    return _read_message(node, msg)


_XSD_SCALAR = {
    FD.CPPTYPE_INT32: "xs:int", FD.CPPTYPE_INT64: "xs:long",
    FD.CPPTYPE_UINT32: "xs:unsignedInt", FD.CPPTYPE_UINT64: "xs:unsignedLong",
    FD.CPPTYPE_DOUBLE: "xs:double", FD.CPPTYPE_FLOAT: "xs:float",
    FD.CPPTYPE_BOOL: "xs:boolean",
}


def _collect(d: Descriptor, order: list[Descriptor]) -> None:
    if any(x is d or x.full_name == d.full_name for x in order):
        return
    order.append(d)
    for f in d.fields:
        if f.cpp_type == FD.CPPTYPE_MESSAGE:
            _collect(f.message_type, order)


def xsd(root: Descriptor) -> str:
    """An XSD schema for ``root`` and every message type it reaches."""
    order: list[Descriptor] = []
    _collect(root, order)
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n'
           '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n',
           f'  <xs:element name="{root.name}" type="{root.name}"/>\n']
    for d in order:
        out.append(f'  <xs:complexType name="{d.name}">\n    <xs:sequence>\n')
        for f in d.fields:
            if f.cpp_type == FD.CPPTYPE_MESSAGE:
                type_name = f.message_type.name
            else:
                type_name = _XSD_SCALAR.get(f.cpp_type, "xs:string")
            line = f'      <xs:element name="{f.name}" type="{type_name}" minOccurs="0"'
            if is_repeated(f):
                line += ' maxOccurs="unbounded"'
            out.append(line + "/>\n")
        out.append("    </xs:sequence>\n  </xs:complexType>\n")
    out.append("</xs:schema>\n")
    return "".join(out)
