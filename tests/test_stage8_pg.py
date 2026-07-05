"""Stage 8 (PostgreSQL backend) -- opt-in live-PG integration test.

Generates the project with the PostgreSQL DB backend (HARPIA_DB_BACKEND=postgresql)
and drives the generated CRUDL DAO against a REAL PostgreSQL server, proving the
same generated code (dialect-free SOCI) runs on Postgres as well as SQLite.

This test is opt-in: it is skipped unless a reachable server is provided via the
``HARPIA_PG_DSN`` environment variable (a libpq/SOCI connection string, e.g.
``host=localhost dbname=harpiadb user=harpia password=...``). A convenient way to
run it:

    docker network create harpia-pg-net
    docker run -d --name harpia-pg --network harpia-pg-net \\
        -e POSTGRES_USER=harpia -e POSTGRES_PASSWORD=harpiapass \\
        -e POSTGRES_DB=harpiadb postgres:16-alpine
    docker run --rm --network harpia-pg-net -v "$PWD":/harpia -w /harpia \\
        -e HOME=/tmp \\
        -e HARPIA_PG_DSN="host=harpia-pg dbname=harpiadb user=harpia password=harpiapass" \\
        harpia-build pytest tests/test_stage8_pg.py
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HASH = "c96f8fd7f45108efee5a8ecb43eab1da"
PG_DSN = os.environ.get("HARPIA_PG_DSN")

pytestmark = pytest.mark.skipif(
    not PG_DSN or any(shutil.which(t) is None
                      for t in ("protoc", "g++", "pkg-config", "pg_config")),
    reason="needs HARPIA_PG_DSN + protoc/g++/pkg-config/libpq (opt-in live PG)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def pg_generated(tmp_path_factory):
    """Run the full pipeline with the PostgreSQL backend into a temp dir."""
    out = str(tmp_path_factory.mktemp("harpia_pg"))
    env = dict(os.environ, HARPIA_DB_BACKEND="postgresql", HARPIA_OUTPUT_DIR=out,
               HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
               HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include")
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DB backend: postgresql" in r.stdout, r.stdout
    return os.path.join(out, "generated", "cpp")


def test_pg_crudl_roundtrip(pg_generated, tmp_path):
    """The generated PG-backend CRUDL round-trips over a live PostgreSQL server:
    scalar (users), map+repeated+embed+enum (data), FK+repeated-FK (top_users).
    Tables are dropped first so the run is idempotent against a persistent DB."""
    cpp_root = pg_generated
    prog = tmp_path / "pg_crudl.cpp"
    prog.write_text(
        '#include <soci/soci.h>\n'
        '#include <soci/postgresql/soci-postgresql.h>\n'
        '#include <cstdlib>\n#include <string>\n#include <vector>\n'
        '#include "db/users_{h}_crudl.h"\n'
        '#include "db/data_{h}_crudl.h"\n'
        '#include "db/top_users_{h}_crudl.h"\n'
        '#include "db/vip_users_{h}_crudl.h"\n'
        "int main() {{\n"
        '    ::soci::session sql(::soci::postgresql, std::getenv("HARPIA_PG_DSN"));\n'
        "    {{ harpia::db::users_dao dao(sql); dao.drop_table();\n"
        "      if (!dao.create_table()) return 1;\n"
        "      ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
        "      if (!dao.create(a)) return 2;\n"
        "      ::users got; if (!dao.read(1, &got)) return 3;\n"
        '      if (got.name() != "neo" || got.address() != "matrix") return 4;\n'
        "      ::users b = a; b.set_name(\"trinity\"); if (!dao.update(b)) return 5;\n"
        "      ::users g2; dao.read(1, &g2); if (g2.name() != \"trinity\") return 6;\n"
        "      ::users c; c.set_id_{h}(2); c.set_name(\"m\"); dao.create(c);\n"
        "      std::vector<::users> all; if (!dao.list(&all) || all.size() != 2) return 7;\n"
        "      if (!dao.remove(1)) return 8; ::users gone; if (dao.read(1, &gone)) return 9;\n"
        "      dao.drop_table(); }}\n"
        "    {{ harpia::db::data_dao dao(sql); dao.drop_table();\n"
        "      if (!dao.create_table()) return 20;\n"
        "      ::data d; d.set_id_{h}(1); d.set_i(7);\n"
        "      d.mutable_val()->set_var(3); d.set_car(static_cast<::grower>(2));\n"
        '      (*d.mutable_val()->mutable_a())["k1"] = "v1";\n'
        "      d.add_tags(11); d.add_tags(22); d.mutable_val()->add_scores(100);\n"
        "      if (!dao.create(d)) return 21; ::data got; if (!dao.read(1, &got)) return 22;\n"
        "      if (got.i() != 7 || got.val().var() != 3) return 23;\n"
        "      if (static_cast<int>(got.car()) != 2) return 24;\n"
        '      if (got.val().a().at("k1") != "v1") return 25;\n'
        "      if (got.tags_size() != 2 || got.val().scores_size() != 1) return 26; }}\n"
        "    {{ harpia::db::vip_users_dao v(sql); harpia::db::top_users_dao dao(sql);\n"
        "      dao.drop_table(); v.drop_table();\n"
        "      if (!v.create_table() || !dao.create_table()) return 40;\n"
        "      ::top_users t; t.set_id_{h}(1); t.set_name(\"boss\");\n"
        "      t.mutable_myusers()->set_id_{h}(10); t.mutable_myusers()->set_family(\"smith\");\n"
        "      auto* m1 = t.add_members(); m1->set_id_{h}(20); m1->set_family(\"a\");\n"
        "      auto* m2 = t.add_members(); m2->set_id_{h}(21); m2->set_family(\"b\");\n"
        "      if (!dao.create(t)) return 42; ::top_users got; if (!dao.read(1, &got)) return 43;\n"
        '      if (got.name() != "boss" || got.myusers().family() != "smith") return 44;\n'
        "      if (got.members_size() != 2) return 45;\n"
        '      if (got.members(0).family() != "a" || got.members(1).family() != "b") return 46; }}\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pg_inc = subprocess.run(["pg_config", "--includedir"],
                            capture_output=True, text=True).stdout.strip()
    objs = [os.path.join(cpp_root, "protofiles", "{}_{}.pb.cc".format(m, HASH))
            for m in ("users", "data", "prince", "grower", "top_users",
                      "vip_users")]
    binary = str(tmp_path / "pg_crudl")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, "-I", pg_inc,
         *_pkgconfig("--cflags"), str(prog), *objs, "-o", binary,
         "-lsoci_core", "-lsoci_postgresql",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "PG CRUDL program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "PG CRUDL round-trip failed at check #{}\n{}".format(
        run.returncode, run.stdout + run.stderr)
