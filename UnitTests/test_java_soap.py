"""Sessions J.15/J.16 (Initiatives/multi-language-targets/thread-1-java-
target/histories/SOAP/) -- SOAP envelope parsing and acceptance gate for
the Java target. Landed together -- see JavaSoapAdapter/CLAUDE.md.

Minimal hand-rolled SOAP-over-HTTP (get/set/update/delete in the Body),
NOT a real SOAP/WS-* stack -- same framing as Database/SoapAdapter.py's
C++ target. Credential-gated via the SOAP Header <credentials>.

  - Structural (pure Python, always run): the shared runtime + a per-
    message <name>_soap.java are wired in.
  - Integration (gradle+JDK-gated): a real HttpServer on an ephemeral
    port, driven with java.net.http.HttpClient posting real SOAP
    envelopes -- no/wrong credentials get a 401 Fault; a full
    set(create)/get(read)/update/delete envelope cycle against `users`,
    same fixture as the REST/DB acceptance gates.
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


# -- structural ---------------------------------------------------------

def test_soap_runtime_and_handler_are_wired_in(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "soap", "SoapHelpers.java")
    assert os.path.isfile(runtime_path)

    soap_path = os.path.join(out, "java", "src", "main", "java", "com",
                             "harpia", "generated", "soap", "users_soap.java")
    assert os.path.isfile(soap_path)
    text = open(soap_path).read()
    assert 'SoapHelpers.authorized(doc, "users", "{}")'.format(HASH) in text
    assert "users_dao" in text


# -- integration: a real gradle+JDK build, driven over real HTTP ------------

_SERVER_MAIN = (
    "package smoke;\n"
    "import com.harpia.generated.soap.users_soap;\n"
    "import com.sun.net.httpserver.HttpServer;\n"
    "import java.net.InetSocketAddress;\n"
    "import java.sql.Connection;\n"
    "import java.sql.DriverManager;\n"
    "public class SoapServer {\n"
    "    public static void main(String[] args) throws Exception {\n"
    "        Class.forName(\"org.sqlite.JDBC\");\n"
    "        Connection conn = DriverManager.getConnection(\"jdbc:sqlite:\" + args[1]);\n"
    "        com.harpia.generated.db.users_dao dao = new com.harpia.generated.db.users_dao(conn);\n"
    "        dao.dropTable();\n"
    "        dao.createTable();\n"
    "        HttpServer server = HttpServer.create(new InetSocketAddress(\"127.0.0.1\", Integer.parseInt(args[0])), 0);\n"
    "        users_soap.register(server, conn, \"\");\n"
    "        server.start();\n"
    "        System.out.println(\"LISTENING\");\n"
    "        Thread.sleep(60000);\n"
    "    }\n"
    "}\n"
)

_CLIENT_MAIN = (
    "package smoke;\n"
    "import java.net.URI;\n"
    "import java.net.http.HttpClient;\n"
    "import java.net.http.HttpRequest;\n"
    "import java.net.http.HttpResponse;\n"
    "public class SoapClient {{\n"
    "    static String envelope(String header, String body) {{\n"
    "        return \"<?xml version=\\\"1.0\\\"?><soap:Envelope \"\n"
    "            + \"xmlns:soap=\\\"http://schemas.xmlsoap.org/soap/envelope/\\\">\"\n"
    "            + header + \"<soap:Body>\" + body + \"</soap:Body></soap:Envelope>\";\n"
    "    }}\n"
    "    static String creds(String user, String pswd) {{\n"
    "        return \"<soap:Header><credentials><user>\" + user + \"</user><pswd>\" + pswd\n"
    "            + \"</pswd></credentials></soap:Header>\";\n"
    "    }}\n"
    "    public static void main(String[] args) throws Exception {{\n"
    "        String base = \"http://127.0.0.1:\" + args[0];\n"
    "        HttpClient client = HttpClient.newHttpClient();\n"
    "\n"
    "        // wrong credentials -> 401 Fault\n"
    "        HttpResponse<String> noAuth = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(\n"
    "                    envelope(creds(\"users\", \"wrong\"), \"<get><id>1</id></get>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (noAuth.statusCode() != 401) {{ System.out.println(\"noauth:\" + noAuth.statusCode()); System.exit(1); }}\n"
    "        if (!noAuth.body().contains(\"Fault\")) {{ System.out.println(noAuth.body()); System.exit(2); }}\n"
    "\n"
    "        String header = creds(\"users\", \"{h}\");\n"
    "\n"
    "        // set (create)\n"
    "        HttpResponse<String> set = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(envelope(header,\n"
    "                    \"<set><users><ID_{h}>1</ID_{h}><address>matrix</address><name>neo</name></users></set>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (set.statusCode() != 200 || !set.body().contains(\"<ok>true</ok>\")) {{\n"
    "            System.out.println(\"set:\" + set.statusCode() + \" \" + set.body()); System.exit(3);\n"
    "        }}\n"
    "\n"
    "        // get\n"
    "        HttpResponse<String> got = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(envelope(header, \"<get><id>1</id></get>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (got.statusCode() != 200 || !got.body().contains(\"<name>neo</name>\")) {{\n"
    "            System.out.println(\"get:\" + got.statusCode() + \" \" + got.body()); System.exit(4);\n"
    "        }}\n"
    "\n"
    "        // update\n"
    "        HttpResponse<String> updated = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(envelope(header,\n"
    "                    \"<update><users><ID_{h}>1</ID_{h}><address>matrix</address><name>trinity</name></users></update>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (updated.statusCode() != 200 || !updated.body().contains(\"<ok>true</ok>\")) {{\n"
    "            System.out.println(\"update:\" + updated.statusCode() + \" \" + updated.body()); System.exit(5);\n"
    "        }}\n"
    "\n"
    "        // delete\n"
    "        HttpResponse<String> deleted = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(envelope(header, \"<delete><id>1</id></delete>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (deleted.statusCode() != 200 || !deleted.body().contains(\"<ok>true</ok>\")) {{\n"
    "            System.out.println(\"delete:\" + deleted.statusCode() + \" \" + deleted.body()); System.exit(6);\n"
    "        }}\n"
    "\n"
    "        // get after delete -> not-found Fault\n"
    "        HttpResponse<String> gone = client.send(\n"
    "            HttpRequest.newBuilder(URI.create(base + \"/users\"))\n"
    "                .POST(HttpRequest.BodyPublishers.ofString(envelope(header, \"<get><id>1</id></get>\")))\n"
    "                .build(),\n"
    "            HttpResponse.BodyHandlers.ofString());\n"
    "        if (!gone.body().contains(\"Fault\")) {{ System.out.println(gone.body()); System.exit(7); }}\n"
    "\n"
    "        System.out.println(\"OK\");\n"
    "    }}\n"
    "}}\n"
).format(h=HASH)


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_soap_envelope_cycle_over_http(tmp_path):
    out = generate(tmp_path / "out", lang="java")
    java_root = os.path.join(out, "java")
    db_path = str(tmp_path / "soap.db")

    classpath = build_and_classpath(java_root, {
        "smoke/SoapServer.java": _SERVER_MAIN,
        "smoke/SoapClient.java": _CLIENT_MAIN,
    })

    port = "18733"
    server = subprocess.Popen(
        ["java", "-cp", classpath, "smoke.SoapServer", port, db_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        wait_for_listening(server)

        client = subprocess.run(["java", "-cp", classpath, "smoke.SoapClient", port],
                                capture_output=True, text=True, timeout=60)
        assert client.returncode == 0, "SOAP envelope cycle failed:\n" + client.stdout + client.stderr
        assert "OK" in client.stdout
    finally:
        server.kill()
        server.wait(timeout=10)
