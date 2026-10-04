"""multi-system-reference / db-concurrency task 2 -- the generated REST + SOAP
server (`http/http_server_bringup.h`'s `HttpServer`) over a
::soci::connection_pool.

Before this task every REST route and SOAP endpoint captured one
`soci::session&` shared by all requests, while Crow's `multithreaded()` run
serves them on many threads -- the same race task 1a removed from gRPC. Now
`register_<name>` / `register_<name>_soap` and `HttpServer` also take a pool
(the session overloads stay, additive), and each request borrows its own
session through `harpia::db::PooledSession` after the access gate:
  * borrow deadline -> HTTP 503 "db pool exhausted" (SOAP: 503 + a Fault)
  * dead connection that can't reconnect -> 503 "db reconnect failed"
  * the REST list route gives the session back before serializing rows
  * a pool of SQLite :memory: connections is refused (std::invalid_argument)

Layers:
  * structural (pure Python, always)
  * HTTP (protoc + g++ + SOCI sqlite3, file DB via open_sqlite_pool,
    low-risk profile so the flat X-User/X-Pswd / <credentials> gates apply):
    the pool overloads of register_users / register_users_soap on one
    crow::SimpleApp -- concurrent REST + SOAP writers, exhaustion on both,
    gate-before-borrow, recovery. (The fixture's `protected` message forces the
    whole-project HttpServer bring-up onto TLS, which the plain test client
    can't speak, so the bring-up's pool constructors are checked structurally;
    refuse_sqlite_memory_pool itself is unit-tested by
    test_db_concurrency_audit.py.)
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests.test_grpc_db_pool import _generate, _have_soci_sqlite  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ==========================================================================
# structural -- pure Python, always runs
# ==========================================================================

@pytest.fixture(scope="module")
def pipeline_out(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("harpia_http_pool_struct"))
    r = subprocess.run([sys.executable, RUNNER, out], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(out, "build", "generated", "cpp")


def test_every_route_borrows_through_pooled_session(pipeline_out):
    rest = glob.glob(os.path.join(pipeline_out, "rest", "*_{}_rest.h".format(HASH)))
    soap = glob.glob(os.path.join(pipeline_out, "soap", "*_{}_soap.h".format(HASH)))
    assert rest and len(rest) == len(soap)
    for h in rest:
        text = _read(h)
        name = os.path.basename(h)[:-len("_{}_rest.h".format(HASH))]
        assert '#include "db/harpia_db_pool.h"' in text, h
        # list, read, create, update, remove each borrow exactly once
        assert text.count("::harpia::db::PooledSession lease(db, pool, lease_timeout_ms);") == 5, h
        assert "register_{}_with(".format(name) in text, h
        assert "register_{}(crow::SimpleApp& app, ::soci::connection_pool& pool,".format(name) in text, h
        assert "register_{}(crow::SimpleApp& app, ::soci::session& db,".format(name) in text, h
        assert '"db pool exhausted" : "db reconnect failed"' in text, h
        assert "dao(*dbp)" not in text and "dbp" not in text, h
    for h in soap:
        text = _read(h)
        assert '#include "db/harpia_db_pool.h"' in text, h
        assert text.count("::harpia::db::PooledSession lease(db, pool, lease_timeout_ms);") == 1, h
        # the borrow comes after the operation parse + access gate
        assert text.index("find_operation(doc, &soap_req)") < text.index("PooledSession lease("), h
        assert "dbp" not in text, h


def test_bringup_has_pool_constructors(pipeline_out):
    bringup = _read(os.path.join(pipeline_out, "http", "http_server_bringup.h"))
    assert '#include "db/harpia_db_pool.h"' in bringup
    assert bringup.count("HttpServer(::soci::connection_pool& pool,") == 2   # SSL + plain builds
    assert bringup.count("HttpServer(::soci::session& db,") == 2            # still there (additive)
    assert bringup.count("::harpia::db::refuse_sqlite_memory_pool(pool, lease_timeout_ms);") == 2
    assert "register_users_with(app_, db, pool, lease_timeout_ms, rest_base);" in bringup
    assert "register_users_soap_with(app_, db, pool, lease_timeout_ms, soap_base);" in bringup
    assert os.path.isfile(os.path.join(pipeline_out, "db", "harpia_db_pool.h"))


# ==========================================================================
# HTTP -- generated HttpServer over a file-SQLite pool
# ==========================================================================

_http = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "grpc_cpp_plugin", "g++", "pkg-config"))
    or not _have_soci_sqlite(),
    reason="needs protoc + g++ + protobuf + SOCI sqlite3 (harpia Docker image)")

_ENV = '<soap:Envelope xmlns:soap=\\"http://schemas.xmlsoap.org/soap/envelope/\\">'
_HDR = ('<soap:Header><credentials><user>users</user><pswd>{h}</pswd>'
        '</credentials></soap:Header>'.format(h=HASH))

_HTTP_POOL_CC = r"""
#include "rest/users_{h}_rest.h"
#include "soap/users_{h}_soap.h"
#include "harpia_test_client.h"
#include <soci/sqlite3/soci-sqlite3.h>
#include <atomic>
#include <chrono>
#include <string>
#include <thread>
#include <vector>
using Clock = std::chrono::steady_clock;
static long since(Clock::time_point t0) {{
    return (long)std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count();
}}
static const std::string ENV = "{env}";
static const std::string HDR = "{hdr}";
static std::string soap_set(const ::users& u) {{
    return ENV + HDR + "<soap:Body><set>" + ::harpia::xml::to_xml(u) + "</set></soap:Body></soap:Envelope>";
}}
static std::string soap_get(int id) {{
    return ENV + HDR + "<soap:Body><get><id>" + std::to_string(id) + "</id></get></soap:Body></soap:Envelope>";
}}
static harpia_test::Client client(int port) {{
    harpia_test::Client c("127.0.0.1", port);
    c.set_default_headers({{{{"X-User", "users"}}, {{"X-Pswd", "{h}"}}}});
    return c;
}}

int main(int, char** argv) {{
    const std::string file = argv[1];
    const int port = std::atoi(argv[2]);

    const int kPool = 2;
    ::soci::connection_pool pool(kPool);
    harpia::db::open_sqlite_pool(pool, kPool, ::soci::sqlite3, file);
    {{
        harpia::db::PooledSession l(nullptr, &pool, 2000);
        if (!harpia::db::users_dao(l.session()).create_table()) return 2;
    }}
    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    harpia::rest::register_users(app, pool, "/api", 300);
    harpia::soap::register_users_soap(app, pool, "/soap", 300);
    auto fut = app.bindaddr("127.0.0.1").port(port).multithreaded().run_async();
    app.wait_for_server_start();

    auto run = [&]() -> int {{
        // concurrent writers + readers: 8 REST threads x 25, 4 SOAP threads x 25
        std::atomic<int> bad{{0}};
        std::vector<std::thread> ts;
        for (int t = 0; t < 8; ++t) ts.emplace_back([&, t] {{
            auto cli = client(port);
            for (int i = 0; i < 25; ++i) {{
                const int id = 1 + t * 1000 + i;
                ::users u; u.set_id_{h}(id); u.set_name("r" + std::to_string(id));
                std::string body; ::harpia::json::to_json(u, &body);
                auto p = cli.Post("/api/users", body, "application/json");
                if (!p || p.status != 201) {{ ++bad; continue; }}
                auto g = cli.Get("/api/users/" + std::to_string(id));
                if (!g || g.status != 200 || g.body.find("r" + std::to_string(id)) == std::string::npos) ++bad;
                if (i % 10 == 0) {{
                    auto l = cli.Get("/api/users?limit=3");
                    if (!l || l.status != 200) ++bad;
                }}
            }}
        }});
        for (int t = 0; t < 4; ++t) ts.emplace_back([&, t] {{
            harpia_test::Client cli("127.0.0.1", port);
            for (int i = 0; i < 25; ++i) {{
                const int id = 50000 + t * 1000 + i;
                ::users u; u.set_id_{h}(id); u.set_name("s" + std::to_string(id));
                auto s = cli.Post("/soap/users", soap_set(u), "text/xml");
                if (!s || s.status != 200 || s.body.find("<ok>true</ok>") == std::string::npos) {{ ++bad; continue; }}
                auto g = cli.Post("/soap/users", soap_get(id), "text/xml");
                if (!g || g.status != 200 || g.body.find("s" + std::to_string(id)) == std::string::npos) ++bad;
            }}
        }});
        for (auto& t : ts) t.join();
        if (bad.load() != 0) return 3;
        {{
            harpia::db::PooledSession l(nullptr, &pool, 2000);
            int n = -1;
            l.session() << "SELECT COUNT(*) FROM user_table", ::soci::into(n);
            if (n != 8 * 25 + 4 * 25) return 4;
        }}

        // exhaustion: every slot held -> REST 503 after ~the deadline ...
        {{
            std::size_t a = pool.lease(), b = pool.lease();
            auto cli = client(port);
            auto t0 = Clock::now();
            auto r = cli.Get("/api/users/1");
            const long ms = since(t0);
            // ... and SOAP 503 + Fault
            harpia_test::Client sc("127.0.0.1", port);
            auto s = sc.Post("/soap/users", soap_get(1), "text/xml");
            pool.give_back(a);
            pool.give_back(b);
            if (!r || r.status != 503 || r.body != "db pool exhausted") return 5;
            if (ms < 250 || ms > 5000) return 6;
            if (!s || s.status != 503 || s.body.find("db pool exhausted") == std::string::npos) return 7;
        }}
        // the gate still runs before the borrow: a bad credential is 401, not 503
        {{
            std::size_t a = pool.lease(), b = pool.lease();
            harpia_test::Client anon("127.0.0.1", port);
            auto r = anon.Get("/api/users/1");
            pool.give_back(a);
            pool.give_back(b);
            if (!r || r.status != 401) return 8;
        }}
        // and the server keeps serving afterwards
        auto cli = client(port);
        auto g = cli.Get("/api/users/1");
        if (!g || g.status != 200) return 9;
        return 0;
    }};
    const int code = run();
    app.stop();
    fut.get();
    return code;
}}
"""


@pytest.fixture(scope="module")
def http_build(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_http_pool"))
    cpp_root = _generate(os.path.join(tmp, "gen"))
    return {"tmp": tmp, "cpp_root": cpp_root}


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"], capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@_http
def test_pooled_http_server_concurrency_exhaustion_and_legacy(http_build):
    src = os.path.join(http_build["tmp"], "http_pool.cc")
    with open(src, "w") as f:
        f.write(_HTTP_POOL_CC.format(h=HASH, env=_ENV, hdr=_HDR))
    cpp_root = http_build["cpp_root"]
    pb_srcs = [os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))]
    binp = os.path.join(http_build["tmp"], "http_pool")
    c = subprocess.run(
        ["g++", "-std=c++17", "-O1", "-I", cpp_root, "-I", CROW, "-I", ASIO,
         "-I", TINYXML2, "-I", HERE, *_pkgconfig("--cflags"), src, *pb_srcs,
         os.path.join(TINYXML2, "tinyxml2.cpp"), "-o", binp,
         "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, "HTTP pool program failed to build:\n" + c.stderr[-6000:]
    r = subprocess.run([binp, os.path.join(http_build["tmp"], "http.db"), "18193"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, "HTTP pool check #{}\n{}{}".format(
        r.returncode, r.stdout[-2000:], r.stderr[-4000:])
