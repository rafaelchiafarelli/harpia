"""Sessions J.8/J.9 (Initiatives/multi-language-targets/thread-1-java-target/
histories/DB-CRUDL-POSTGRES/) -- Postgres driver wiring (J.8) + round-trip
acceptance gate (J.9) for the Java target's DB layer.

Per JavaDatabase/CLAUDE.md, JavaCrudlAdapter's generated DAOs take a plain
java.sql.Connection and were already dialect-neutral through the DbBackend
seam J.5 established (dbBackend is resolved once in main.py and shared by
both the C++ and Java targets) -- so J.8's *entire* wiring is the
org.postgresql:postgresql driver dependency (GradleAdapter/templates/
project.gradle.tmpl); no DAO code changes.

Opt-in, same posture as UnitTests/test_stage8_pg.py (the C++ target's own live-
Postgres test): skipped unless a reachable server is provided via
HARPIA_PG_DSN (a libpq-style DSN, parsed here into a JDBC URL) AND
gradle+JDK are on PATH. A convenient way to run it -- same container as
test_stage8_pg.py's own docstring:

    docker network create harpia-pg-net
    docker run -d --name harpia-pg --network harpia-pg-net \\
        -e POSTGRES_USER=harpia -e POSTGRES_PASSWORD=harpiapass \\
        -e POSTGRES_DB=harpiadb postgres:16-alpine
    HARPIA_PG_DSN="host=harpia-pg dbname=harpiadb user=harpia password=harpiapass" \\
        pytest UnitTests/test_java_db_crudl_postgres.py
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402
from UnitTests.test_java_db_crudl import _USERS_CRUDL_HELPER  # noqa: E402

PG_DSN = os.environ.get("HARPIA_PG_DSN")
_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None

pytestmark = pytest.mark.skipif(
    not PG_DSN or not _HAS_JAVA_TOOLCHAIN,
    reason="needs HARPIA_PG_DSN (opt-in live PG) + gradle/JDK",
)


def _dsn_to_jdbc_url(dsn):
    """A minimal libpq `key=value key=value ...` DSN -> a postgresql JDBC URL."""
    parts = dict(kv.split("=", 1) for kv in dsn.split())
    host = parts.get("host", "localhost")
    port = parts.get("port", "5432")
    dbname = parts["dbname"]
    user = parts["user"]
    password = parts.get("password", "")
    return "jdbc:postgresql://{}:{}/{}?user={}&password={}".format(
        host, port, dbname, user, password)


# -- structural: build.gradle wiring (no live server needed, but this file
# is opt-in as a whole per HARPIA_PG_DSN like its C++ counterpart, so this
# still only runs when PG is configured) ------------------------------------

def test_postgres_driver_is_wired_in(tmp_path):
    out = generate(tmp_path, lang="java", db_backend="postgresql")
    build_gradle = open(os.path.join(out, "java", "build.gradle")).read()
    assert "org.postgresql:postgresql" in build_gradle


# -- integration: a real Postgres container ----------------------------------

def test_users_crudl_full_cycle_against_postgres(tmp_path):
    out = generate(tmp_path / "out", lang="java", db_backend="postgresql")
    java_root = os.path.join(out, "java")
    jdbc_url = _dsn_to_jdbc_url(PG_DSN)

    classpath = build_and_classpath(java_root, {
        "smoke/UsersCrudlHelper.java": _USERS_CRUDL_HELPER,
        "smoke/PgCrudlCycle.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.db.users_dao;\n"
            "import java.sql.Connection;\n"
            "import java.sql.DriverManager;\n"
            "import java.util.ArrayList;\n"
            "import java.util.List;\n"
            "public class PgCrudlCycle {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        Class.forName(\"org.postgresql.Driver\");\n"
            "        try (Connection conn = DriverManager.getConnection(args[0])) {\n"
            "            users_dao dao = new users_dao(conn);\n"
            "            dao.dropTable();\n"
            "            if (!dao.createTable()) System.exit(1);\n"
            "            users a = UsersCrudlHelper.withId(\n"
            "                users.newBuilder().setAddress(\"matrix\").setName(\"neo\"), 1);\n"
            "            if (!dao.create(a)) System.exit(2);\n"
            "            users.Builder got = users.newBuilder();\n"
            "            if (!dao.read(1, got)) System.exit(3);\n"
            "            if (!got.getName().equals(\"neo\") || !got.getAddress().equals(\"matrix\")) System.exit(4);\n"
            "            users b = UsersCrudlHelper.withId(\n"
            "                users.newBuilder().setAddress(\"matrix\").setName(\"trinity\"), 1);\n"
            "            if (!dao.update(b)) System.exit(5);\n"
            "            users.Builder got2 = users.newBuilder();\n"
            "            dao.read(1, got2);\n"
            "            if (!got2.getName().equals(\"trinity\")) System.exit(6);\n"
            "            List<users> all = new ArrayList<>();\n"
            "            dao.list(all);\n"
            "            if (all.isEmpty()) System.exit(7);\n"
            "            if (!dao.remove(1)) System.exit(8);\n"
            "            dao.dropTable();\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.PgCrudlCycle", jdbc_url],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "Postgres CRUDL cycle failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
