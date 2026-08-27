"""Session J.23 (Initiatives/multi-language-targets/thread-1-java-target/
histories/Generated-tests-packaging/full-generate-build-run-demo-golden-
baseline.md) -- full generate -> build -> run demo + golden baseline for
the Java target. "Deliverable: nothing new -- proves the whole surface
works together" (this session's own history file).

The golden-snapshot baseline itself is UnitTests/test_golden_java.py
(UnitTests/golden_java/) -- this file is the "run demo" half.

Note on what's *already* proven by every earlier gradle+JDK-gated test in
this thread, not just this one: Gradle's `build` task depends on `check`,
which depends on `test` by default (the `java` plugin's own convention).
So every `gradle build` this thread's tests have run since J.2 already
compiled the ENTIRE src/main/java tree together (every adapter's output
in one build, not just whatever smoke file that particular test added)
and, since J.21 landed, already ran the full generated JUnit suite too.
"The whole surface works together" has been a continuously-checked
property throughout this thread, not something left for this session to
discover for the first time.

What's genuinely new here: a cross-subsystem demo proving these layers
don't just each work in their own isolated test fixture, but actually
interoperate through shared state -- a REST-created row is directly
readable through the DB DAO against the very same SQLite file, mirroring
the point of the C++ target's own client/server demo (independently-built
pieces that actually talk to the same backing store/wire).
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath, wait_for_listening, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_rest_created_row_is_visible_through_the_db_layer_directly(tmp_path):
    out = generate(tmp_path / "out", lang="java")
    java_root = os.path.join(out, "java")
    db_path = str(tmp_path / "demo.db")

    classpath = build_and_classpath(java_root, {
        "smoke/DemoServer.java":
            "package smoke;\n"
            "import com.harpia.generated.rest.users_rest;\n"
            "import com.sun.net.httpserver.HttpServer;\n"
            "import java.net.InetSocketAddress;\n"
            "import java.sql.Connection;\n"
            "import java.sql.DriverManager;\n"
            "public class DemoServer {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        Class.forName(\"org.sqlite.JDBC\");\n"
            "        Connection conn = DriverManager.getConnection(\"jdbc:sqlite:\" + args[1]);\n"
            "        com.harpia.generated.db.users_dao dao = new com.harpia.generated.db.users_dao(conn);\n"
            "        dao.dropTable();\n"
            "        dao.createTable();\n"
            "        HttpServer server = HttpServer.create(new InetSocketAddress(\"127.0.0.1\", Integer.parseInt(args[0])), 0);\n"
            "        users_rest.register(server, conn, \"\");\n"
            "        server.start();\n"
            "        System.out.println(\"LISTENING\");\n"
            "        Thread.sleep(60000);\n"
            "    }\n"
            "}\n",
        "smoke/DemoCheck.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.db.users_dao;\n"
            "import java.net.URI;\n"
            "import java.net.http.HttpClient;\n"
            "import java.net.http.HttpRequest;\n"
            "import java.net.http.HttpResponse;\n"
            "import java.sql.Connection;\n"
            "import java.sql.DriverManager;\n"
            "public class DemoCheck {{\n"
            "    public static void main(String[] args) throws Exception {{\n"
            "        String base = \"http://127.0.0.1:\" + args[0];\n"
            "        HttpClient client = HttpClient.newHttpClient();\n"
            "        String createJson = \"{{\\\"ID{h}\\\":1,\\\"address\\\":\\\"wonderland\\\",\\\"name\\\":\\\"alice\\\"}}\";\n"
            "        HttpResponse<String> created = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .header(\"Content-Type\", \"application/json\")\n"
            "                .POST(HttpRequest.BodyPublishers.ofString(createJson)).build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (created.statusCode() != 201) {{ System.out.println(\"create:\" + created.statusCode()); System.exit(1); }}\n"
            "\n"
            "        // A SEPARATE JDBC connection to the SAME file, going through the\n"
            "        // DB layer directly, not the REST layer -- proving the REST\n"
            "        // handler's write and the DAO's read share real, persisted state.\n"
            "        Class.forName(\"org.sqlite.JDBC\");\n"
            "        try (Connection conn = DriverManager.getConnection(\"jdbc:sqlite:\" + args[1])) {{\n"
            "            users_dao dao = new users_dao(conn);\n"
            "            users.Builder got = users.newBuilder();\n"
            "            if (!dao.read(1, got)) {{ System.exit(2); }}\n"
            "            if (!got.getName().equals(\"alice\") || !got.getAddress().equals(\"wonderland\")) {{\n"
            "                System.exit(3);\n"
            "            }}\n"
            "        }}\n"
            "        System.out.println(\"OK\");\n"
            "    }}\n"
            "}}\n".format(h=HASH),
    })

    port = "18742"
    server = subprocess.Popen(
        ["java", "-cp", classpath, "smoke.DemoServer", port, db_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        wait_for_listening(server)

        check = subprocess.run(["java", "-cp", classpath, "smoke.DemoCheck", port, db_path],
                               capture_output=True, text=True, timeout=60)
        assert check.returncode == 0, "full demo check failed:\n" + check.stdout + check.stderr
        assert "OK" in check.stdout
    finally:
        server.kill()
        server.wait(timeout=10)
