"""Sessions J.12/J.13/J.14 (initiatives/multi-language-targets/thread-1-
java-target/histories/REST/) -- REST routing scaffolding, CRUDL handlers,
and acceptance gate for the Java target. Landed together -- see
JavaRestAdapter/CLAUDE.md.

Routes on JDK-builtin com.sun.net.httpserver.HttpServer, credential-gated
(X-User/X-Pswd) and content-negotiated (JSON/XML via the already-generic
HarpiaJson/HarpiaXml runtimes), same shape as Database/RestAdapter.py's
C++ target.

  - Structural (pure Python, always run): the shared runtime + a per-
    message <name>_rest.java are wired in.
  - Integration (gradle+JDK-gated): a real HttpServer on an ephemeral
    port, driven with java.net.http.HttpClient -- the credential gate
    rejects a request with no/wrong credentials (401); a full create/
    read/update/list/delete cycle over HTTP against `users` (all-scalar,
    same fixture as the DB layer's own acceptance gate); a JSON body in,
    an XML body back out via Accept: application/xml, proving content
    negotiation actually dispatches, not just that both runtimes exist.
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

from tests._java_gradle_helpers import generate, build_and_classpath, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


# -- structural ---------------------------------------------------------

def test_rest_runtime_and_handler_are_wired_in(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "rest", "HttpRestHelpers.java")
    assert os.path.isfile(runtime_path)

    rest_path = os.path.join(out, "java", "src", "main", "java", "com",
                             "harpia", "generated", "rest", "users_rest.java")
    assert os.path.isfile(rest_path)
    text = open(rest_path).read()
    assert 'authorized(exchange, "users", "{}")'.format(HASH) in text
    assert "users_dao" in text


# -- integration: a real gradle+JDK build, driven over real HTTP ------------

_SERVER_MAIN = (
    "package smoke;\n"
    "import com.harpia.generated.rest.users_rest;\n"
    "import com.sun.net.httpserver.HttpServer;\n"
    "import java.net.InetSocketAddress;\n"
    "import java.sql.Connection;\n"
    "import java.sql.DriverManager;\n"
    "public class RestServer {\n"
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
    "}\n"
)


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_rest_crud_cycle_over_http(tmp_path):
    out = generate(tmp_path / "out", lang="java")
    java_root = os.path.join(out, "java")
    db_path = str(tmp_path / "rest.db")

    classpath = build_and_classpath(java_root, {
        "smoke/RestServer.java": _SERVER_MAIN,
        "smoke/RestClient.java":
            "package smoke;\n"
            "import java.net.URI;\n"
            "import java.net.http.HttpClient;\n"
            "import java.net.http.HttpRequest;\n"
            "import java.net.http.HttpResponse;\n"
            "public class RestClient {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        String base = \"http://127.0.0.1:\" + args[0];\n"
            "        HttpClient client = HttpClient.newHttpClient();\n"
            "\n"
            "        // no credentials -> 401\n"
            "        HttpResponse<String> noAuth = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users\")).GET().build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (noAuth.statusCode() != 401) { System.out.println(\"noauth:\" + noAuth.statusCode()); System.exit(1); }\n"
            "\n"
            "        // create (JSON body)\n"
            "        String createJson = \"{\\\"address\\\":\\\"matrix\\\",\\\"name\\\":\\\"neo\\\"}\";\n"
            "        HttpResponse<String> created = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .header(\"Content-Type\", \"application/json\")\n"
            "                .POST(HttpRequest.BodyPublishers.ofString(createJson)).build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (created.statusCode() != 201) { System.out.println(\"create:\" + created.statusCode()); System.exit(2); }\n"
            "\n"
            "        // read back as XML (content negotiation)\n"
            "        HttpResponse<String> got = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users/1\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .header(\"Accept\", \"application/xml\")\n"
            "                .GET().build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (got.statusCode() != 200) { System.out.println(\"read:\" + got.statusCode()); System.exit(3); }\n"
            "        if (!got.body().contains(\"<name>neo</name>\")) { System.out.println(got.body()); System.exit(4); }\n"
            "\n"
            "        // update\n"
            "        String updateJson = \"{\\\"address\\\":\\\"matrix\\\",\\\"name\\\":\\\"trinity\\\"}\";\n"
            "        HttpResponse<String> updated = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users/1\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .header(\"Content-Type\", \"application/json\")\n"
            "                .PUT(HttpRequest.BodyPublishers.ofString(updateJson)).build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (updated.statusCode() != 204) { System.out.println(\"update:\" + updated.statusCode()); System.exit(5); }\n"
            "\n"
            "        // list\n"
            "        HttpResponse<String> listed = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .GET().build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (listed.statusCode() != 200 || !listed.body().contains(\"trinity\")) {\n"
            "            System.out.println(\"list:\" + listed.statusCode() + \" \" + listed.body()); System.exit(6);\n"
            "        }\n"
            "\n"
            "        // delete\n"
            "        HttpResponse<String> deleted = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users/1\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .DELETE().build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (deleted.statusCode() != 204) { System.out.println(\"delete:\" + deleted.statusCode()); System.exit(7); }\n"
            "\n"
            "        HttpResponse<String> gone = client.send(\n"
            "            HttpRequest.newBuilder(URI.create(base + \"/users/1\"))\n"
            "                .header(\"X-User\", \"users\").header(\"X-Pswd\", \"{h}\")\n"
            "                .GET().build(),\n"
            "            HttpResponse.BodyHandlers.ofString());\n"
            "        if (gone.statusCode() != 404) { System.out.println(\"gone:\" + gone.statusCode()); System.exit(8); }\n"
            "\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n".format(h=HASH),
    })

    port = "18732"
    server = subprocess.Popen(
        ["java", "-cp", classpath, "smoke.RestServer", port, db_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        line = server.stdout.readline()
        assert "LISTENING" in line, "server did not start:\n" + line + server.stdout.read()

        client = subprocess.run(["java", "-cp", classpath, "smoke.RestClient", port],
                                capture_output=True, text=True, timeout=60)
        assert client.returncode == 0, "REST CRUD cycle failed:\n" + client.stdout + client.stderr
        assert "OK" in client.stdout
    finally:
        server.kill()
        server.wait(timeout=10)
