"""Covers the WS-Discovery test-client harness itself (sdc-biceps task 1).

Pure Python, always runs -- no C++ toolchain, no generator pipeline. The live
multicast round-trip belongs to task 2's integration test; here everything is
either a canned-fixture parse or a unicast loopback exchange, so nothing
depends on the CI network's multicast behaviour.
"""
import os
import socket
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from wsdiscovery_harness import (  # noqa: E402
    ACTION_PROBE,
    ACTION_RESOLVE,
    WSDiscoveryClient,
    WSDiscoveryTimeout,
    build_probe,
    build_resolve,
    get_action,
    parse_matches,
    parse_probe,
)

# A recorded ProbeMatches response (two matches, prefixes deliberately unlike
# the harness's own so the local-name parsing is exercised).
PROBE_MATCHES = b"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:d="http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01">
  <s:Header>
    <a:Action>http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/ProbeMatches</a:Action>
    <a:MessageID>urn:uuid:2c8f0e1a-0000-4000-8000-000000000001</a:MessageID>
    <a:RelatesTo>urn:uuid:probe-1</a:RelatesTo>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <a:EndpointReference><a:Address>urn:uuid:device-aaaa</a:Address></a:EndpointReference>
        <d:Types>dpws:Device mdpws:MedicalDevice</d:Types>
        <d:Scopes>https://harpia.dev/sdc/scope/harpiatest/patient_vitals</d:Scopes>
        <d:XAddrs>http://127.0.0.1:18077/soap/patient_vitals</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
      <d:ProbeMatch>
        <a:EndpointReference><a:Address>urn:uuid:device-bbbb</a:Address></a:EndpointReference>
        <d:Types>dpws:Device</d:Types>
        <d:Scopes>https://harpia.dev/sdc/scope/harpiatest/alarm_event</d:Scopes>
        <d:XAddrs>http://127.0.0.1:18077/soap/alarm_event http://[::1]:18077/soap/alarm_event</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>"""

RESOLVE_MATCHES = b"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:d="http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01">
  <s:Header>
    <a:Action>http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/ResolveMatches</a:Action>
  </s:Header>
  <s:Body>
    <d:ResolveMatches>
      <d:ResolveMatch>
        <a:EndpointReference><a:Address>urn:uuid:device-aaaa</a:Address></a:EndpointReference>
        <d:Types>dpws:Device</d:Types>
        <d:Scopes>https://harpia.dev/sdc/scope/harpiatest/patient_vitals</d:Scopes>
        <d:XAddrs>http://127.0.0.1:18077/soap/patient_vitals</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ResolveMatch>
    </d:ResolveMatches>
  </s:Body>
</s:Envelope>"""

EMPTY_PROBE_MATCHES = b"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:d="http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01">
  <s:Header/>
  <s:Body><d:ProbeMatches/></s:Body>
</s:Envelope>"""


# --- fixture parsing ---------------------------------------------------

def test_parse_probe_matches_extracts_every_field():
    matches = parse_matches(PROBE_MATCHES)
    assert len(matches) == 2
    first = matches[0]
    assert first.endpoint_reference == "urn:uuid:device-aaaa"
    assert first.types == ["dpws:Device", "mdpws:MedicalDevice"]
    assert first.scopes == ["https://harpia.dev/sdc/scope/harpiatest/patient_vitals"]
    assert first.xaddrs == ["http://127.0.0.1:18077/soap/patient_vitals"]
    assert first.metadata_version == 1
    # multi-valued XAddrs split on whitespace
    assert matches[1].xaddrs == [
        "http://127.0.0.1:18077/soap/alarm_event",
        "http://[::1]:18077/soap/alarm_event",
    ]


def test_parse_resolve_matches_returns_single_entry():
    matches = parse_matches(RESOLVE_MATCHES)
    assert len(matches) == 1
    assert matches[0].endpoint_reference == "urn:uuid:device-aaaa"
    assert matches[0].xaddrs == ["http://127.0.0.1:18077/soap/patient_vitals"]


def test_matches_wrapper_with_no_entries_is_empty_not_error():
    assert parse_matches(EMPTY_PROBE_MATCHES) == []


# --- message construction --------------------------------------------

def test_build_probe_is_well_formed_and_carries_the_probe_action():
    wire = build_probe(types="dpws:Device", scopes="https://harpia.dev/sdc/scope/x")
    assert get_action(wire) == ACTION_PROBE
    parsed = parse_probe(wire)
    assert parsed["types"] == ["dpws:Device"]
    assert parsed["scopes"] == ["https://harpia.dev/sdc/scope/x"]


def test_build_probe_accepts_iterables_and_omits_empty_selectors():
    wire = build_probe(types=["dpws:Device", "mdpws:MedicalDevice"])
    parsed = parse_probe(wire)
    assert parsed["types"] == ["dpws:Device", "mdpws:MedicalDevice"]
    assert parsed["scopes"] == []
    assert b"<wsd:Scopes>" not in wire


def test_build_resolve_carries_action_and_endpoint_reference():
    wire = build_resolve("urn:uuid:device-aaaa")
    assert get_action(wire) == ACTION_RESOLVE
    assert b"urn:uuid:device-aaaa" in wire


# --- socket round-trip (unicast loopback, no multicast) --------------

def _free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CannedResponder:
    """Replies to the first datagram it receives with a fixed payload."""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(5.0)
        self.addr = self.sock.getsockname()
        self.request = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        try:
            self.sock.close()
        except OSError:
            pass

    def _serve(self):
        try:
            data, peer = self.sock.recvfrom(65535)
        except (OSError, socket.timeout):
            return
        self.request = data
        self.sock.sendto(self.payload, peer)


def test_client_probe_round_trips_against_a_canned_responder():
    with _CannedResponder(PROBE_MATCHES) as responder, \
         WSDiscoveryClient(timeout=2.0) as client:
        matches = client.probe(types="dpws:Device", to_addr=responder.addr)

    assert responder.request is not None, "responder never received the probe"
    assert get_action(responder.request) == ACTION_PROBE
    assert [m.endpoint_reference for m in matches] == [
        "urn:uuid:device-aaaa",
        "urn:uuid:device-bbbb",
    ]
    assert matches[0].xaddrs == ["http://127.0.0.1:18077/soap/patient_vitals"]


def test_client_resolve_round_trips_against_a_canned_responder():
    with _CannedResponder(RESOLVE_MATCHES) as responder, \
         WSDiscoveryClient(timeout=2.0) as client:
        match = client.resolve("urn:uuid:device-aaaa", to_addr=responder.addr)
    assert match.xaddrs == ["http://127.0.0.1:18077/soap/patient_vitals"]


def test_probe_raises_timeout_when_no_one_answers():
    dead = ("127.0.0.1", _free_udp_port())
    with WSDiscoveryClient(timeout=0.3) as client:
        with pytest.raises(WSDiscoveryTimeout):
            client.probe(types="dpws:Device", to_addr=dead)


def test_timeout_not_swallowed_as_empty_success():
    """A no-response probe must raise, never return []."""
    dead = ("127.0.0.1", _free_udp_port())
    with WSDiscoveryClient(timeout=0.3) as client:
        try:
            result = client.probe(to_addr=dead)
        except WSDiscoveryTimeout:
            return
        pytest.fail("expected WSDiscoveryTimeout, got {!r}".format(result))
