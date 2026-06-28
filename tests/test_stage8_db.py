"""Stage 8 (database) test -- the generated SQL schema is valid SQLite.

Runs the generator, then compiles a tiny checker against the vendored SQLite
amalgamation and executes every generated CREATE TABLE in an in-memory database,
asserting SQLite accepts it.

Needs only g++ (it compiles the vendored sqlite3.c), so it is skipped on a host
without a compiler; runs in the Docker image.
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

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None,
    reason="needs g++ to compile the vendored sqlite (harpia Docker image)",
)

_CHECKER_SRC = r"""
#include "sqlite3.h"
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
int main(int argc, char** argv) {
    if (argc < 2) return 2;
    std::ifstream f(argv[1]);
    std::stringstream ss; ss << f.rdbuf();
    const std::string sql = ss.str();
    sqlite3* db = nullptr;
    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 3;
    char* err = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err);
    if (rc != SQLITE_OK) {
        std::fprintf(stderr, "%s\n", err ? err : "?");
        sqlite3_free(err);
        sqlite3_close(db);
        return 1;
    }
    sqlite3_close(db);
    return 0;
}
"""


@pytest.fixture(scope="module")
def schema(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_db")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    # build the sqlite checker once (compiling sqlite3.c is the slow part)
    src = os.path.join(str(out), "checker.cpp")
    with open(src, "w") as f:
        f.write(_CHECKER_SRC)
    # sqlite3.c is C -- compile it with the C compiler (g++ would reject its
    # implicit void* conversions), then link with the C++ checker.
    sqlite_obj = os.path.join(str(out), "sqlite3.o")
    cc = subprocess.run(
        ["cc", "-c", "-I", SQLITE, os.path.join(SQLITE, "sqlite3.c"),
         "-o", sqlite_obj],
        capture_output=True, text=True, timeout=300,
    )
    assert cc.returncode == 0, "sqlite3.c failed to compile:\n" + cc.stderr

    checker = os.path.join(str(out), "checker")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", SQLITE, src, sqlite_obj, "-o", checker,
         "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120,
    )
    assert c.returncode == 0, "sqlite checker failed to build:\n" + c.stderr
    return {
        "db_dir": os.path.join(str(out), "build", "database"),
        "checker": checker,
    }


def _create_table_files(db_dir):
    files = []
    for path in sorted(glob.glob(os.path.join(db_dir, "*_table.sql"))):
        with open(path) as f:
            if "CREATE TABLE" in f.read():
                files.append(path)
    return files


def test_generated_schema_is_valid_sqlite(schema):
    files = _create_table_files(schema["db_dir"])
    assert len(files) >= 4, "expected at least 4 tables, got {}".format(len(files))
    for path in files:
        r = subprocess.run([schema["checker"], path],
                           capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, "invalid schema {}:\n{}".format(
            os.path.basename(path), r.stderr)
