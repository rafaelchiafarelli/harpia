"""Stage 12 (REST) test -- the generated bindings serve real HTTP CRUD.

Builds a program that registers the generated routes on a cpp-httplib server
backed by an in-memory SQLite, then drives them with an HTTP client:
POST -> GET/:id -> GET (list) -> PUT -> DELETE -> GET/:id (404).

Needs protoc + g++ + cc + pkg-config (compiles the vendored sqlite; httplib and
the JSON adapter are header-only). Skipped otherwise; runs in the Docker image.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
HTTPLIB = os.path.join(REPO_ROOT, "third_party", "cpp-httplib")
HASH = "734126ee6efdfbd64a1678bf49ee9683"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "cc", "pkg-config")),
    reason="needs protoc + g++ + cc + protobuf (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_rest")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    sqlite_obj = os.path.join(str(out), "sqlite3.o")
    cc = subprocess.run(
        ["cc", "-c", "-I", SQLITE, os.path.join(SQLITE, "sqlite3.c"),
         "-o", sqlite_obj], capture_output=True, text=True, timeout=300)
    assert cc.returncode == 0, cc.stderr
    return {
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "sqlite_obj": sqlite_obj,
        "tmp": str(out),
    }


def test_rest_http_crud(built):
    prog = os.path.join(built["tmp"], "rest.cpp")
    with open(prog, "w") as f:
        f.write(
            '#include "rest/users_{h}_rest.h"\n'
            "#include <thread>\n"
            "int main() {{\n"
            "    ::sqlite3* db = nullptr;\n"
            '    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    ::httplib::Server svr;\n"
            '    harpia::rest::register_users(svr, db, "/api/v1");\n'
            '    std::thread t([&]{{ svr.listen("127.0.0.1", 18099); }});\n'
            "    svr.wait_until_ready();\n"
            '    ::httplib::Client cli("127.0.0.1", 18099);\n'
            "    auto run = [&]() -> int {{\n"
            "        ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
            "        std::string body; ::harpia::json::to_json(a, &body);\n"
            '        auto post = cli.Post("/api/v1/users", body, "application/json");\n'
            "        if (!post || post->status != 201) return 3;\n"
            '        auto get = cli.Get("/api/v1/users/1");\n'
            '        if (!get || get->status != 200 || get->body.find("neo") == std::string::npos) return 4;\n'
            '        auto list = cli.Get("/api/v1/users");\n'
            '        if (!list || list->status != 200 || list->body.find("matrix") == std::string::npos) return 5;\n'
            "        ::users b = a; b.set_name(\"trinity\");\n"
            "        std::string bb; ::harpia::json::to_json(b, &bb);\n"
            '        auto put = cli.Put("/api/v1/users/1", bb, "application/json");\n'
            "        if (!put || put->status != 204) return 6;\n"
            '        auto get2 = cli.Get("/api/v1/users/1");\n'
            '        if (!get2 || get2->body.find("trinity") == std::string::npos) return 7;\n'
            '        auto del = cli.Delete("/api/v1/users/1");\n'
            "        if (!del || del->status != 204) return 8;\n"
            '        auto gone = cli.Get("/api/v1/users/1");\n'
            "        if (!gone || gone->status != 404) return 9;\n"
            "        return 0;\n"
            "    }};\n"
            "    const int code = run();\n"
            "    svr.stop(); t.join();\n"
            "    return code;\n"
            "}}\n".format(h=HASH))

    pb_cc = os.path.join(built["cpp_root"], "protofiles",
                         "users_{}.pb.cc".format(HASH))
    binary = os.path.join(built["tmp"], "rest_app")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", SQLITE,
         "-I", HTTPLIB, *_pkgconfig("--cflags"), prog, pb_cc,
         built["sqlite_obj"], "-o", binary,
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "REST program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "REST CRUD failed at check #{}".format(
        run.returncode)
