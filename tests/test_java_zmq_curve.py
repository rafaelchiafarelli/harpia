"""Session J.19 (initiatives/multi-language-targets/thread-1-java-target/
histories/ZMQ/CURVE-secured-ZMQ-variant.md) -- CURVE-secured ZMQ variant
for the Java target, building on J.18's core transport now that J.17
confirmed JeroMQ supports CURVE on the pinned version.

Every com.harpia.generated.zmq.<name>_zmq factory method gets a CURVE-
taking overload (HarpiaZmq.CurveKeys) -- see JavaZmqAdapter/CLAUDE.md.

  - Structural (pure Python, always run): the generated factories carry
    the CURVE-taking overloads, and the shared runtime exposes
    CurveKeys/generateCurveKeyPair.
  - Integration (gradle+JDK-gated): a real CURVE handshake over tcp://
    (CURVE is a no-op over inproc://, which every other ZMQ test in this
    thread uses -- this one needs a real socket, same discipline as the
    C++ target's own test_stage13_zmq.py) -- matching keys succeed, a
    wrong server public key on the client side times out rather than
    silently succeeding plaintext.
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

from tests._java_gradle_helpers import generate, build_and_classpath, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


# -- structural ---------------------------------------------------------

def test_zmq_factories_carry_curve_overloads(tmp_path):
    out = generate(tmp_path, lang="java")
    path = os.path.join(out, "java", "src", "main", "java", "com", "harpia",
                        "generated", "zmq", "courier_zmq.java")
    text = open(path).read()
    assert "HarpiaZmq.CurveKeys curve" in text
    assert text.count("HarpiaZmq.CurveKeys curve") >= 2  # newSender + newReceiver


def test_curve_keys_runtime_api_is_wired_in(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "zmq", "HarpiaZmq.java")
    text = open(runtime_path).read()
    assert "class CurveKeys" in text
    assert "generateCurveKeyPair" in text
    assert "setCurveServer" in text
    assert "setCurveServerKey" in text


# -- integration: a real gradle+JDK build, real CURVE handshake over tcp:// --

_CURVE_HELPER = (
    "package smoke;\n"
    "import com.harpia.runtime.zmq.HarpiaZmq;\n"
    "public class CurveKeysHelper {\n"
    "    public static HarpiaZmq.CurveKeys server(byte[] secretKey) {\n"
    "        return HarpiaZmq.CurveKeys.server(secretKey);\n"
    "    }\n"
    "    public static HarpiaZmq.CurveKeys client(byte[] serverPub, byte[] pub, byte[] sec) {\n"
    "        return HarpiaZmq.CurveKeys.client(serverPub, pub, sec);\n"
    "    }\n"
    "}\n"
)


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_curve_handshake_matching_keys_succeed(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/CurveKeysHelper.java": _CURVE_HELPER,
        "smoke/ZmqCurveOk.java":
            "package smoke;\n"
            "import com.harpia.generated.courier;\n"
            "import com.harpia.generated.zmq.courier_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqCurveOk {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        byte[][] server = HarpiaZmq.generateCurveKeyPair();\n"
            "        byte[][] client = HarpiaZmq.generateCurveKeyPair();\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            String endpoint = \"tcp://127.0.0.1:\" + args[0];\n"
            "            HarpiaZmq.Receiver receiver = courier_zmq.newReceiver(ctx, endpoint,\n"
            "                CurveKeysHelper.server(server[1]));\n"
            "            HarpiaZmq.Sender sender = courier_zmq.newSender(ctx, endpoint,\n"
            "                CurveKeysHelper.client(server[0], client[0], client[1]));\n"
            "            receiver.socket().setReceiveTimeOut(5000);\n"
            "            Thread.sleep(200);\n"
            "            courier msg = courier.newBuilder().setPayload(\"secret\").build();\n"
            "            courier.Builder b = courier.newBuilder();\n"
            "            boolean got = false;\n"
            "            for (int i = 0; i < 10 && !got; i++) {\n"
            "                sender.send(msg);\n"
            "                got = receiver.receive(b);\n"
            "            }\n"
            "            if (!got || !b.getPayload().equals(\"secret\")) System.exit(1);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.ZmqCurveOk", "18740"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "CURVE handshake (matching keys) failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_curve_handshake_wrong_server_key_times_out(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/CurveKeysHelper.java": _CURVE_HELPER,
        "smoke/ZmqCurveWrongKey.java":
            "package smoke;\n"
            "import com.harpia.generated.courier;\n"
            "import com.harpia.generated.zmq.courier_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqCurveWrongKey {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        byte[][] server = HarpiaZmq.generateCurveKeyPair();\n"
            "        byte[][] impostor = HarpiaZmq.generateCurveKeyPair();\n"
            "        byte[][] client = HarpiaZmq.generateCurveKeyPair();\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            String endpoint = \"tcp://127.0.0.1:\" + args[0];\n"
            "            HarpiaZmq.Receiver receiver = courier_zmq.newReceiver(ctx, endpoint,\n"
            "                CurveKeysHelper.server(server[1]));\n"
            "            // client is told the WRONG server public key (impostor's, not\n"
            "            // server's own) -- the handshake must not complete.\n"
            "            HarpiaZmq.Sender sender = courier_zmq.newSender(ctx, endpoint,\n"
            "                CurveKeysHelper.client(impostor[0], client[0], client[1]));\n"
            "            receiver.socket().setReceiveTimeOut(2000);\n"
            "            // A wrong server key means the CURVE handshake never\n"
            "            // completes, so the PUSH socket never gets a ready peer to\n"
            "            // queue to -- send() itself blocks, not just receive() (found\n"
            "            // by hand: a diagnostic run showed \"sending...\" printed but\n"
            "            // send() never returned). Bound it the same way.\n"
            "            sender.socket().setSendTimeOut(2000);\n"
            "            Thread.sleep(200);\n"
            "            courier msg = courier.newBuilder().setPayload(\"secret\").build();\n"
            "            sender.send(msg);\n"
            "            courier.Builder b = courier.newBuilder();\n"
            "            if (receiver.receive(b)) {\n"
            "                System.out.println(\"unexpectedly received a message\");\n"
            "                System.exit(1);\n"
            "            }\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.ZmqCurveWrongKey", "18741"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "CURVE wrong-key test failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
