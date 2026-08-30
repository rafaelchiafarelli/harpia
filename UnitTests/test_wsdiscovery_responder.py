"""sdc-biceps task 2 -- the generated WS-Discovery responder, end to end.

One compiled program exercises two layers:

  * **socket-free core** (`Responder::handle_datagram`): a matching Probe ->
    a ProbeMatch carrying the right per-message scope + SOAP XAddrs; a Probe
    whose Types don't match -> no reply; a Resolve by endpoint reference ->
    a ResolveMatch.
  * **live**: the program starts the Stage 11 SOAP endpoint on a Crow app
    *and* the WS-Discovery `Responder` pointed at it, then the task-1
    `wsdiscovery_harness.WSDiscoveryClient` sends a real Probe, reads the
    XAddrs out of the ProbeMatch, and a plain HTTP client opens that SOAP
    URL and gets a SOAP envelope back.

Needs protoc + g++ + cc + pkg-config (the harpia Docker image); skipped
otherwise, same as the other live-HTTP stage tests.
"""
import http.client
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "cc", "pkg-config")),
    reason="needs protoc + g++ + cc + protobuf (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


PROGRAM = r'''
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include "soap/users_{h}_soap.h"
#include "sdc/users_{h}_sdc.h"
#include "sdc/patient_vitals_{h}_sdc.h"

#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>

using harpia::wsdiscovery::Responder;

static std::string probe_envelope(const std::string& types,
                                  const std::string& scopes) {{
    std::string inner = "<wsd:Probe>";
    if (!types.empty())  inner += "<wsd:Types>"  + types  + "</wsd:Types>";
    if (!scopes.empty()) inner += "<wsd:Scopes>" + scopes + "</wsd:Scopes>";
    inner += "</wsd:Probe>";
    return
      "<?xml version=\"1.0\"?><soap:Envelope "
      "xmlns:soap=\"http://www.w3.org/2003/05/soap-envelope\" "
      "xmlns:wsa=\"http://www.w3.org/2005/08/addressing\" "
      "xmlns:wsd=\"http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01\">"
      "<soap:Header>"
      "<wsa:Action>http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/Probe"
      "</wsa:Action><wsa:MessageID>urn:uuid:probe-1</wsa:MessageID></soap:Header>"
      "<soap:Body>" + inner + "</soap:Body></soap:Envelope>";
}}

static std::string resolve_envelope(const std::string& epr) {{
    return
      "<?xml version=\"1.0\"?><soap:Envelope "
      "xmlns:soap=\"http://www.w3.org/2003/05/soap-envelope\" "
      "xmlns:wsa=\"http://www.w3.org/2005/08/addressing\" "
      "xmlns:wsd=\"http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01\">"
      "<soap:Header>"
      "<wsa:Action>http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/Resolve"
      "</wsa:Action></soap:Header><soap:Body><wsd:Resolve>"
      "<wsa:EndpointReference><wsa:Address>" + epr +
      "</wsa:Address></wsa:EndpointReference></wsd:Resolve></soap:Body></soap:Envelope>";
}}

static int core_checks() {{
    Responder r;
    harpia::wsdiscovery::register_users_wsdiscovery(r, "http://127.0.0.1:0/soap");
    harpia::wsdiscovery::register_patient_vitals_wsdiscovery(r, "http://127.0.0.1:0/soap");

    // 1. empty Probe matches both; ProbeMatch carries per-message scope + XAddrs
    std::string out;
    if (!r.handle_datagram(probe_envelope("", ""), &out)) return 2;
    if (out.find("ProbeMatches") == std::string::npos) return 3;
    if (out.find("https://harpia.dev/sdc/scope/default/users") == std::string::npos) return 4;
    if (out.find("https://harpia.dev/sdc/scope/default/patient_vitals") == std::string::npos) return 5;
    if (out.find("http://127.0.0.1:0/soap/users") == std::string::npos) return 6;

    // 2. Probe scoped to one message returns only that one
    out.clear();
    if (!r.handle_datagram(
            probe_envelope("", "https://harpia.dev/sdc/scope/default/patient_vitals"),
            &out)) return 7;
    if (out.find("scope/default/patient_vitals") == std::string::npos) return 8;
    if (out.find("scope/default/users") != std::string::npos) return 9;

    // 3. Probe with an unknown type -> no reply at all
    out.clear();
    if (r.handle_datagram(probe_envelope("dpws:NoSuchType", ""), &out)) return 10;

    // 4. Resolve by endpoint reference -> ResolveMatch for that endpoint
    const std::string epr =
        harpia::wsdiscovery::users_wsdiscovery_endpoint("http://x/soap").endpoint_reference;
    out.clear();
    if (!r.handle_datagram(resolve_envelope(epr), &out)) return 11;
    if (out.find("ResolveMatches") == std::string::npos) return 12;
    if (out.find("http://127.0.0.1:0/soap/users") == std::string::npos) return 13;
    return 0;
}}

int main() {{
    const int rc = core_checks();
    if (rc != 0) {{ std::fprintf(stderr, "core check failed: %d\n", rc); return rc; }}

    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) return 30;

    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    harpia::soap::register_users_soap(app, db, "/soap");
    const int port = 18091;
    auto fut = app.bindaddr("127.0.0.1").port(port).multithreaded().run_async();
    app.wait_for_server_start();

    Responder responder;
    const std::string base = "http://127.0.0.1:" + std::to_string(port) + "/soap";
    harpia::wsdiscovery::register_users_wsdiscovery(responder, base);
    harpia::wsdiscovery::register_patient_vitals_wsdiscovery(responder, base);
    if (!responder.start()) {{
        std::fprintf(stderr, "responder.start() failed\n");
        app.stop(); fut.get();
        return 21;
    }}

    std::printf("READY %d\n", port);
    std::fflush(stdout);
    std::this_thread::sleep_for(std::chrono::seconds(30));

    responder.stop();
    app.stop(); fut.get();
    return 0;
}}
'''


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_wsd")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(build, "generated", "cpp")

    prog = os.path.join(str(out), "wsd.cpp")
    with open(prog, "w") as f:
        f.write(PROGRAM.format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    tinyxml = os.path.join(TINYXML2, "tinyxml2.cpp")
    binary = os.path.join(str(out), "wsd_app")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         "-I", CROW, "-I", ASIO, "-I", TINYXML2, "-I", HERE,
         *_pkgconfig("--cflags"), prog, pb_cc, tinyxml, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=240)
    assert c.returncode == 0, "wsd program failed to build:\n" + c.stderr
    return {"binary": binary}


def _soap_get(url, msg_id=1):
    m = re.match(r"http://([^:/]+):(\d+)(/.*)$", url)
    assert m, "unexpected XAddrs url: {}".format(url)
    host, port, path = m.group(1), int(m.group(2)), m.group(3)
    env = (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap:Header><credentials><user>users</user><pswd>{h}</pswd>'
        '</credentials></soap:Header>'
        '<soap:Body><get><id>{i}</id></get></soap:Body></soap:Envelope>'
    ).format(h=HASH, i=msg_id)
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request("POST", path, body=env, headers={"Content-Type": "text/xml"})
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


def test_discovery_then_soap_roundtrip(built):
    from wsdiscovery_harness import WSDiscoveryClient

    proc = subprocess.Popen([built["binary"]], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        # wait for READY (or an early exit meaning a core check failed)
        port = None
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            m = re.match(r"READY (\d+)", line)
            if m:
                port = int(m.group(1))
                break
        if port is None:
            proc.wait(timeout=5)
            out, err = proc.communicate()
            pytest.fail("responder program never became READY (rc={}):\n{}\n{}"
                        .format(proc.returncode, out, err))

        # 1. discover via a real Probe datagram (unicast to the ANY-bound
        #    responder socket -- no multicast routing needed in the container)
        with WSDiscoveryClient(timeout=4.0) as client:
            matches = client.probe(to_addr=("127.0.0.1", 3702))
        assert matches, "no ProbeMatch from the generated responder"

        by_scope = {s.split("/")[-1]: mtch
                    for mtch in matches for s in mtch.scopes}
        assert "users" in by_scope and "patient_vitals" in by_scope, \
            "expected both endpoints discovered, got {}".format(
                [m.scopes for m in matches])

        users = by_scope["users"]
        assert users.types == ["dpws:Device"]
        assert users.xaddrs, "ProbeMatch carried no XAddrs"
        xaddr = users.xaddrs[0]
        assert xaddr == "http://127.0.0.1:{}/soap/users".format(port), xaddr

        # 2. resolve the users endpoint by its reference
        with WSDiscoveryClient(timeout=4.0) as client:
            resolved = client.resolve(users.endpoint_reference,
                                      to_addr=("127.0.0.1", 3702))
        assert resolved.xaddrs == [xaddr]

        # 3. open the discovered SOAP endpoint -- a well-formed SOAP reply
        #    proves the connection opened and the Stage 11 endpoint is live
        status, body = _soap_get(xaddr)
        assert status == 200, (status, body)
        assert "Envelope" in body or "Fault" in body, body
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
