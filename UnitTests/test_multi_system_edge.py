"""multi-system-reference / reference-system task 4 -- `edge`, the reference
system's Linux program (`HarpiaTest/app_example/multi_system/edge/`), which
has no database.

`station` (SQLite file) + `edge` run for a few seconds against the task-1 PKI:
  * every reading edge creates over mTLS + a bearer session lands in
    station's database;
  * edge's CURVE PUB, guarded by the ZAP allowlist, delivers `live_sample`s to
    a test subscriber whose key is allowlisted (handheld's), and nothing to
    one whose key is not;
  * edge lists `field_note`s from station (the station -> edge direction);
  * the edge binary links no database library (ldd), a checked build
    property, not a convention.
"""
import os
import sqlite3
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    CPP_SKIP, HAVE_CPP, build_cpp, free_port, generate, provision, read, running,
    schema_hash, station_cmd)

pytestmark = pytest.mark.skipif(not HAVE_CPP, reason=CPP_SKIP)

# A CURVE subscriber to edge's live_sample stream, built from the generated
# C++ subscriber: counts the samples it gets in `seconds` and prints the count.
_SUB_CC = r"""
#include "zmq/live_sample_{h}_zmq.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
static std::string key(const std::string& p) {{ std::ifstream f(p); std::string k; f >> k; return k; }}
int main(int, char** argv) {{
    const std::string endpoint = argv[1], zk = argv[2], who = argv[3];
    const int seconds = std::stoi(argv[4]);
    ::zmq::context_t ctx;
    ::harpia::zmq_transport::live_sample_subscriber sub(ctx, endpoint,
        {{key(zk + "/zmq_server_public.key"), key(zk + "/zmq_" + who + "_public.key"),
          key(zk + "/zmq_" + who + "_secret.key")}});
    sub.socket().set(::zmq::sockopt::rcvtimeo, 200);
    sub.socket().set(::zmq::sockopt::linger, 0);
    std::cout << "READY" << std::endl;
    int n = 0;
    long long last_seq = -1;
    const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    while (std::chrono::steady_clock::now() < end) {{
        ::live_sample s;
        if (sub.receive(&s) && s.device_id() == "edge-test") {{ ++n; last_seq = s.seq(); }}
    }}
    std::cout << "received=" << n << " last_seq=" << last_seq << std::endl;
    return 0;
}}
"""


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"], capture_output=True, text=True)
    return out.stdout.split()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_edge")
    gen = generate(tmp / "gen")
    h = schema_hash(gen)
    cpp = os.path.join(gen, "generated", "cpp")
    src = os.path.join(str(tmp), "sub.cc")
    with open(src, "w") as f:
        f.write(_SUB_CC.format(h=h))
    sub = os.path.join(str(tmp), "sub")
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp, *_pkgconfig("--cflags"), src,
                        os.path.join(cpp, "protofiles", "live_sample_{}.pb.cc".format(h)),
                        "-o", sub, *_pkgconfig("--libs"), "-lpthread"],
                       capture_output=True, text=True, timeout=600)
    assert c.returncode == 0, c.stderr[-4000:]
    # "stranger" gets a CURVE keypair but is NOT in the allowlist
    pki = provision(tmp / "pki")
    zk = pki["zmq"]
    allow = os.path.join(zk, "allowlist.txt")
    with open(allow) as f:
        rows = f.read()
    r = subprocess.run(["sh", os.path.join(REPO_ROOT, "Assets", "cmake", "zmq_zap_provision.sh"),
                        zk, "edge", "handheld", "guest", "stranger"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with open(allow, "w") as f:          # restore: stranger keeps its keys, stays unlisted
        f.write(rows)
    return {"tmp": tmp, "gen": gen, "sub": sub, "pki": pki,
            "station": build_cpp("station", gen, str(tmp / "b_station")),
            "edge": build_cpp("edge", gen, str(tmp / "b_edge"))}


def test_edge_links_no_database(built):
    out = subprocess.run(["ldd", built["edge"]], capture_output=True, text=True).stdout
    for lib in ("soci", "sqlite", "libpq"):
        assert lib not in out, "edge links {}:\n{}".format(lib, out)
    assert "libgrpc++" in out and "libzmq" in out


def test_station_edge_and_allowlisted_subscriber(built, tmp_path):
    b = built
    pki, zk, env = b["pki"]["pki"], b["pki"]["zmq"], b["pki"]["env"]
    sport, pport = free_port(), free_port()
    db = str(tmp_path / "station.db")
    with running(station_cmd(b["station"], sport, "sqlite:" + db, pki), env,
                 str(tmp_path / "station.log"), ready_port=sport):
        endpoint = "tcp://127.0.0.1:{}".format(pport)
        edge = subprocess.Popen(
            [b["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
             "--certs", pki, "--identity", "edge", "--pub", endpoint, "--zmq-keys", zk,
             "--device", "edge-test", "--interval", "100", "--notes-every", "10",
             "--id-base", "1000", "--duration", "5"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.5)                                  # edge has bound its PUB
        subs = {who: subprocess.Popen([b["sub"], endpoint, zk, who, "3"], env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for who in ("handheld", "stranger")}
        got = {who: p.communicate(timeout=60)[0] for who, p in subs.items()}
        edge_out = edge.communicate(timeout=60)[0]
    assert edge.returncode == 0, edge_out
    assert "readings_failed=0" in edge_out, edge_out
    assert "field_notes on station: 0" in edge_out, edge_out    # the list call ran
    created = int(edge_out.split("readings_created=")[1].split()[0])
    assert created >= 30, edge_out
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT COUNT(*), MIN(device_id) FROM reading_table").fetchone()
    assert rows == (created, "edge-test")
    n_ok = int(got["handheld"].split("received=")[1].split()[0])
    assert n_ok >= 10, got["handheld"]
    assert "received=0 " in got["stranger"], got["stranger"]
