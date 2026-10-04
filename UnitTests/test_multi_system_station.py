"""multi-system-reference / reference-system task 3 -- `station`, the reference
system's DB server (`HarpiaTest/app_example/multi_system/station/`).

Built with its own CMake against a project generated from the reference
schema, run against the task-1 dev PKI, and driven by this test's own C++
smoke client (deliberately not `edge`):
  * an identity with role `main` (edge) gets a session token from heartBeat and
    creates + reads back a `reading` over mTLS;
  * `guest` may read but is PERMISSION_DENIED on create;
  * a client without a certificate never gets past the TLS handshake;
  * the stats line appears, SIGINT shuts it down cleanly (exit 0);
  * `--db sqlite::memory:` is refused at startup (a pool can't use :memory:);
  * opt-in: the same against live PostgreSQL (HARPIA_PG_DSN; picked up by
    Docker/run_pg_tests.sh).
"""
import glob
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
PG_DSN = os.environ.get("HARPIA_PG_DSN")

_SMOKE_CC = r"""
#include "grpc/harpia_grpc_mtls.h"
#include "protofiles/reading_{h}_service.grpc.pb.h"
#include <grpcpp/grpcpp.h>
#include <iostream>
#include <string>
using Stub = frameworkProtos::reading_Service::Stub;

static std::unique_ptr<Stub> stub(const std::string& target, const std::string& pki,
                                  const std::string& who) {{
    std::shared_ptr<::grpc::ChannelCredentials> creds;
    if (who.empty()) {{   // CA only, no client certificate
        ::grpc::SslCredentialsOptions o;
        o.pem_root_certs = ::harpia::grpc_transport::detail::read_pem(pki + "/ca.pem");
        creds = ::grpc::SslCredentials(o);
    }} else {{
        creds = ::harpia::grpc_transport::channel_credentials(true,
            {{pki + "/ca.pem", pki + "/client_" + who + ".pem", pki + "/client_" + who + "_key.pem"}});
    }}
    return frameworkProtos::reading_Service::NewStub(::grpc::CreateChannel(target, creds));
}}
static void deadline(::grpc::ClientContext& c) {{
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(10));
}}
static std::string session(Stub& s, ::grpc::Status* st) {{
    ::grpc::ClientContext c; deadline(c);
    c.AddMetadata("harpia-issue-session", "1");
    frameworkProtos::reading_HeartBeat req, resp;
    *st = s.heartBeat(&c, req, &resp);
    auto it = c.GetServerTrailingMetadata().find("harpia-session-token");
    return it == c.GetServerTrailingMetadata().end() ? "" : std::string(it->second.data(), it->second.size());
}}
static ::grpc::Status push(Stub& s, const std::string& tok, int id, float v) {{
    ::grpc::ClientContext c; deadline(c);
    c.AddMetadata("authorization", "Bearer " + tok);
    frameworkProtos::reading_Message m;
    m.mutable_msg()->set_id_{h}(id);
    m.mutable_msg()->set_device_id("smoke");
    m.mutable_msg()->set_value(v);
    m.mutable_msg()->set_unit("C");
    frameworkProtos::errorCode ec;
    ::grpc::Status st = s.push(&c, m, &ec);
    if (st.ok() && ec.code() != 0) return ::grpc::Status(::grpc::StatusCode::INTERNAL, ec.message());
    return st;
}}

int main(int, char** argv) {{
    const std::string target = argv[1], pki = argv[2];
    ::grpc::Status st;
    // main role: session, create, read back
    auto edge = stub(target, pki, "edge");
    const std::string tok = session(*edge, &st);
    if (!st.ok() || tok.empty()) {{ std::cerr << "issue: " << st.error_message() << "\n"; return 1; }}
    if (!(st = push(*edge, tok, 7, 21.5f)).ok()) {{ std::cerr << "push: " << st.error_message() << "\n"; return 2; }}
    {{
        ::grpc::ClientContext c; deadline(c);
        c.AddMetadata("authorization", "Bearer " + tok);
        frameworkProtos::reading_ID id; id.set_id(7);
        frameworkProtos::reading_Message back;
        st = edge->pullByID(&c, id, &back);
        if (!st.ok() || back.msg().device_id() != "smoke" || back.msg().value() != 21.5f) return 3;
    }}
    // guest: may read, may not create
    auto guest = stub(target, pki, "guest");
    const std::string gtok = session(*guest, &st);
    if (gtok.empty()) return 4;
    if (push(*guest, gtok, 8, 1.0f).error_code() != ::grpc::StatusCode::PERMISSION_DENIED) return 5;
    {{
        ::grpc::ClientContext c; deadline(c);
        c.AddMetadata("authorization", "Bearer " + gtok);
        frameworkProtos::reading_ID id; id.set_id(7);
        frameworkProtos::reading_Message back;
        if (!guest->pullByID(&c, id, &back).ok()) return 6;
    }}
    // no client certificate: refused at the TLS handshake
    auto anon = stub(target, pki, "");
    session(*anon, &st);
    if (st.error_code() != ::grpc::StatusCode::UNAVAILABLE) {{
        std::cerr << "certless code=" << st.error_code() << "\n"; return 7;
    }}
    return 0;
}}
"""


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"], capture_output=True, text=True)
    return out.stdout.split()


def _build_smoke(gen, tmp):
    h = schema_hash(gen)
    cpp = os.path.join(gen, "generated", "cpp")
    src = os.path.join(str(tmp), "smoke.cc")
    with open(src, "w") as f:
        f.write(_SMOKE_CC.format(h=h))
    pbs = [os.path.join(cpp, "protofiles", n) for n in (
        "errorCode.pb.cc", "heartBeat.pb.cc", "reading_{}.pb.cc".format(h),
        "reading_{}_service.pb.cc".format(h), "reading_{}_service.grpc.pb.cc".format(h))]
    binp = os.path.join(str(tmp), "smoke")
    c = subprocess.run(["g++", "-std=c++17", "-O1", "-I", cpp, *_pkgconfig("--cflags"), src, *pbs,
                        "-o", binp, *_pkgconfig("--libs"), "-lpthread"],
                       capture_output=True, text=True, timeout=600)
    assert c.returncode == 0, c.stderr[-4000:]
    return binp


def _exercise(station, smoke, pki, env, db, tmp):
    port = free_port()
    log = os.path.join(str(tmp), "station.log")
    with running(station_cmd(station, port, db, pki, stats_every=1), env, log, ready_port=port) as p:
        r = subprocess.run([smoke, "127.0.0.1:{}".format(port), pki],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, "smoke check #{}\n{}\nstation log:\n{}".format(
            r.returncode, r.stderr, read(log))
        time.sleep(1.5)                      # at least one stats line
    assert p.returncode == 0, read(log)
    text = read(log)
    assert "mTLS required" in text
    assert "station: last 1s calls=" in text
    assert "station: shutting down" in text
    return text


@pytest.fixture(scope="module")
def sqlite_build(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_station")
    gen = generate(tmp / "gen")
    return {"tmp": tmp, "gen": gen,
            "station": build_cpp("station", gen, str(tmp / "b_station")),
            "smoke": _build_smoke(gen, tmp),
            "pki": provision(tmp / "pki")}


def test_station_serves_hardened_reading_crud(sqlite_build, tmp_path):
    b = sqlite_build
    db = "sqlite:" + str(tmp_path / "station.db")
    _exercise(b["station"], b["smoke"], b["pki"]["pki"], b["pki"]["env"], db, tmp_path)
    # the row is really in the file
    with sqlite3.connect(str(tmp_path / "station.db")) as c:
        assert c.execute("SELECT device_id, value FROM reading_table").fetchall() == [("smoke", 21.5)]


def test_station_refuses_memory_db(sqlite_build, tmp_path):
    b = sqlite_build
    r = subprocess.run(station_cmd(b["station"], free_port(), "sqlite::memory:", b["pki"]["pki"]),
                       env=b["pki"]["env"], capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "in-memory" in r.stderr or ":memory:" in r.stderr, r.stderr


def test_station_refuses_incomplete_pki(sqlite_build, tmp_path):
    b = sqlite_build
    r = subprocess.run(station_cmd(b["station"], free_port(), "sqlite:" + str(tmp_path / "x.db"),
                                   str(tmp_path / "no_such_pki")),
                       env=b["pki"]["env"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "mTLS refused" in r.stderr


@pytest.mark.skipif(not PG_DSN or not glob.glob("/usr/include/soci/postgresql"),
                    reason="opt-in live PG: HARPIA_PG_DSN (Docker/run_pg_tests.sh)")
def test_station_on_live_postgres(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_station_pg")
    gen = generate(tmp / "gen", db_backend="postgresql")
    station = build_cpp("station", gen, str(tmp / "b_station"))
    smoke = _build_smoke(gen, tmp)
    pki = provision(tmp / "pki")
    # run_pg_tests.sh starts a throwaway PostgreSQL per run, so the tables are
    # fresh; station's migrations create them.
    _exercise(station, smoke, pki["pki"], pki["env"], PG_DSN, tmp)
