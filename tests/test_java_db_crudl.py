"""Sessions J.5/J.6/J.7 (initiatives/multi-language-targets/thread-1-java-
target/histories/DB-CRUDL-SQLITE/) -- DB package scaffolding + JDBC bind/
extract primitives (J.5), CRUDL DAO generation (J.6), and the SQLite
round-trip acceptance gate (J.7, "nothing new -- closes the loop").

Landed together (J.6 has no standalone product without J.5's runtime to
generate against, and J.7 is explicitly "nothing new" in its own history
file) -- see JavaDatabase/CLAUDE.md.

Deliberately reduced scope for this first pass: only top-level scalar/enum
columns are handled (no embed, singular-FK-to-table, map, or repeated child
tables yet -- flagged, not silently dropped, same treatment this track
already gives schema migration). `users` (HarpiaTest/test.harpia: `address`,
`name`, both plain strings) is an all-scalar table, so its DAO is a
complete, not partial, CRUDL surface -- the right fixture for the
acceptance-gate round trip.

  - Structural (pure Python, always run): the JDBC runtime and sqlite-jdbc
    dependency are wired in; a DAO is generated per table-bearing message;
    a message with deferred columns (top_users: myUsers/members) still gets
    a DAO, just noting what it skipped.
  - Integration (gradle+JDK-gated): J.5's bind/extract round-trips every
    supported column kind (int/int64/float/string/enum) directly against a
    raw JDBC PreparedStatement/ResultSet, no generated DAO involved; J.6/J.7
    drive the generated `users_dao` through a full create/read/update/list/
    remove cycle, then -- the literal J.7 acceptance-gate bar -- write in
    one `java` process, close the connection, and read back in a SEPARATE
    `java` process to prove the data survived on disk, not just in memory.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HASH = "c96f8fd7f45108efee5a8ecb43eab1da"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests._java_gradle_helpers import generate, build_and_classpath, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None

_ALL_TYPES_HARPIA = (
    "enum color{\n"
    "    red;\n"
    "    green;\n"
    "    blue;\n"
    "}\n"
    "message all_types{\n"
    "    required string s;\n"
    "    required int n;\n"
    "    required int64 big;\n"
    "    required float f;\n"
    "    color c;\n"
    "}all_types_table;\n"
)


def _write_fixture(tmp_path, contents):
    src = tmp_path / "fixture.harpia"
    src.write_text(contents, encoding="utf-8")
    return str(src), str(tmp_path)


# -- structural ---------------------------------------------------------

def test_jdbc_runtime_and_driver_are_wired_in(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "db", "JdbcBind.java")
    assert os.path.isfile(runtime_path)
    build_gradle = open(os.path.join(out, "java", "build.gradle")).read()
    assert "sqlite-jdbc" in build_gradle


def test_crudl_dao_generated_for_all_scalar_table(tmp_path):
    out = generate(tmp_path, lang="java")
    dao_path = os.path.join(out, "java", "src", "main", "java", "com",
                            "harpia", "generated", "db", "users_dao.java")
    assert os.path.isfile(dao_path)
    text = open(dao_path).read()
    assert "user_table" in text
    assert "CREATE_TABLE_SQL" in text
    assert "JdbcBind.bind" in text
    assert "JdbcBind.extract" in text
    # "address"/"name" are real columns; STATUS_/ERROR_/ORIGINATOR (front-end-
    # injected, plain string columns, same as the C++ schema) ride along too.
    assert '"address"' in text
    assert '"name"' in text
    assert "STATUS_{}".format(HASH) in text


def test_crudl_dao_notes_deferred_columns(tmp_path):
    out = generate(tmp_path, lang="java")
    dao_path = os.path.join(out, "java", "src", "main", "java", "com",
                            "harpia", "generated", "db", "top_users_dao.java")
    assert os.path.isfile(dao_path), "top_users has scalar columns too, should still get a DAO"
    text = open(dao_path).read()
    # myUsers (singular FK-to-table) is deferred and noted, not silently
    # dropped or (worse) emitted as a broken column reference.
    assert "myUsers" in text
    assert "Deferred columns" in text
    assert "JdbcBind.bind(ps" not in text.split("Deferred columns")[1].split("\n")[0]


# -- integration: a real gradle+JDK build --------------------------------

@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_bind_extract_roundtrip_per_supported_type(tmp_path):
    harpia_file, include_folder = _write_fixture(tmp_path / "src", _ALL_TYPES_HARPIA)
    out = generate(tmp_path / "out", lang="java", harpia_file=harpia_file,
                   include_folder=include_folder)
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/BindExtract.java":
            "package smoke;\n"
            "import com.harpia.generated.all_types;\n"
            "import com.harpia.runtime.db.JdbcBind;\n"
            "import java.sql.*;\n"
            "public class BindExtract {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        all_types msg = all_types.newBuilder()\n"
            "            .setS(\"hello\").setN(42).setBig(9000000000L)\n"
            "            .setF(3.5f).setC(color.green).build();\n"
            "        Class.forName(\"org.sqlite.JDBC\");\n"
            "        try (Connection conn = DriverManager.getConnection(\"jdbc:sqlite::memory:\")) {\n"
            "            try (Statement st = conn.createStatement()) {\n"
            "                st.execute(\"CREATE TABLE t (s TEXT, n INTEGER, big INTEGER, f REAL, c INTEGER)\");\n"
            "            }\n"
            "            try (PreparedStatement ps = conn.prepareStatement(\n"
            "                    \"INSERT INTO t (s,n,big,f,c) VALUES (?,?,?,?,?)\")) {\n"
            "                JdbcBind.bind(ps, 1, msg, \"s\");\n"
            "                JdbcBind.bind(ps, 2, msg, \"n\");\n"
            "                JdbcBind.bind(ps, 3, msg, \"big\");\n"
            "                JdbcBind.bind(ps, 4, msg, \"f\");\n"
            "                JdbcBind.bind(ps, 5, msg, \"c\");\n"
            "                ps.executeUpdate();\n"
            "            }\n"
            "            all_types.Builder b = all_types.newBuilder();\n"
            "            try (Statement st = conn.createStatement();\n"
            "                 ResultSet rs = st.executeQuery(\"SELECT * FROM t\")) {\n"
            "                rs.next();\n"
            "                JdbcBind.extract(rs, \"s\", b, \"s\");\n"
            "                JdbcBind.extract(rs, \"n\", b, \"n\");\n"
            "                JdbcBind.extract(rs, \"big\", b, \"big\");\n"
            "                JdbcBind.extract(rs, \"f\", b, \"f\");\n"
            "                JdbcBind.extract(rs, \"c\", b, \"c\");\n"
            "            }\n"
            "            all_types back = b.build();\n"
            "            if (!back.getS().equals(\"hello\")) System.exit(1);\n"
            "            if (back.getN() != 42) System.exit(2);\n"
            "            if (back.getBig() != 9000000000L) System.exit(3);\n"
            "            if (back.getF() != 3.5f) System.exit(4);\n"
            "            if (back.getC() != color.green) System.exit(5);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.BindExtract"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "bind/extract round trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


_USERS_CRUDL_HELPER = (
    "package smoke;\n"
    "import com.harpia.generated.users;\n"
    "import com.harpia.generated.db.users_dao;\n"
    "import com.google.protobuf.Descriptors.FieldDescriptor;\n"
    "import java.sql.*;\n"
    "public class UsersCrudlHelper {{\n"
    "    static final String PK_FIELD = \"ID_{h}\";\n"
    "    static users withId(users.Builder b, int id) {{\n"
    "        FieldDescriptor fd = b.getDescriptorForType().findFieldByName(PK_FIELD);\n"
    "        b.setField(fd, id);\n"
    "        return b.build();\n"
    "    }}\n"
    "    static Connection open(String path) throws Exception {{\n"
    "        Class.forName(\"org.sqlite.JDBC\");\n"
    "        return DriverManager.getConnection(\"jdbc:sqlite:\" + path);\n"
    "    }}\n"
    "}}\n"
).format(h=HASH)


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_users_crudl_full_cycle(tmp_path):
    out = generate(tmp_path / "out", lang="java")
    java_root = os.path.join(out, "java")
    db_path = str(tmp_path / "cycle.db")

    classpath = build_and_classpath(java_root, {
        "smoke/UsersCrudlHelper.java": _USERS_CRUDL_HELPER,
        "smoke/CrudlCycle.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.db.users_dao;\n"
            "import java.sql.Connection;\n"
            "import java.util.ArrayList;\n"
            "import java.util.List;\n"
            "public class CrudlCycle {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        try (Connection conn = UsersCrudlHelper.open(args[0])) {\n"
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
            "            users c = UsersCrudlHelper.withId(\n"
            "                users.newBuilder().setAddress(\"zion\").setName(\"morpheus\"), 2);\n"
            "            dao.create(c);\n"
            "            List<users> all = new ArrayList<>();\n"
            "            if (!dao.list(all) || all.size() != 2) System.exit(7);\n"
            "            if (!dao.remove(1)) System.exit(8);\n"
            "            users.Builder gone = users.newBuilder();\n"
            "            if (dao.read(1, gone)) System.exit(9);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.CrudlCycle", db_path],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "CRUDL cycle failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_sqlite_round_trip_survives_process_restart(tmp_path):
    """J.7 acceptance gate: write -> persist -> restart process -> read."""
    out = generate(tmp_path / "out", lang="java")
    java_root = os.path.join(out, "java")
    db_path = str(tmp_path / "restart.db")

    classpath = build_and_classpath(java_root, {
        "smoke/UsersCrudlHelper.java": _USERS_CRUDL_HELPER,
        "smoke/DbWrite.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.db.users_dao;\n"
            "import java.sql.Connection;\n"
            "public class DbWrite {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        try (Connection conn = UsersCrudlHelper.open(args[0])) {\n"
            "            users_dao dao = new users_dao(conn);\n"
            "            dao.dropTable();\n"
            "            dao.createTable();\n"
            "            users a = UsersCrudlHelper.withId(\n"
            "                users.newBuilder().setAddress(\"matrix\").setName(\"neo\"), 1);\n"
            "            if (!dao.create(a)) System.exit(1);\n"
            "        }\n"
            "        System.out.println(\"WROTE\");\n"
            "    }\n"
            "}\n",
        "smoke/DbRead.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.db.users_dao;\n"
            "import java.sql.Connection;\n"
            "public class DbRead {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        try (Connection conn = UsersCrudlHelper.open(args[0])) {\n"
            "            users_dao dao = new users_dao(conn);\n"
            "            users.Builder got = users.newBuilder();\n"
            "            if (!dao.read(1, got)) System.exit(1);\n"
            "            if (!got.getName().equals(\"neo\") || !got.getAddress().equals(\"matrix\")) System.exit(2);\n"
            "        }\n"
            "        System.out.println(\"READ_OK\");\n"
            "    }\n"
            "}\n",
    })

    write = subprocess.run(["java", "-cp", classpath, "smoke.DbWrite", db_path],
                           capture_output=True, text=True, timeout=60)
    assert write.returncode == 0, "write process failed:\n" + write.stdout + write.stderr
    assert "WROTE" in write.stdout

    # A genuinely separate JVM process, not just a fresh Connection --
    # proves the data is on disk, not held alive in the writer's memory.
    read = subprocess.run(["java", "-cp", classpath, "smoke.DbRead", db_path],
                          capture_output=True, text=True, timeout=60)
    assert read.returncode == 0, "read process failed:\n" + read.stdout + read.stderr
    assert "READ_OK" in read.stdout
