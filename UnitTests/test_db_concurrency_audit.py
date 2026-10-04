"""multi-system-reference / db-concurrency task 1b -- SQLite under a connection
pool, and a thread-safety audit of the other state a generated server shares
across its handler threads.

Part 1 (SQLite under a pool), `Database/runtime/harpia_db_pool.h`:
  * a pool of SQLite `:memory:` connections is refused (each would be its own
    empty database): `refuse_sqlite_memory_pool()` throws
    std::invalid_argument, and the pooled `GrpcServer` constructors call it;
    the single-session constructor still takes `:memory:`.
  * `open_sqlite_pool()` opens every slot on a FILE with WAL + busy_timeout,
    so concurrent writers wait instead of failing "database is locked".

Part 2 (audit). What a gRPC handler touches besides its pooled session:
  * AuditSink -- `NoOpAuditSink` is stateless and `default_audit_sink()` is a
    function-local static (thread-safe init): safe. A deployment's own sink
    must be thread-safe; documented in Compliance/CLAUDE.md.
  * KeyProvider -- RACY before this task: `default_key_provider()` is ONE
    process-wide InMemoryKeyProvider every phi DAO shares, with unguarded
    std::map/std::set members, and `detail::random_bytes` shared one
    `static std::random_device`. Fixed with a per-instance mutex in every
    provider (+ MockKms) and a thread_local random_device.
  * Sessions -- key/TTL are const statics; `RevocationList` is
    mutex-guarded; jti uses a local random_device: safe.
  * RBAC -- `role_map()` is a const function-local static, read-only after
    init: safe.
  * Event channels -- already TSan-covered by test_events_callbacks.py.

Proof: the key-provider TSan unit below, and a ThreadSanitizer build of a
hardened, pooled gRPC server under concurrent load that exercises the
session-token verification, the RBAC gate (allow + deny) and the phi DAO
path (encrypt/decrypt + audit) on a file-SQLite pool.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
POOL_DIR = os.path.join(REPO_ROOT, "Database", "runtime")
CRYPTO_DIR = os.path.join(REPO_ROOT, "Crypto", "runtime")
COMPLIANCE_DIR = os.path.join(REPO_ROOT, "Compliance", "runtime")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests.test_grpc_db_pool import (  # noqa: E402
    _have, _have_soci_sqlite, _pb_archive, _pkgconfig)

# ignore_noninstrumented_modules: gRPC/abseil/SOCI/SQLite come from apt
# without TSan instrumentation, so TSan can't see their internal locking and
# flags their own memmoves (seen: absl GraphCycles inside gRPC's timer
# thread). This option drops reports for accesses made BY uninstrumented
# libraries only; every access in the instrumented test program -- the
# generated handlers, DAOs, RBAC/session/key-provider/audit code -- is still
# checked. (Suppression patterns would be wrong here: they match ANY frame,
# and every handler runs under gRPC frames.)
_TSAN_OPTS = ("halt_on_error=1 exitcode=66 second_deadlock_stack=1 "
              "ignore_noninstrumented_modules=1")


_TSAN_FLAGS = ["-fsanitize=thread", "-g", "-O1", "-fno-pie", "-no-pie"]
_TSAN_MAPPING = "ThreadSanitizer: unexpected memory mapping"
# Printed by every TSan test program as the first statement of main(), so a
# crash *before* it is known to be TSan's own startup, not test code.
_MAIN_MARK = "HARPIA_TSAN_MAIN"
_MARK_STMT = 'std::fputs("HARPIA_TSAN_MAIN\\n", stderr); std::fflush(stderr);'



def _run_tsan(cmd, timeout, env=None, attempts=25):
    """Run a TSan binary, retrying ONLY TSan's own startup abort.

    On kernels with high mmap ASLR entropy (this WSL2 host; vm.mmap_rnd_bits
    can't be lowered from inside the container, and Docker's seccomp profile
    blocks the personality(ADDR_NO_RANDOMIZE) re-exec newer TSan uses), TSan
    aborts or segfaults *before main()* whenever a library lands outside its
    shadow layout ("unexpected memory mapping") -- roughly half the starts here,
    non-PIE. Only a run that never reached main() (no _MAIN_MARK on stderr) is
    retried, so this cannot mask a race or a crash in test code: those happen
    after the mark and are returned on the first occurrence. If TSan never
    starts, skip.
    """
    env = {**(env or os.environ), "TSAN_OPTIONS": _TSAN_OPTS}
    for _ in range(attempts):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        if _MAIN_MARK in r.stderr:
            return r
    pytest.skip("ThreadSanitizer never got past startup in {} attempts "
                "(kernel mmap layout)".format(attempts))


# ==========================================================================
# runtime unit -- g++ + SOCI sqlite3
# ==========================================================================

_unit = pytest.mark.skipif(
    shutil.which("g++") is None or not _have_soci_sqlite(),
    reason="needs g++ + SOCI sqlite3 backend (harpia Docker image)")

_SQLITE_POOL_CC = r"""
#include "harpia_db_pool.h"
#include <soci/sqlite3/soci-sqlite3.h>
#include <stdexcept>
#include <string>
using namespace harpia::db;

int main(int, char** argv) {
    const std::string file = argv[1];
    // path classification
    if (!is_sqlite_memory_path(":memory:") || !is_sqlite_memory_path("") ||
        !is_sqlite_memory_path("file::memory:?cache=shared") ||
        !is_sqlite_memory_path("file:x?mode=memory") || is_sqlite_memory_path(file))
        return 1;
    // open_sqlite_pool refuses an in-memory path up front
    {
        ::soci::connection_pool pool(2);
        try { open_sqlite_pool(pool, 2, ::soci::sqlite3, ":memory:"); return 2; }
        catch (const std::invalid_argument&) {}
    }
    // a pool somebody opened on :memory: is detected and refused
    {
        ::soci::connection_pool pool(2);
        for (std::size_t i = 0; i < 2; ++i) pool.at(i).open(::soci::sqlite3, ":memory:");
        try { refuse_sqlite_memory_pool(pool, 500); return 3; }
        catch (const std::invalid_argument& e) {
            if (std::string(e.what()).find(":memory:") == std::string::npos) return 4;
        }
    }
    // a file pool: every slot WAL + busy_timeout, and not refused
    {
        ::soci::connection_pool pool(3);
        open_sqlite_pool(pool, 3, ::soci::sqlite3, file, 1234);
        refuse_sqlite_memory_pool(pool, 500);
        for (std::size_t i = 0; i < 3; ++i) {
            std::string mode; int busy = 0;
            pool.at(i) << "PRAGMA journal_mode", ::soci::into(mode);
            pool.at(i) << "PRAGMA busy_timeout", ::soci::into(busy);
            if (mode != "wal") return 5;
            if (busy != 1234) return 6;
            if (is_sqlite_memory(pool.at(i))) return 7;
        }
    }
    return 0;
}
"""


@_unit
def test_sqlite_pool_helpers(tmp_path):
    src = tmp_path / "sqlite_pool.cc"
    src.write_text(_SQLITE_POOL_CC, encoding="utf-8")
    binp = tmp_path / "sqlite_pool"
    c = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", POOL_DIR,
                        str(src), "-o", str(binp), "-lsoci_core", "-lsoci_sqlite3",
                        "-lpthread", "-ldl"], capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    r = subprocess.run([str(binp), str(tmp_path / "pool.db")], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, "sqlite pool check #{}\n{}".format(r.returncode, r.stderr)


_KEYS_TSAN_CC = r"""
#include "harpia_encrypted_column.h"
#include "harpia_key_provider_local.h"
#include <cstdio>
#include "harpia_key_provider_kms.h"
#include <atomic>
#include <string>
#include <thread>
#include <vector>
using namespace harpia::crypto;

// Every provider, hammered from 8 threads at once: encrypt/decrypt round
// trips, plus rotation and shredding interleaved -- what a pooled server's
// phi DAOs do to the one shared default_key_provider().
static int hammer(KeyProvider& kp) {
    std::atomic<int> bad{0};
    std::vector<std::thread> ts;
    for (int t = 0; t < 8; ++t) ts.emplace_back([&, t] {
        for (int i = 0; i < 200; ++i) {
            const std::string v = "v" + std::to_string(t) + "-" + std::to_string(i);
            if (decrypt_field(kp, encrypt_field(kp, v)) != v) ++bad;
            if (i % 50 == 0 && t == 0) kp.rotate();
            if (i % 40 == 0) {
                Dek d = kp.generate_dek();
                WrappedDek w = kp.wrap_dek(d);
                kp.shred_dek(w);
                if (kp.unwrap_dek(w).has_value()) ++bad;
            }
            (void)kp.active_kek_version();
        }
    });
    for (auto& t : ts) t.join();
    return bad.load();
}

int main(int, char** argv) {
    MARK
    if (hammer(default_key_provider()) != 0) return 1;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = argv[1];
    LocalKeyProvider local(cfg);
    if (hammer(local) != 0) return 2;
    MockKms kms;
    KmsKeyProvider remote(kms);
    if (hammer(remote) != 0) return 3;
    return 0;
}
"""


@_unit
def test_key_providers_are_thread_safe_under_tsan(tmp_path):
    """Fails (TSan data race, exit 66) against the pre-1b providers: the
    shared default_key_provider()'s map/set and the static random_device."""
    src = tmp_path / "keys_tsan.cc"
    src.write_text(_KEYS_TSAN_CC.replace("MARK", _MARK_STMT), encoding="utf-8")
    binp = tmp_path / "keys_tsan"
    c = subprocess.run(["g++", "-std=c++17", *_TSAN_FLAGS,
                        "-I", CRYPTO_DIR, "-I", COMPLIANCE_DIR, str(src), "-o", str(binp),
                        "-lpthread"], capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    r = _run_tsan([str(binp), str(tmp_path / "keks.store")], timeout=300)
    assert r.returncode == 0, "key-provider TSan check #{}\n{}".format(
        r.returncode, r.stderr[-6000:])


from UnitTests.test_events_callbacks import _PROLOGUE, _RUNTIME_INC  # noqa: E402


@_unit
def test_event_channel_churn_is_race_free_under_tsan(tmp_path):
    """The audit's event-channel item. Until 1b nothing in the suite actually
    ran the event runtime under TSan (test_events_callbacks.py's churn test
    only checks it doesn't crash), so this is that check: publish from one
    thread while another subscribes/unsubscribes, with detached dispatch."""
    body = r'''
    EventChannel<int> c(CacheMode::Cached);
    std::atomic<int> delivered{0};
    auto keep = c.subscribe([&](const int&){ ++delivered; });
    (void)keep;
    std::atomic<bool> stop{false};
    std::thread churn([&]{
        while (!stop.load()) {
            auto id = c.subscribe([](const int&){});
            c.unsubscribe(id);
            (void)c.has_last(); (void)c.subscriber_count();
        }
    });
    const int N = 200;
    for (int i = 0; i < N; ++i) c.publish(i);
    stop = true;
    churn.join();
    // every publish reaches `keep` (it was subscribed throughout); let the
    // detached dispatch threads finish before the channel goes away
    if (!wait_for([&]{ return delivered.load() >= N; })) return 1;
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
'''
    src = tmp_path / "ec_tsan.cpp"
    src.write_text("#include <cstdio>\n" + _PROLOGUE + "\nint main() {\n    " + _MARK_STMT + "\n" + body + "\n    return 0;\n}\n",
                   encoding="utf-8")
    binp = tmp_path / "ec_tsan"
    inc = []
    for d in _RUNTIME_INC:
        inc += ["-I", d]
    c = subprocess.run(["g++", "-std=c++17", "-pthread", *_TSAN_FLAGS, *inc, str(src),
                        "-o", str(binp)], capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    r = _run_tsan([str(binp)], timeout=120)
    assert r.returncode == 0, "event-channel TSan check #{}\n{}".format(
        r.returncode, r.stderr[-6000:])


# ==========================================================================
# gRPC -- hardened generated GrpcServer over a file-SQLite pool
# ==========================================================================

_grpc = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "grpc_cpp_plugin", "g++", "ar"))
    or not _have("grpc++") or not _have_soci_sqlite(),
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ + SOCI sqlite3 (harpia Docker image)")

_HARDENED_LOAD_CC = r"""
#include "grpc/grpc_server_bringup.h"
#include "db/users_{h}_crudl.h"
#include "db/patient_vitals_{h}_crudl.h"
#include <soci/sqlite3/soci-sqlite3.h>
#include <grpcpp/grpcpp.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using UsersStub = ::frameworkProtos::users_Service::Stub;
using VitalsStub = ::frameworkProtos::patient_vitals_Service::Stub;

static std::mutex report_mu;
static int reported = 0;
static void report(const char* what, const ::grpc::Status& st) {{
    std::lock_guard<std::mutex> lk(report_mu);
    if (reported++ < 8)
        std::cerr << what << " code=" << st.error_code() << " msg=" << st.error_message() << "\n";
}}
static void ctx(::grpc::ClientContext& c, const std::string& token) {{
    c.AddMetadata("authorization", "Bearer " + token);
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(60));
}}

int main(int, char** argv) {{
    MARK
    const std::string file = argv[1];

    // :memory: behind a pooled GrpcServer is refused, not silently wrong
    {{
        ::soci::connection_pool mem(2);
        for (std::size_t i = 0; i < 2; ++i) mem.at(i).open(::soci::sqlite3, ":memory:");
        try {{ harpia::grpc_transport::GrpcServer bad(mem); return 1; }}
        catch (const std::invalid_argument&) {{}}
        // ...while the single-session constructor still takes it
        ::soci::session single(::soci::sqlite3, ":memory:");
        harpia::grpc_transport::GrpcServer ok(single);
        if (!ok.ok()) return 2;
        ok.shutdown();
    }}

    const int kPool = 4, kWriters = 8, kOps = 100;
    ::soci::connection_pool pool(kPool);
    harpia::db::open_sqlite_pool(pool, kPool, ::soci::sqlite3, file);
    {{
        harpia::db::PooledSession l(nullptr, &pool, 2000);
        if (!harpia::db::users_dao(l.session()).create_table()) return 3;
        if (!harpia::db::patient_vitals_dao(l.session()).create_table()) return 4;
    }}
    harpia::grpc_transport::GrpcServer server(pool, 10000);
    if (!server.ok()) return 5;
    auto ch = server.get()->InProcessChannel(::grpc::ChannelArguments());
    auto users = ::frameworkProtos::users_Service::NewStub(ch);
    auto vitals = ::frameworkProtos::patient_vitals_Service::NewStub(ch);

    const std::string admin = harpia::session::issue("alice", "admin");
    const std::string guest = harpia::session::issue("gus", "guest");
    if (admin.empty() || guest.empty()) return 6;

    std::atomic<int> bad{{0}};
#ifdef HARPIA_TSAN_CANARY
    static int canary = 0;   // deliberately unsynchronized: TSan must flag it
#endif
    std::vector<std::thread> ts;
    for (int t = 0; t < kWriters; ++t) ts.emplace_back([&, t] {{
        for (int i = 0; i < kOps; ++i) {{
#ifdef HARPIA_TSAN_CANARY
            ++canary;
#endif
            const int id = 1 + t * 1000 + i;
            {{   // users: create through RBAC(admin via token) + pool
                ::grpc::ClientContext c; ctx(c, admin);
                ::frameworkProtos::users_Message req;
                req.mutable_msg()->set_id_{h}(id);
                req.mutable_msg()->set_name("n" + std::to_string(id));
                ::frameworkProtos::errorCode ec;
                ::grpc::Status st = users->push(&c, req, &ec);
                if (!st.ok() || ec.code() != 0) {{
                    report("users.push", st.ok() ? ::grpc::Status(::grpc::StatusCode::INTERNAL, ec.message()) : st);
                    ++bad;
                }}
            }}
            if (i % 4 == 0) {{   // phi path: encrypt + audit on create, decrypt on read
                ::grpc::ClientContext c; ctx(c, admin);
                ::frameworkProtos::patient_vitals_Message req;
                req.mutable_msg()->set_id_{h}(id);
                req.mutable_msg()->set_patient_id("p" + std::to_string(id));
                req.mutable_msg()->set_heart_rate(60.0f + (i % 40));
                ::frameworkProtos::errorCode ec;
                ::grpc::Status st = vitals->push(&c, req, &ec);
                if (!st.ok() || ec.code() != 0) {{ report("vitals.push", st); ++bad; continue; }}
                ::grpc::ClientContext c2; ctx(c2, guest);   // guest may read
                ::frameworkProtos::patient_vitals_ID rid; rid.set_id(id);
                ::frameworkProtos::patient_vitals_Message got;
                st = vitals->pullByID(&c2, rid, &got);
                if (!st.ok() || got.msg().patient_id() != "p" + std::to_string(id)) {{
                    report("vitals.pullByID", st); ++bad;
                }}
            }}
            if (i % 10 == 0) {{   // RBAC deny path: guest may not create
                ::grpc::ClientContext c; ctx(c, guest);
                ::frameworkProtos::users_Message req;
                req.mutable_msg()->set_id_{h}(900000 + id);
                ::frameworkProtos::errorCode ec;
                if (users->push(&c, req, &ec).error_code() != ::grpc::StatusCode::PERMISSION_DENIED) ++bad;
            }}
            if (i % 10 == 5) {{   // session-denied path: a forged token
                ::grpc::ClientContext c; ctx(c, admin + "x");
                ::frameworkProtos::users_ID rid; rid.set_id(id);
                ::frameworkProtos::users_Message got;
                if (users->pullByID(&c, rid, &got).error_code() != ::grpc::StatusCode::UNAUTHENTICATED) ++bad;
            }}
            if (i % 25 == 0) {{   // stream through the pool
                ::grpc::ClientContext c; ctx(c, guest);
                ::frameworkProtos::users_Stream req; req.set_limit(5);
                auto reader = users->streamSrc(&c, req);
                ::frameworkProtos::users_Message m;
                while (reader->Read(&m)) {{}}
                if (!reader->Finish().ok()) ++bad;
            }}
        }}
    }});
    for (auto& t : ts) t.join();
    server.shutdown();
    if (bad.load() != 0) return 7;

    // exact counts: nothing lost to "database is locked"
    harpia::db::PooledSession l(nullptr, &pool, 2000);
    int n_users = -1, n_vitals = -1;
    l.session() << "SELECT COUNT(*) FROM user_table", ::soci::into(n_users);
    l.session() << "SELECT COUNT(*) FROM patient_vitals_table", ::soci::into(n_vitals);
    if (n_users != kWriters * kOps) {{ std::cerr << "users=" << n_users << "\n"; return 8; }}
    if (n_vitals != kWriters * kOps / 4) {{ std::cerr << "vitals=" << n_vitals << "\n"; return 9; }}
    return 0;
}}
"""


@pytest.fixture(scope="module")
def hardened_build(tmp_path_factory):
    """main.py under the repo's own (hardened: class_c / cloud_connected)
    profile, so the generated gRPC services carry the RBAC + session gate."""
    tmp = str(tmp_path_factory.mktemp("harpia_db_concurrency_audit"))
    out = os.path.join(tmp, "gen")
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out,
               HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
               HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include")
    for k in ("HARPIA_COMPLIANCE_CONFIG", "HARPIA_DB_BACKEND", "HARPIA_GEN_LANG"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    cpp_root = os.path.join(out, "generated", "cpp")
    assert "kHardeningRequired = true" in open(
        os.path.join(cpp_root, "grpc", "grpc_server_bringup.h")).read()
    rbac_map = os.path.join(tmp, "rbac.map")
    with open(rbac_map, "w") as f:
        f.write("alice admin\ngus guest\n")
    return {"tmp": tmp, "cpp_root": cpp_root, "pb": _pb_archive(cpp_root, tmp),
            "env": {**os.environ, "HARPIA_RBAC_MAP": rbac_map,
                    "HARPIA_SESSION_KEY": "db-concurrency-1b-test-key"}}


def _build_load(build, name, *flags):
    src = os.path.join(build["tmp"], name + ".cc")
    with open(src, "w") as f:
        f.write(_HARDENED_LOAD_CC.format(h=HASH).replace("MARK", _MARK_STMT))
    binp = os.path.join(build["tmp"], name)
    c = subprocess.run(["g++", "-std=c++17", *flags, "-I", build["cpp_root"],
                        *_pkgconfig("--cflags"), src, build["pb"], "-o", binp,
                        "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
                        "-lpthread", "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return binp


@_grpc
def test_pooled_file_sqlite_concurrent_writers(hardened_build):
    """8 writers x 100 creates through a 4-slot file-SQLite pool on the
    hardened server: no "database is locked", exact final counts; plus the
    :memory: refusal and the single-session constructor still accepting it."""
    binp = _build_load(hardened_build, "load_plain", "-O1")
    db = os.path.join(hardened_build["tmp"], "plain.db")
    r = subprocess.run([binp, db], capture_output=True, text=True, timeout=300,
                       env=hardened_build["env"])
    assert r.returncode == 0, "hardened pooled load check #{}\n{}".format(
        r.returncode, r.stderr[-4000:])


@_grpc
def test_pooled_hardened_server_is_race_free_under_tsan(hardened_build):
    """The same load under ThreadSanitizer: handlers, the RBAC gate, session
    verification and the phi DAO path (key provider + audit) race-free."""
    binp = _build_load(hardened_build, "load_tsan", *_TSAN_FLAGS)
    db = os.path.join(hardened_build["tmp"], "tsan.db")
    if os.path.exists(db):
        os.remove(db)
    r = _run_tsan([binp, db], timeout=900, env=hardened_build["env"])
    assert r.returncode == 0, "TSan load check #{}\n{}".format(r.returncode, r.stderr[-8000:])

    # Negative control: the same binary plus one deliberately racy counter in
    # the client threads must be reported, proving TSan is live in this build
    # and ignore_noninstrumented_modules doesn't blind the instrumented code.
    canary = _build_load(hardened_build, "load_tsan_canary", *_TSAN_FLAGS,
                         "-DHARPIA_TSAN_CANARY")
    os.remove(db)
    r = _run_tsan([canary, db], timeout=900, env=hardened_build["env"])
    assert r.returncode == 66 and "data race" in r.stderr, (
        "TSan did not flag the deliberate race (rc={})".format(r.returncode))
