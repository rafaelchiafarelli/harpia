"""Stage 8 (database) tests.

  - the generated SQL schema executes in SQLite (needs g++ to compile the
    vendored sqlite3.c), and
  - the generated CRUDL DAO does a real round-trip against an in-memory database
    (additionally needs protoc for the message C++).

Skipped when the toolchain is absent so the host suite stays green; runs fully in
the Docker image.
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
SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
HASH = "734126ee6efdfbd64a1678bf49ee9683"

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None or shutil.which("cc") is None,
    reason="needs a C/C++ compiler for the vendored sqlite (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def sqlite_obj(tmp_path_factory):
    """Compile the vendored sqlite3.c once (it is C; g++ would reject it)."""
    out = tmp_path_factory.mktemp("sqlite_obj")
    obj = os.path.join(str(out), "sqlite3.o")
    c = subprocess.run(
        ["cc", "-c", "-I", SQLITE, os.path.join(SQLITE, "sqlite3.c"), "-o", obj],
        capture_output=True, text=True, timeout=300,
    )
    assert c.returncode == 0, "sqlite3.c failed to compile:\n" + c.stderr
    return obj


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_db")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build")


def test_generated_schema_is_valid_sqlite(generated, sqlite_obj, tmp_path):
    checker_src = tmp_path / "checker.cpp"
    checker_src.write_text(
        '#include "sqlite3.h"\n#include <fstream>\n#include <sstream>\n'
        '#include <string>\nint main(int c,char**v){if(c<2)return 2;'
        'std::ifstream f(v[1]);std::stringstream s;s<<f.rdbuf();'
        'sqlite3*db=nullptr;if(sqlite3_open(":memory:",&db))return 3;'
        'char*e=nullptr;if(sqlite3_exec(db,s.str().c_str(),0,0,&e)){'
        'fprintf(stderr,"%s\\n",e);return 1;}return 0;}\n')
    checker = str(tmp_path / "checker")
    c = subprocess.run(["g++", "-std=c++17", "-I", SQLITE, str(checker_src),
                        sqlite_obj, "-o", checker, "-lpthread", "-ldl"],
                       capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, c.stderr

    db_dir = os.path.join(generated, "database")
    files = [p for p in sorted(glob.glob(os.path.join(db_dir, "*_table.sql")))
             if "CREATE TABLE" in open(p).read()]
    assert len(files) >= 4
    for path in files:
        r = subprocess.run([checker, path], capture_output=True, text=True,
                           timeout=15)
        assert r.returncode == 0, "invalid schema {}:\n{}".format(
            os.path.basename(path), r.stderr)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="CRUDL round-trip needs protoc + protobuf")
def test_crudl_roundtrip(generated, sqlite_obj, tmp_path):
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "crudl.cpp"
    prog.write_text(
        '#include "db/users_{h}_crudl.h"\n'
        "#include <vector>\n"
        "int main() {{\n"
        "    ::sqlite3* db = nullptr;\n"
        '    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;\n'
        "    harpia::db::users_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
        "    if (!dao.create(a)) return 3;\n"
        "    ::users got;\n"
        "    if (!dao.read(1, &got)) return 4;\n"
        '    if (got.name() != "neo" || got.address() != "matrix") return 5;\n'
        "    ::users b = a; b.set_name(\"trinity\");\n"
        "    if (!dao.update(b)) return 6;\n"
        "    ::users got2; dao.read(1, &got2);\n"
        '    if (got2.name() != "trinity") return 7;\n'
        "    ::users a2; a2.set_id_{h}(2); a2.set_name(\"morpheus\");\n"
        "    if (!dao.create(a2)) return 8;\n"
        "    std::vector<::users> all;\n"
        "    if (!dao.list(&all) || all.size() != 2) return 9;\n"
        "    if (!dao.remove(1)) return 10;\n"
        "    ::users gone;\n"
        "    if (dao.read(1, &gone)) return 11;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "crudl")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, "-I", SQLITE,
         *_pkgconfig("--cflags"), str(prog), pb_cc, sqlite_obj, "-o", binary,
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "CRUDL program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "CRUDL round-trip failed at check #{}".format(
        run.returncode)
