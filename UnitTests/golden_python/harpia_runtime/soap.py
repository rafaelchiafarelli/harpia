"""The SOAP envelope-parse seam (Python port of
``SoapAdapter/runtime/harpia_soap.h``).

Hand-written, copied into a generated project as ``harpia_runtime.soap``;
generated ``harpia_generated/soap/<name>_<hash>_soap.py`` endpoints use it.

Like tinyxml2 in C++, the parser does **no namespace processing**: element
names keep their literal ``prefix:local`` form and an undeclared prefix is
fine, so any envelope the C++ endpoint accepts parses here too.
:func:`local_name` strips a ``prefix:`` (or an ElementTree ``{uri}``).

**Hardening:** a document with a DTD (``<!DOCTYPE`` / ``<!ENTITY``) is
refused before parsing -- SOAP messages must not carry one -- so entity
expansion ("billion laughs") never happens, and expat would reject a late
declaration anyway. Request size is bounded by the HTTP router
(``MAX_BODY``). Malformed input gives ``None`` / ``False``; nothing raises.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.parsers import expat

from google.protobuf.message import Message

from harpia_runtime.xml import from_xml_element

_DTD = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


class _Refused(Exception):
    pass


def local_name(e: ET.Element | None) -> str:
    """The element's name without its namespace prefix."""
    if e is None:
        return ""
    tag = e.tag
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag.split(":", 1)[1] if ":" in tag else tag


def find_child(parent: ET.Element | None, local: str) -> ET.Element | None:
    """The first child element whose :func:`local_name` is ``local``."""
    if parent is None:
        return None
    for child in parent:
        if local_name(child) == local:
            return child
    return None


def child_text(parent: ET.Element | None, local: str) -> str:
    """The text of :func:`find_child` (``""`` when absent or empty)."""
    child = find_child(parent, local)
    return (child.text or "") if child is not None else ""


def parse_envelope(envelope: str | bytes) -> ET.Element | None:
    """Parse an envelope (no namespace processing); its root element, or
    ``None`` when it is malformed or carries a DTD."""
    raw = envelope.encode("utf-8") if isinstance(envelope, str) else envelope
    if _DTD.search(raw):
        return None
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate()  # no namespace_separator: literal names

    def refuse(*_: object) -> None:
        raise _Refused()

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = lambda name, attrs: builder.start(name, attrs)
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    try:
        parser.Parse(raw, True)
        root = builder.close()
    except (expat.ExpatError, _Refused, ValueError, AssertionError, IndexError):
        return None
    return root


@dataclass(frozen=True)
class Request:
    """The SOAP operation: the Body's first child element."""

    operation: str
    op: ET.Element


def find_operation(root: ET.Element | None) -> Request | None:
    """The Body's first child element, or ``None``."""
    body = find_child(root, "Body")
    if body is None or len(body) == 0:
        return None
    op = body[0]
    return Request(local_name(op), op)


def message_from_request(envelope: str | bytes, msg: Message) -> bool:
    """Decode the operation's first child element into ``msg`` (the pure
    string → message decode the endpoints and the fuzz test share)."""
    req = find_operation(parse_envelope(envelope))
    if req is None or len(req.op) == 0:
        return False
    try:
        return from_xml_element(req.op[0], msg)
    except Exception:
        return False


def envelope(body: str) -> str:
    """Wrap ``body`` in the SOAP 1.1 envelope C++ answers with."""
    return ('<?xml version="1.0"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body>" + body + "</soap:Body></soap:Envelope>")


def fault(text: str, code: str = "") -> str:
    """A ``soap:Fault`` body (``faultcode`` only when given)."""
    head = f"<faultcode>{code}</faultcode>" if code else ""
    return f"<soap:Fault>{head}<faultstring>{text}</faultstring></soap:Fault>"
