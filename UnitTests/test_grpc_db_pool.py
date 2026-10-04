"""multi-system-reference / db-concurrency task 1a -- the generated gRPC server
over a ::soci::connection_pool.

Before this task every generated `<name>_service` held one `soci::session&`
shared by all RPCs, and gRPC calls handlers from a thread pool: a data race
the moment two clients call at once. Now each service (and `GrpcServer`)
also has a pool constructor, and every RPC borrows its own session through
`harpia::db::PooledSession` (`Database/runtime/harpia_db_pool.h`, copied to
`generated/cpp/db/`), which enforces:
  1. borrow deadline -> RESOURCE_EXHAUSTED "db pool exhausted"
  2. one borrow per RPC (debug assert on a second borrow on one thread)
  3. reconnect on borrow -> UNAVAILABLE "db reconnect failed" if it can't
  4. rollback before give-back when the handler exits by exception
     (generated code opens transactions only via soci::transaction, so a
     normal exit can't leave one open -- structurally checked below)
  5. always give back

Layers:
  * structural (pure Python, always)
  * runtime unit (g++ + SOCI sqlite3, file DB): PooledSession on its own
  * gRPC (C++ gRPC toolchain + SOCI sqlite3, file DB, low-risk profile so the
    in-process calls use the flat x-user/x-pswd gate): concurrent reads,
    exhaustion, the legacy single-session constructor
  * live PostgreSQL (opt-in, HARPIA_PG_DSN -- `Docker/run_pg_tests.sh
    UnitTests/test_grpc_db_pool.py`): 32 clients x 200 mixed CRUDL calls with
    no lost or corrupted rows, reconnect after pg_terminate_backend, rollback
"""
import concurrent.futures
import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
POOL_SRC = os.path.join(REPO_ROOT, "Database", "runtime", "harpia_db_pool.h")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PG_DSN = os.environ.get("HARPIA_PG_DSN")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _have(pkg):
    return (shutil.which("pkg-config") is not None
            and subprocess.run(["pkg-config", "--exists", pkg]).returncode == 0)


def _have_soci_sqlite():
    return os.path.exists("/usr/include/soci/sqlite3/soci-sqlite3.h")


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


_LOW_RISK = "risk_class: class_a\ntopology: standalone\n"


def _generate(out, db_backend=None):
    """main.py into `out` under a low-risk profile (flat gRPC gate); returns
    generated/cpp. main.py also runs protoc + grpc_cpp_plugin."""
    os.makedirs(out, exist_ok=True)
    cfg = os.path.join(out, "low_risk.harpia.yaml")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write(_LOW_RISK)
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out, HARPIA_COMPLIANCE_CONFIG=cfg,
               HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
               HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include")
    if db_backend:
        env["HARPIA_DB_BACKEND"] = db_backend
    else:
        env.pop("HARPIA_DB_BACKEND", None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(out, "generated", "cpp")


def _pb_archive(cpp_root, tmp):
    """Compile every generated .pb.cc once, in parallel, into one archive (the
    bring-up header includes every service, so a server links all of them)."""
    srcs = glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
    objdir = os.path.join(tmp, "pbobj")
    os.makedirs(objdir, exist_ok=True)

    def cc(src):
        obj = os.path.join(objdir, os.path.basename(src) + ".o")
        c = subprocess.run(["g++", "-std=c++17", "-c", "-I", cpp_root,
                            *_pkgconfig("--cflags"), src, "-o", obj],
                           capture_output=True, text=True)
        assert c.returncode == 0, c.stderr
        return obj

    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        objs = list(ex.map(cc, srcs))
    lib = os.path.join(tmp, "libharpia_pb.a")
    subprocess.run(["ar", "rcs", lib, *objs], check=True)
    return lib


# ==========================================================================
# structural -- pure Python, always runs
# ==========================================================================

@pytest.fixture(scope="module")
def pipeline_out(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("harpia_db_pool_struct"))
    r = subprocess.run([sys.executable, RUNNER, out], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(out, "build", "generated", "cpp")


def test_pool_runtime_shipped_verbatim(pipeline_out):
    shipped = os.path.join(pipeline_out, "db", "harpia_db_pool.h")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(POOL_SRC)


def test_every_service_borrows_through_pooled_session(pipeline_out):
    headers = glob.glob(os.path.join(pipeline_out, "grpc", "*_{}_grpc.h".format(HASH)))
    assert headers
    for h in headers:
        text = _read(h)
        assert '#include "db/harpia_db_pool.h"' in text, h
        assert "::soci::connection_pool& pool" in text, h
        # push, pullByID, streamSrc each borrow exactly once
        assert text.count("::harpia::db::PooledSession lease(db_, pool_, lease_timeout_ms_);") == 3, h
        assert "RESOURCE_EXHAUSTED, \"db pool exhausted\"" in text, h
        assert "UNAVAILABLE, \"db reconnect failed\"" in text, h
        # no DAO is ever built on the shared member directly any more
        assert "_dao dao(db_)" not in text, h


def test_bringup_has_pool_constructors(pipeline_out):
    bringup = _read(os.path.join(pipeline_out, "grpc", "grpc_server_bringup.h"))
    assert "GrpcServer(::soci::connection_pool& pool, const std::string& addr," in bringup
    assert "explicit GrpcServer(::soci::connection_pool& pool," in bringup
    # the pre-pool constructors are still there (additive)
    assert "GrpcServer(::soci::session& db, const std::string& addr," in bringup
    assert "explicit GrpcServer(::soci::session& db)" in bringup


_RAW_BEGIN = re.compile(r"^\s*[\w:>.\-()\[\]]+\s*(?:\.|->)\s*begin\(\)\s*;", re.M)


def test_generated_code_never_opens_a_raw_transaction(pipeline_out):
    """Rule 4's structural half: generated code opens transactions only via
    ::soci::transaction (RAII rollback unless committed), never a bare
    session.begin() that a normal return could leave open."""
    offenders = []
    for sub in ("db", "grpc", "migrate", "dbio"):
        for h in glob.glob(os.path.join(pipeline_out, sub, "*.h")):
            if os.path.basename(h) == "harpia_db_pool.h":
                continue
            for m in _RAW_BEGIN.finditer(_read(h)):
                offenders.append("{}: {}".format(os.path.basename(h), m.group(0).strip()))
    assert not offenders, offenders


# ==========================================================================
# runtime unit -- g++ + SOCI sqlite3, PooledSession on its own
# ==========================================================================

_unit = pytest.mark.skipif(
    shutil.which("g++") is None or not _have_soci_sqlite(),
    reason="needs g++ + SOCI sqlite3 backend (harpia Docker image)")

_UNIT_CC = r"""
#include "harpia_db_pool.h"
#include <soci/sqlite3/soci-sqlite3.h>
#include <chrono>
#include <string>
#include <thread>
using harpia::db::PooledSession;
using Clock = std::chrono::steady_clock;

int main(int, char** argv) {
    const std::string file = argv[1];
    ::soci::connection_pool pool(2);
    for (std::size_t i = 0; i < 2; ++i) pool.at(i).open(::soci::sqlite3, file);
    pool.at(0) << "CREATE TABLE IF NOT EXISTS t (v INTEGER)";

    // single-session mode wraps the given session, no lease
    {
        ::soci::session s(::soci::sqlite3, file);
        PooledSession l(&s, nullptr);
        if (!l.ok() || &l.session() != &s) return 1;
    }
    // rule 1: every slot held -> exhausted after ~the deadline, never a hang
    {
        std::size_t a = pool.lease(), b = pool.lease();
        PooledSession::Outcome out = PooledSession::Outcome::ok;
        long ms = 0;
        std::thread t([&] {
            const auto t0 = Clock::now();
            PooledSession l(nullptr, &pool, 300);
            out = l.outcome();
            ms = (long)std::chrono::duration_cast<std::chrono::milliseconds>(
                     Clock::now() - t0).count();
        });
        t.join();
        pool.give_back(a);
        pool.give_back(b);
        if (out != PooledSession::Outcome::exhausted) return 2;
        if (ms < 250 || ms > 3000) return 3;
    }
    // rule 5: given back on every path, exceptions included
    for (int i = 0; i < 100; ++i) {
        try {
            PooledSession l(nullptr, &pool, 1000);
            if (!l.ok()) return 4;
            if (i % 3 == 0) throw 1;
        } catch (int) {
        }
    }
    {
        std::size_t a, b;
        if (!pool.try_lease(a, 100) || !pool.try_lease(b, 100)) return 5;
        pool.give_back(a);
        pool.give_back(b);
    }
    // rule 4: a throw mid-transaction is rolled back before give-back
    ::soci::connection_pool one(1);
    one.at(0).open(::soci::sqlite3, file);
    try {
        PooledSession l(nullptr, &one, 1000);
        l.session().begin();
        l.session() << "INSERT INTO t (v) VALUES (42)";
        throw 7;
    } catch (int) {
    }
    {
        PooledSession l(nullptr, &one, 1000);
        int n = -1;
        l.session() << "SELECT COUNT(*) FROM t WHERE v = 42", ::soci::into(n);
        if (n != 0) return 6;
        try {                        // SQLite: begin inside an open txn throws
            l.session().begin();
            l.session().commit();
        } catch (...) {
            return 7;
        }
    }
    return 0;
}
"""

_NESTED_CC = r"""
#include "harpia_db_pool.h"
#include <soci/sqlite3/soci-sqlite3.h>
int main(int, char** argv) {
    ::soci::connection_pool pool(2);
    for (std::size_t i = 0; i < 2; ++i) pool.at(i).open(::soci::sqlite3, argv[1]);
    harpia::db::PooledSession outer(nullptr, &pool, 500);
    harpia::db::PooledSession inner(nullptr, &pool, 500);   // rule 2 violation
    return 0;
}
"""


def _build_unit(tmp_path, name, source, *flags):
    src = tmp_path / (name + ".cc")
    src.write_text(source, encoding="utf-8")
    binp = tmp_path / name
    c = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *flags,
                        "-I", os.path.dirname(POOL_SRC), str(src), "-o", str(binp),
                        "-lsoci_core", "-lsoci_sqlite3", "-lpthread", "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    return str(binp)


@_unit
def test_pooled_session_rules(tmp_path):
    binp = _build_unit(tmp_path, "pool_unit", _UNIT_CC)
    r = subprocess.run([binp, str(tmp_path / "unit.db")], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, "PooledSession check #{}\n{}".format(r.returncode, r.stderr)


@_unit
def test_second_borrow_on_one_thread_asserts_in_debug(tmp_path):
    binp = _build_unit(tmp_path, "pool_nested", _NESTED_CC)
    r = subprocess.run([binp, str(tmp_path / "nested.db")], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode != 0, "nested borrow was not caught"
    assert "rule 2" in r.stderr, r.stderr


_CLOCK_SHIM_C = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <sys/time.h>
/* The next gettimeofday() after HARPIA_TEST_CLOCK_STEP_ONCE=1 is set reads 3 s
   behind the kernel's CLOCK_REALTIME -- to SOCI's deadline arithmetic that is
   exactly a +3 s wall-clock step happening mid-wait. */
int gettimeofday(struct timeval *restrict tv, void *restrict tz) {
    static int (*real)(struct timeval *, void *) = 0;
    if (!real) real = (int (*)(struct timeval *, void *))dlsym(RTLD_NEXT, "gettimeofday");
    int r = real(tv, tz);
    const char *s = getenv("HARPIA_TEST_CLOCK_STEP_ONCE");
    if (s && s[0] == '1') {
        unsetenv("HARPIA_TEST_CLOCK_STEP_ONCE");
        tv->tv_sec -= 3;
    }
    return r;
}
"""

_CLOCK_STEP_CC = r"""
#include "harpia_db_pool.h"
#include <soci/sqlite3/soci-sqlite3.h>
#include <chrono>
#include <cstdlib>
using Clock = std::chrono::steady_clock;
static long since(Clock::time_point t0) {
    return (long)std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - t0).count();
}
int main() {
    ::soci::connection_pool pool(1);
    pool.at(0).open(::soci::sqlite3, ":memory:");
    std::size_t held = pool.lease();                 // the only slot is busy

    // the SOCI 4.0.x bug: a wall-clock step ends the wait at once
    setenv("HARPIA_TEST_CLOCK_STEP_ONCE", "1", 1);
    std::size_t pos;
    auto t0 = Clock::now();
    const bool raw = pool.try_lease(pos, 1000);
    const long raw_ms = since(t0);
    if (raw) return 1;
    if (raw_ms > 300) return 2;                       // shim not effective: test proves nothing

    // PooledSession keeps its deadline on the monotonic clock
    setenv("HARPIA_TEST_CLOCK_STEP_ONCE", "1", 1);
    t0 = Clock::now();
    harpia::db::PooledSession::Outcome out;
    {
        harpia::db::PooledSession l(nullptr, &pool, 1000);
        out = l.outcome();
    }
    const long ms = since(t0);
    pool.give_back(held);
    if (out != harpia::db::PooledSession::Outcome::exhausted) return 3;
    if (ms < 900) return 4;
    return 0;
}
"""


@_unit
def test_borrow_deadline_survives_a_wall_clock_step(tmp_path):
    """Regression: SOCI 4.0.x's POSIX try_lease() takes its deadline from the
    wall clock, so a forward step (NTP, VM resume, WSL2's ~every-32-s resync)
    made waiting borrows fail after ~0 ms -- seen as sporadic "db pool
    exhausted" under load. PooledSession must still wait its full deadline."""
    if shutil.which("gcc") is None:
        pytest.skip("needs gcc for the LD_PRELOAD clock shim")
    shim_src = tmp_path / "clock_step_shim.c"
    shim_src.write_text(_CLOCK_SHIM_C, encoding="utf-8")
    shim = tmp_path / "clock_step_shim.so"
    c = subprocess.run(["gcc", "-shared", "-fPIC", "-O1", str(shim_src), "-o", str(shim), "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    binp = _build_unit(tmp_path, "clock_step", _CLOCK_STEP_CC)
    r = subprocess.run([binp], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "LD_PRELOAD": str(shim)})
    assert r.returncode == 0, "clock-step check #{}\n{}".format(r.returncode, r.stderr)


# ==========================================================================
# gRPC -- generated GrpcServer over a pool (SQLite file)
# ==========================================================================

_grpc = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "grpc_cpp_plugin", "g++", "ar"))
    or not _have("grpc++") or not _have_soci_sqlite(),
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ + SOCI sqlite3 (harpia Docker image)")

_CLIENT_HELPERS = r"""
#include "grpc/grpc_server_bringup.h"
#include "db/users_{h}_crudl.h"
#include <grpcpp/grpcpp.h>
#include <atomic>
#include <chrono>
#include <string>
#include <thread>
#include <vector>
#include <iostream>
#include <mutex>
using Clock = std::chrono::steady_clock;
using Stub = ::frameworkProtos::users_Service::Stub;

// First few failing RPCs to stderr, so a failure says what went wrong.
static std::mutex report_mu;
static int reported = 0;
static bool report(const char* op, int id, const ::grpc::Status& st, long ms = -1) {{
    std::lock_guard<std::mutex> lk(report_mu);
    if (reported++ < 5)
        std::cerr << op << " id=" << id << " code=" << st.error_code()
                  << " msg=" << st.error_message() << " ms=" << ms << std::endl;
    return false;
}}
static long since(Clock::time_point t0) {{
    return (long)std::chrono::duration_cast<std::chrono::milliseconds>(
        Clock::now() - t0).count();
}}

static void auth(::grpc::ClientContext& c) {{
    c.AddMetadata("x-user", "users");
    c.AddMetadata("x-pswd", "{h}");
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(20));
}}
static ::grpc::Status push(Stub& s, int id, const std::string& name) {{
    ::grpc::ClientContext c; auth(c);
    ::frameworkProtos::users_Message req;
    req.mutable_msg()->set_id_{h}(id);
    req.mutable_msg()->set_name(name);
    ::frameworkProtos::errorCode ec;
    ::grpc::Status st = s.push(&c, req, &ec);
    if (st.ok() && ec.code() != 0) return ::grpc::Status(::grpc::StatusCode::INTERNAL, ec.message());
    return st;
}}
static ::grpc::Status pull(Stub& s, int id, std::string* name) {{
    ::grpc::ClientContext c; auth(c);
    ::frameworkProtos::users_ID req; req.set_id(id);
    ::frameworkProtos::users_Message resp;
    ::grpc::Status st = s.pullByID(&c, req, &resp);
    if (st.ok() && name) *name = resp.msg().name();
    return st;
}}
static ::grpc::Status stream(Stub& s, int limit, int* got) {{
    ::grpc::ClientContext c; auth(c);
    ::frameworkProtos::users_Stream req; req.set_limit(limit);
    auto reader = s.streamSrc(&c, req);
    ::frameworkProtos::users_Message m; int n = 0;
    while (reader->Read(&m)) ++n;
    if (got) *got = n;
    return reader->Finish();
}}
"""

_GRPC_SQLITE_CC = _CLIENT_HELPERS + r"""
#include <soci/sqlite3/soci-sqlite3.h>
int main(int, char** argv) {{
    const std::string file = argv[1];
    ::soci::connection_pool pool(2);
    for (std::size_t i = 0; i < 2; ++i) pool.at(i).open(::soci::sqlite3, file);
    {{
        harpia::db::users_dao dao(pool.at(0));
        if (!dao.create_table()) return 1;
        for (int id = 1; id <= 20; ++id) {{
            ::users u; u.set_id_{h}(id); u.set_name("seed" + std::to_string(id));
            if (!dao.create(u)) return 2;
        }}
    }}
    harpia::grpc_transport::GrpcServer server(pool, 300);
    if (!server.ok()) return 3;
    auto ch = server.get()->InProcessChannel(::grpc::ChannelArguments());
    auto stub = ::frameworkProtos::users_Service::NewStub(ch);

    // concurrent reads: 8 clients x 50 calls through a 2-slot pool
    std::atomic<int> bad{{0}};
    std::vector<std::thread> ts;
    for (int t = 0; t < 8; ++t) ts.emplace_back([&, t] {{
        for (int i = 0; i < 50; ++i) {{
            const int id = 1 + (t * 50 + i) % 20;
            std::string name;
            if (!pull(*stub, id, &name).ok() || name != "seed" + std::to_string(id)) ++bad;
            int got = 0;
            if (i % 10 == 0 && (!stream(*stub, 5, &got).ok() || got != 5)) ++bad;
        }}
    }});
    for (auto& t : ts) t.join();
    if (bad.load() != 0) return 4;

    // exhaustion: every slot held -> RESOURCE_EXHAUSTED after ~300 ms
    {{
        std::size_t a = pool.lease(), b = pool.lease();
        const auto t0 = Clock::now();
        ::grpc::Status st = pull(*stub, 1, nullptr);
        const long ms = (long)std::chrono::duration_cast<std::chrono::milliseconds>(
                            Clock::now() - t0).count();
        pool.give_back(a);
        pool.give_back(b);
        if (st.error_code() != ::grpc::StatusCode::RESOURCE_EXHAUSTED) return 5;
        if (st.error_message() != "db pool exhausted") return 6;
        if (ms < 250 || ms > 5000) return 7;
    }}
    // and the server keeps serving afterwards
    std::string name;
    if (!pull(*stub, 7, &name).ok() || name != "seed7") return 8;
    server.shutdown();

    // the pre-pool single-session constructor still works (additive)
    ::soci::session single(::soci::sqlite3, file);
    harpia::grpc_transport::GrpcServer legacy(single);
    auto stub2 = ::frameworkProtos::users_Service::NewStub(
        legacy.get()->InProcessChannel(::grpc::ChannelArguments()));
    if (!pull(*stub2, 3, &name).ok() || name != "seed3") return 9;
    legacy.shutdown();
    return 0;
}}
"""


@pytest.fixture(scope="module")
def sqlite_build(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_db_pool_sqlite"))
    cpp_root = _generate(os.path.join(tmp, "gen"))
    return {"tmp": tmp, "cpp_root": cpp_root, "pb": _pb_archive(cpp_root, tmp)}


def _link(build, name, source, *extra):
    src = os.path.join(build["tmp"], name + ".cc")
    with open(src, "w") as f:
        f.write(source.format(h=HASH))
    binp = os.path.join(build["tmp"], name)
    c = subprocess.run(["g++", "-std=c++17", "-I", build["cpp_root"], *extra,
                        *_pkgconfig("--cflags"), src, build["pb"], "-o", binp,
                        "-lsoci_core", "-lsoci_sqlite3", "-lsoci_postgresql",
                        *_pkgconfig("--libs"), "-lpthread", "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return binp


@_grpc
def test_pooled_grpc_server_concurrency_exhaustion_and_legacy(sqlite_build):
    binp = _link(sqlite_build, "grpc_pool_sqlite", _GRPC_SQLITE_CC)
    r = subprocess.run([binp, os.path.join(sqlite_build["tmp"], "grpc.db")],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, "gRPC pool check #{}\n{}".format(r.returncode, r.stderr)


# ==========================================================================
# live PostgreSQL -- opt-in
# ==========================================================================

_pg = pytest.mark.skipif(
    not PG_DSN
    or any(shutil.which(t) is None for t in ("protoc", "grpc_cpp_plugin", "g++", "ar", "pg_config"))
    or not _have("grpc++"),
    reason="needs HARPIA_PG_DSN + the C++ gRPC toolchain + libpq (opt-in live PG: "
           "Docker/run_pg_tests.sh UnitTests/test_grpc_db_pool.py)")

_GRPC_PG_CC = _CLIENT_HELPERS + r"""
#include <soci/postgresql/soci-postgresql.h>
#include <cstdlib>
int main() {{
    const std::string dsn = std::getenv("HARPIA_PG_DSN");
    {{
        ::soci::session admin(::soci::postgresql, dsn);
        harpia::db::users_dao dao(admin);
        dao.drop_table();
        if (!dao.create_table()) return 1;
    }}

    // 32 clients x 200 mixed CRUDL calls through an 8-slot pool
    const int kClients = 32, kOps = 200;
    {{
        ::soci::connection_pool pool(8);
        for (std::size_t i = 0; i < 8; ++i) pool.at(i).open(::soci::postgresql, dsn);
        harpia::grpc_transport::GrpcServer server(pool);
        if (!server.ok()) return 2;
        auto ch = server.get()->InProcessChannel(::grpc::ChannelArguments());
        auto stub = ::frameworkProtos::users_Service::NewStub(ch);
        std::atomic<int> bad{{0}};
        std::vector<std::thread> ts;
        for (int t = 0; t < kClients; ++t) ts.emplace_back([&, t] {{
            for (int i = 0; i < kOps; ++i) {{
                const int id = 1 + t * 1000 + i;
                const std::string want = "c" + std::to_string(t) + "-" + std::to_string(i);
                auto t0 = Clock::now();
                ::grpc::Status st = push(*stub, id, want);
                if (!st.ok()) {{ report("push", id, st, since(t0)); ++bad; continue; }}
                std::string got;
                t0 = Clock::now();
                st = pull(*stub, id, &got);
                if (!st.ok() || got != want) {{ report("pull", id, st, since(t0)); ++bad; }}
                int n = 0;
                if (i % 25 == 0 && !(st = stream(*stub, 3, &n)).ok()) {{ report("stream", id, st); ++bad; }}
            }}
        }});
        for (auto& t : ts) t.join();
        server.shutdown();
        if (bad.load() != 0) return 3;
    }}
    {{
        ::soci::session check(::soci::postgresql, dsn);
        harpia::db::users_dao dao(check);
        std::vector< ::users> rows;
        if (!dao.list(&rows)) return 4;
        if ((int)rows.size() != kClients * kOps) return 5;          // nothing lost
        for (const auto& r : rows) {{                                // nothing corrupted
            const int id = r.id_{h}() - 1;
            const std::string want = "c" + std::to_string(id / 1000) + "-" + std::to_string(id % 1000);
            if (r.name() != want) return 6;
        }}
    }}

    // rule 3: a pooled connection the server killed is reconnected on borrow
    {{
        ::soci::connection_pool pool(1);
        pool.at(0).open(::soci::postgresql, dsn);
        int pid = 0;
        {{
            std::size_t pos = pool.lease();
            pool.at(pos) << "SELECT pg_backend_pid()", ::soci::into(pid);
            pool.give_back(pos);
        }}
        {{
            ::soci::session admin(::soci::postgresql, dsn);
            int killed = 0;
            admin << "SELECT CASE WHEN pg_terminate_backend(:p) THEN 1 ELSE 0 END",
                ::soci::use(pid), ::soci::into(killed);
            if (killed != 1) return 7;
        }}
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        harpia::grpc_transport::GrpcServer server(pool);
        auto stub = ::frameworkProtos::users_Service::NewStub(
            server.get()->InProcessChannel(::grpc::ChannelArguments()));
        std::string got;
        if (!pull(*stub, 1, &got).ok() || got != "c0-0") return 8;
        server.shutdown();
    }}

    // rule 4 on PostgreSQL: a throw mid-transaction leaves nothing behind
    {{
        ::soci::connection_pool pool(1);
        pool.at(0).open(::soci::postgresql, dsn);
        try {{
            harpia::db::PooledSession l(nullptr, &pool, 1000);
            l.session().begin();
            l.session() << "DELETE FROM " << "user_table";
            throw 7;
        }} catch (int) {{
        }}
        harpia::db::PooledSession l(nullptr, &pool, 1000);
        int n = -1;
        l.session() << "SELECT COUNT(*) FROM user_table", ::soci::into(n);
        if (n != kClients * kOps) return 9;
    }}
    return 0;
}}
"""


@pytest.fixture(scope="module")
def pg_build(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_db_pool_pg"))
    cpp_root = _generate(os.path.join(tmp, "gen"), db_backend="postgresql")
    return {"tmp": tmp, "cpp_root": cpp_root, "pb": _pb_archive(cpp_root, tmp)}


@_pg
def test_pooled_grpc_server_on_live_postgres(pg_build):
    pg_inc = subprocess.run(["pg_config", "--includedir"], capture_output=True,
                            text=True).stdout.strip()
    binp = _link(pg_build, "grpc_pool_pg", _GRPC_PG_CC, "-I", pg_inc)
    r = subprocess.run([binp], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, "PostgreSQL pool check #{}\n{}".format(r.returncode, r.stderr)
