"""Minimal WS-Discovery (OASIS WS-DD 2009) probe/resolve responder (Python
port of ``SdcAdapter/runtime/harpia_wsdiscovery.h``).

Hand-written, copied into a generated project as ``harpia_runtime.wsdiscovery``.
Answers multicast ``Probe`` and unicast ``Resolve`` datagrams on
``239.255.255.250:3702`` so an IEEE 11073 SDC / DPWS-aware client can find this
project's SOAP endpoints with zero configuration. **Additive:** a
``ProbeMatch`` only carries the SOAP URL in ``XAddrs``; the endpoint itself is
unchanged.

Messages are byte-for-byte the C++ ones (:func:`build_response`). Inbound
datagrams are parsed by :func:`harpia_runtime.soap.parse_envelope` -- no
namespace processing (names stay ``prefix:local``, as tinyxml2) and any DTD /
entity declaration refused, so no entity expansion.

Matching (WS-Discovery default): every requested type must be one of the
endpoint's types, and every requested scope a prefix of one of its scopes; an
empty selector matches everything. A probe matching nothing gets no answer.

Threading: register every endpoint with :meth:`Responder.add` before
:meth:`Responder.start`; ``start`` runs one daemon listener thread, ``stop``
closes the socket and joins it. :meth:`Responder.handle_datagram` is pure.
"""
import socket
import struct
import threading
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from harpia_runtime.soap import local_name, parse_envelope

#: standard WS-Discovery IPv4 multicast group / UDP port
MULTICAST_GROUP = "239.255.255.250"
PORT = 3702

_WSD = "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01"
ACTION_PROBE = _WSD + "/Probe"
ACTION_PROBE_MATCHES = _WSD + "/ProbeMatches"
ACTION_RESOLVE = _WSD + "/Resolve"
ACTION_RESOLVE_MATCHES = _WSD + "/ResolveMatches"


@dataclass
class Endpoint:
    """One advertised endpoint (the SOAP service of one generated message)."""

    #: stable ``urn:uuid:`` endpoint reference
    endpoint_reference: str
    #: QNames, e.g. ``["dpws:Device"]``
    types: list[str] = field(default_factory=list)
    #: scope URIs
    scopes: list[str] = field(default_factory=list)
    #: transport address (the SOAP URL)
    xaddrs: str = ""


class Kind(Enum):
    """What a datagram asked for."""

    none = "none"
    probe = "probe"
    resolve = "resolve"


@dataclass
class Request:
    """A parsed inbound Probe or Resolve."""

    kind: Kind = Kind.none
    #: ``wsa:MessageID``, echoed as ``RelatesTo``
    message_id: str = ""
    types: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    #: the Resolve target's endpoint reference
    target_epr: str = ""


def _first_by_local(el: ET.Element | None, want: str) -> ET.Element | None:
    """Depth-first: the first element (``el`` included) with local name
    ``want``."""
    if el is None:
        return None
    if local_name(el) == want:
        return el
    for child in el:
        hit = _first_by_local(child, want)
        if hit is not None:
            return hit
    return None


def _text(el: ET.Element | None) -> str:
    return (el.text or "") if el is not None else ""


def _ws_tokens(s: str) -> list[str]:
    """Split on space / tab / CR / LF only (C++ ``split_ws``)."""
    out: list[str] = []
    cur = ""
    for ch in s:
        if ch in " \t\n\r":
            if cur:
                out.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def parse_request(datagram: str | bytes) -> Request:
    """Parse one datagram; unparsable or not Probe/Resolve → ``Kind.none``."""
    root = parse_envelope(datagram)
    req = Request()
    if root is None:
        return req
    action = _text(_first_by_local(root, "Action"))
    req.message_id = _text(_first_by_local(root, "MessageID"))
    if action == ACTION_PROBE:
        req.kind = Kind.probe
        probe = _first_by_local(root, "Probe")
        if probe is not None:
            req.types = _ws_tokens(_text(_first_by_local(probe, "Types")))
            req.scopes = _ws_tokens(_text(_first_by_local(probe, "Scopes")))
    elif action == ACTION_RESOLVE:
        req.kind = Kind.resolve
        resolve = _first_by_local(root, "Resolve")
        if resolve is not None:
            req.target_epr = _text(_first_by_local(resolve, "Address"))
    return req


def endpoint_matches(ep: Endpoint, req: Request) -> bool:
    """WS-Discovery default matching (see the module docstring)."""
    return (all(t in ep.types for t in req.types)
            and all(any(es.startswith(s) for es in ep.scopes) for s in req.scopes))


def build_match(ep: Endpoint, resolve: bool) -> str:
    """One ``ProbeMatch`` / ``ResolveMatch`` element."""
    wrap = "ResolveMatch" if resolve else "ProbeMatch"
    return (f"<wsd:{wrap}><wsa:EndpointReference><wsa:Address>"
            f"{_escape(ep.endpoint_reference)}</wsa:Address></wsa:EndpointReference>"
            '<wsd:Types xmlns:dpws="http://docs.oasis-open.org/ws-dd/ns/dpws/2009/01">'
            f"{_escape(' '.join(ep.types))}</wsd:Types><wsd:Scopes>"
            f"{_escape(' '.join(ep.scopes))}</wsd:Scopes><wsd:XAddrs>"
            f"{_escape(ep.xaddrs)}</wsd:XAddrs>"
            f"<wsd:MetadataVersion>1</wsd:MetadataVersion></wsd:{wrap}>")


def build_response(matches: Sequence[Endpoint], relates_to: str, resolve: bool) -> str:
    """A full ``ProbeMatches`` / ``ResolveMatches`` SOAP 1.2 envelope."""
    action = ACTION_RESOLVE_MATCHES if resolve else ACTION_PROBE_MATCHES
    wrap = "ResolveMatches" if resolve else "ProbeMatches"
    related = (f"<wsa:RelatesTo>{_escape(relates_to)}</wsa:RelatesTo>"
               if relates_to else "")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:wsa="http://www.w3.org/2005/08/addressing"'
            f' xmlns:wsd="{_WSD}">'
            f"<soap:Header><wsa:Action>{action}</wsa:Action>{related}</soap:Header>"
            f"<soap:Body><wsd:{wrap}>"
            + "".join(build_match(ep, resolve) for ep in matches)
            + f"</wsd:{wrap}></soap:Body></soap:Envelope>")


class Responder:
    """Holds the advertised endpoints and answers probes."""

    def __init__(self) -> None:
        self.endpoints: list[Endpoint] = []
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def add(self, ep: Endpoint) -> None:
        """Register an endpoint to advertise (before :meth:`start`)."""
        self.endpoints.append(ep)

    def handle_datagram(self, data: str | bytes) -> bytes | None:
        """The answer to one datagram, or ``None`` when nothing should be sent
        (unparsable, not Probe/Resolve, a probe matching nothing, a resolve
        for an unknown reference). Socket-free."""
        req = parse_request(data)
        if req.kind is Kind.probe:
            matches = [ep for ep in self.endpoints if endpoint_matches(ep, req)]
            if not matches:
                return None
            return build_response(matches, req.message_id, False).encode("utf-8")
        if req.kind is Kind.resolve:
            for ep in self.endpoints:
                if ep.endpoint_reference == req.target_epr:
                    return build_response([ep], req.message_id, True).encode("utf-8")
        return None

    def start(self, port: int = PORT) -> bool:
        """Bind ``0.0.0.0:port``, join the multicast group and start the
        listener thread; ``False`` if the socket couldn't be set up.
        Idempotent while running."""
        if self._running.is_set():
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(("0.0.0.0", port))
            mreq = struct.pack("4s4s", socket.inet_aton(MULTICAST_GROUP),
                               socket.inet_aton("0.0.0.0"))
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError:
                pass  # no multicast route: still answers unicast, as C++
            sock.settimeout(0.2)
        except OSError:
            sock.close()
            return False
        self._sock = sock
        self._running.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the listener and close the socket (safe when not running)."""
        self._running.clear()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _loop(self) -> None:
        sock = self._sock
        assert sock is not None
        while self._running.is_set():
            try:
                data, peer = sock.recvfrom(8192)
            except TimeoutError:
                continue
            except OSError:
                break
            out = self.handle_datagram(data)
            if out:
                try:
                    sock.sendto(out, peer)
                except OSError:
                    pass
