"""Stage 11 (SOAP) test -- the generated endpoint serves real SOAP over HTTP.

Starts an httplib server with the generated SOAP endpoint (backed by in-memory
SQLite), then POSTs SOAP envelopes: a `set` (create) then a `get` (read), plus a
not-found that returns a SOAP Fault.

Needs protoc + g++ + cc + pkg-config (compiles the vendored sqlite; httplib,
tinyxml2 and the XML adapter are header-only/linked). Skipped otherwise.
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
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
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
    out = tmp_path_factory.mktemp("harpia_soap")
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


def test_soap_http_roundtrip(built):
    env = '<soap:Envelope xmlns:soap=\\"http://schemas.xmlsoap.org/soap/envelope/\\">'
    prog = os.path.join(built["tmp"], "soap.cpp")
    with open(prog, "w") as f:
        f.write(
            '#include "soap/users_{h}_soap.h"\n'
            "#include <thread>\n"
            "int main() {{\n"
            "    ::sqlite3* db = nullptr;\n"
            '    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    ::httplib::Server svr;\n"
            '    harpia::soap::register_users_soap(svr, db, "/soap");\n'
            '    std::thread t([&]{{ svr.listen("127.0.0.1", 18077); }});\n'
            "    svr.wait_until_ready();\n"
            '    ::httplib::Client cli("127.0.0.1", 18077);\n'
            "    auto run = [&]() -> int {{\n"
            "        ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
            "        const std::string mx = ::harpia::xml::to_xml(a);\n"
            '        const std::string setBody = "{env}<soap:Body><set>" + mx + "</set></soap:Body></soap:Envelope>";\n'
            '        auto s = cli.Post("/soap/users", setBody, "text/xml");\n'
            '        if (!s || s->status != 200 || s->body.find("<ok>true</ok>") == std::string::npos) return 3;\n'
            '        const std::string getBody = "{env}<soap:Body><get><id>1</id></get></soap:Body></soap:Envelope>";\n'
            '        auto g = cli.Post("/soap/users", getBody, "text/xml");\n'
            '        if (!g || g->status != 200) return 4;\n'
            '        if (g->body.find("getResponse") == std::string::npos) return 5;\n'
            '        if (g->body.find("neo") == std::string::npos) return 6;\n'
            '        const std::string missBody = "{env}<soap:Body><get><id>999</id></get></soap:Body></soap:Envelope>";\n'
            '        auto nf = cli.Post("/soap/users", missBody, "text/xml");\n'
            '        if (!nf || nf->body.find("Fault") == std::string::npos) return 7;\n'
            "        return 0;\n"
            "    }};\n"
            "    const int code = run();\n"
            "    svr.stop(); t.join();\n"
            "    return code;\n"
            "}}\n".format(h=HASH, env=env))

    pb_cc = os.path.join(built["cpp_root"], "protofiles",
                         "users_{}.pb.cc".format(HASH))
    tinyxml = os.path.join(TINYXML2, "tinyxml2.cpp")
    binary = os.path.join(built["tmp"], "soap_app")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", SQLITE,
         "-I", HTTPLIB, "-I", TINYXML2, *_pkgconfig("--cflags"), prog, pb_cc,
         tinyxml, built["sqlite_obj"], "-o", binary,
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "SOAP program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "SOAP round-trip failed at check #{}".format(
        run.returncode)
