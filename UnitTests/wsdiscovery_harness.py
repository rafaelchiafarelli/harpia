"""Minimal WS-Discovery probe/resolve client -- test scaffolding only.

Not a test and not part of the generator pipeline. This is the "generic
SDC-aware client" stand-in that the sdc-biceps epic's WS-Discovery responder
task (task 2) drives from its integration test: send a multicast ``Probe``,
read the ``ProbeMatch`` responses, pull the ``XAddrs`` a matched service
listens on, optionally ``Resolve`` an endpoint reference.

Protocol: WS-Discovery (OASIS WS-DD 2009,
``http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01``) carried as SOAP 1.2
over UDP. The standard multicast endpoint is ``239.255.255.250:3702``. This is
*not* the SOAP 1.1 document/literal shape ``Database/SoapAdapter.py`` emits for
Stage 11 -- the envelopes here are built by hand from the WS-Discovery spec.

Stdlib only (``socket`` + ``xml.etree``); no third-party dependency. Parsing
matches element *local names* inside the known SOAP/WS-Addressing/WS-Discovery
namespaces rather than pinning a prefix, so it tolerates the namespace-prefix
variance real responders show.
"""
from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

WSD_MULTICAST_GROUP = "239.255.255.250"
WSD_PORT = 3702
WSD_NS = "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01"
WSA_NS = "http://www.w3.org/2005/08/addressing"
SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"
WSD_TO = "urn:docs-oasis-open-org:ws-dd:ns:discovery:2009:01"

ACTION_PROBE = WSD_NS + "/Probe"
ACTION_PROBE_MATCHES = WSD_NS + "/ProbeMatches"
ACTION_RESOLVE = WSD_NS + "/Resolve"
ACTION_RESOLVE_MATCHES = WSD_NS + "/ResolveMatches"


class WSDiscoveryTimeout(Exception):
    """Raised when a probe/resolve gets no answer within the timeout window."""


@dataclass
class Match:
    """One ``ProbeMatch`` / ``ResolveMatch`` entry, parsed."""

    endpoint_reference: str = ""
    types: list = field(default_factory=list)
    scopes: list = field(default_factory=list)
    xaddrs: list = field(default_factory=list)
    metadata_version: Optional[int] = None


# --- message construction ---------------------------------------------------

def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return " ".join(str(v) for v in value)


def _new_message_id() -> str:
    return "urn:uuid:" + str(uuid.uuid4())


def build_probe(types=None, scopes=None, message_id: Optional[str] = None) -> bytes:
    """A WS-Discovery ``Probe`` SOAP 1.2 envelope, ready to ``sendto``.

    ``types`` / ``scopes`` accept a string or an iterable of strings; an empty
    value is omitted (an empty Probe matches every target).
    """
    mid = message_id or _new_message_id()
    body = ["<wsd:Probe>"]
    t = _as_text(types)
    s = _as_text(scopes)
    if t:
        body.append("<wsd:Types>{}</wsd:Types>".format(t))
    if s:
        body.append("<wsd:Scopes>{}</wsd:Scopes>".format(s))
    body.append("</wsd:Probe>")
    return _envelope(ACTION_PROBE, mid, "".join(body))


def build_resolve(endpoint_reference: str, message_id: Optional[str] = None) -> bytes:
    """A WS-Discovery ``Resolve`` SOAP 1.2 envelope for one endpoint reference."""
    mid = message_id or _new_message_id()
    inner = (
        "<wsd:Resolve><wsa:EndpointReference><wsa:Address>{}</wsa:Address>"
        "</wsa:EndpointReference></wsd:Resolve>".format(endpoint_reference)
    )
    return _envelope(ACTION_RESOLVE, mid, inner)


def _envelope(action: str, message_id: str, body_xml: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="{soap}" xmlns:wsa="{wsa}" xmlns:wsd="{wsd}">'
        "<soap:Header>"
        "<wsa:Action>{action}</wsa:Action>"
        "<wsa:MessageID>{mid}</wsa:MessageID>"
        "<wsa:To>{to}</wsa:To>"
        "</soap:Header>"
        "<soap:Body>{body}</soap:Body>"
        "</soap:Envelope>"
    ).format(
        soap=SOAP12_NS, wsa=WSA_NS, wsd=WSD_NS,
        action=action, mid=message_id, to=WSD_TO, body=body_xml,
    )
    return xml.encode("utf-8")


# --- response parsing -----------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_first(el, name):
    for child in el.iter():
        if _local(child.tag) == name:
            return child
    return None


def _find_all(el, name):
    return [c for c in el.iter() if _local(c.tag) == name]


def get_action(data: bytes) -> str:
    """The ``wsa:Action`` URI of a WS-Discovery envelope, or ``""``."""
    root = ET.fromstring(data)
    act = _find_first(root, "Action")
    return (act.text or "").strip() if act is not None else ""


def parse_matches(data: bytes):
    """Parse a ``ProbeMatches`` or ``ResolveMatches`` envelope into ``[Match]``.

    An envelope carrying the matches wrapper but no match entries parses to an
    empty list (a valid "nothing matched" answer), not an error.
    """
    root = ET.fromstring(data)
    entries = _find_all(root, "ProbeMatch") + _find_all(root, "ResolveMatch")
    out = []
    for entry in entries:
        m = Match()
        addr = _find_first(entry, "Address")
        if addr is not None and addr.text:
            m.endpoint_reference = addr.text.strip()
        types_el = _find_first(entry, "Types")
        if types_el is not None and types_el.text:
            m.types = types_el.text.split()
        scopes_el = _find_first(entry, "Scopes")
        if scopes_el is not None and scopes_el.text:
            m.scopes = scopes_el.text.split()
        xaddrs_el = _find_first(entry, "XAddrs")
        if xaddrs_el is not None and xaddrs_el.text:
            m.xaddrs = xaddrs_el.text.split()
        mv = _find_first(entry, "MetadataVersion")
        if mv is not None and mv.text and mv.text.strip().isdigit():
            m.metadata_version = int(mv.text.strip())
        out.append(m)
    return out


def parse_probe(data: bytes):
    """Parse a ``Probe`` envelope -> ``{"types": [...], "scopes": [...]}``.

    Provided so task 2's responder-side unit tests can assert on what a probe
    asked for without re-implementing the parse.
    """
    root = ET.fromstring(data)
    probe = _find_first(root, "Probe")
    result = {"types": [], "scopes": []}
    if probe is None:
        return result
    t = _find_first(probe, "Types")
    if t is not None and t.text:
        result["types"] = t.text.split()
    s = _find_first(probe, "Scopes")
    if s is not None and s.text:
        result["scopes"] = s.text.split()
    return result


# --- client -------------------------------------------------------------

class WSDiscoveryClient:
    """Send probes/resolves and collect the answers off one UDP socket.

    Not thread-safe -- caller-synchronised, same contract as the rest of the
    Harpia runtime. Use as a context manager, or call :meth:`close`.
    """

    def __init__(self, timeout: float = 2.0, multicast_group: str = WSD_MULTICAST_GROUP,
                 port: int = WSD_PORT, multicast_ttl: int = 1):
        self.timeout = timeout
        self.multicast_group = multicast_group
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, multicast_ttl)
        self._sock.bind(("", 0))
        self._sock.settimeout(timeout)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass

    @property
    def source_port(self) -> int:
        return self._sock.getsockname()[1]

    def _collect(self, wanted_actions) -> list:
        """Read datagrams until the socket times out; return parsed matches.

        Raises :class:`WSDiscoveryTimeout` if not a single matching response
        arrived -- an empty read is a timeout, never a silent empty success.
        """
        matches = []
        got_response = False
        while True:
            try:
                data, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                break
            try:
                action = get_action(data)
            except ET.ParseError:
                continue
            if action not in wanted_actions:
                continue
            got_response = True
            matches.extend(parse_matches(data))
        if not got_response:
            raise WSDiscoveryTimeout(
                "no WS-Discovery response within {}s".format(self.timeout)
            )
        return matches

    def probe(self, types=None, scopes=None, to_addr=None) -> list:
        """Multicast a ``Probe`` and return the collected ``[Match]``.

        ``to_addr`` overrides the destination (an explicit ``(host, port)``),
        used by tests to target a local responder instead of the multicast
        group.
        """
        dest = to_addr or (self.multicast_group, self.port)
        self._sock.sendto(build_probe(types, scopes), dest)
        return self._collect({ACTION_PROBE_MATCHES})

    def resolve(self, endpoint_reference: str, to_addr=None) -> Match:
        """Send a ``Resolve`` for one endpoint reference; return its ``Match``."""
        dest = to_addr or (self.multicast_group, self.port)
        self._sock.sendto(build_resolve(endpoint_reference), dest)
        matches = self._collect({ACTION_RESOLVE_MATCHES})
        return matches[0]
