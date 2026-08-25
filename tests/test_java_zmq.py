"""Session J.18 (initiatives/multi-language-targets/thread-1-java-target/
histories/ZMQ/ZMQ-core.md) -- ZMQ core transport (no CURVE, J.19) for the
Java target.

org.zeromq:jeromq (pure-Java ZMTP -- no JNI, no native library). The
transport/origin-stamping logic lives once in the shared
com.harpia.runtime.zmq.HarpiaZmq (generic over any Message via
reflection); only a thin per-message factory
(com.harpia.generated.zmq.<name>_zmq) is generated -- see
JavaZmqAdapter/CLAUDE.md.

  - Structural (pure Python, always run): the runtime + per-message
    factories (push/pull-only for `courier`, both push/pull AND pub/sub
    for `users`, HarpiaTest/test.harpia) are wired in, with the right
    origin-id expression per message's one-to-*/many-to-* classification.
  - Integration (gradle+JDK-gated): a real PUSH/PULL and PUB/SUB round
    trip over inproc://, in-process (no server subprocess needed --
    JeroMQ's inproc transport works within one JVM), confirming the
    ORIGINATOR field gets stamped on send.
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

def test_zmq_runtime_and_dependency_are_wired_in(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "zmq", "HarpiaZmq.java")
    assert os.path.isfile(runtime_path)
    build_gradle = open(os.path.join(out, "java", "build.gradle")).read()
    assert "org.zeromq:jeromq:0.6.0" in build_gradle


def test_push_pull_only_message_gets_sender_receiver_with_runtime_origin(tmp_path):
    out = generate(tmp_path, lang="java")
    path = os.path.join(out, "java", "src", "main", "java", "com", "harpia",
                        "generated", "zmq", "courier_zmq.java")
    assert os.path.isfile(path)
    text = open(path).read()
    assert "newSender" in text and "newReceiver" in text
    assert "newPublisher" not in text and "newSubscriber" not in text
    # courier is push-only (many-to-*): runtime, not compile-time, origin id.
    assert "HarpiaZmq.runtimeOriginId()" in text


def test_push_pull_and_pubsub_message_gets_all_four_with_compiletime_origin(tmp_path):
    out = generate(tmp_path, lang="java")
    path = os.path.join(out, "java", "src", "main", "java", "com", "harpia",
                        "generated", "zmq", "users_zmq.java")
    assert os.path.isfile(path)
    text = open(path).read()
    for factory in ("newSender", "newReceiver", "newPublisher", "newSubscriber"):
        assert factory in text
    # users declares pull (PULL/EVENT/STREAM present) -> one-to-*, compile-
    # time ORIGIN_ID. Each of newSender/newPublisher has a plain overload
    # and a CURVE-taking overload (J.19), both referencing ORIGIN_ID.
    assert text.count("ORIGIN_ID,") == 4
    assert "HarpiaZmq.runtimeOriginId()" not in text


# -- integration: a real gradle+JDK build ------------------------------------

@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_push_pull_roundtrip_stamps_origin(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/ZmqPushPull.java":
            "package smoke;\n"
            "import com.harpia.generated.courier;\n"
            "import com.harpia.generated.zmq.courier_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqPushPull {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            String endpoint = \"inproc://courier-test\";\n"
            "            HarpiaZmq.Receiver receiver = courier_zmq.newReceiver(ctx, endpoint);\n"
            "            HarpiaZmq.Sender sender = courier_zmq.newSender(ctx, endpoint);\n"
            "            Thread.sleep(100);\n"
            "            courier msg = courier.newBuilder().setPayload(\"hello\").build();\n"
            "            if (!sender.send(msg)) System.exit(1);\n"
            "            courier.Builder b = courier.newBuilder();\n"
            "            if (!receiver.receive(b)) System.exit(2);\n"
            "            courier got = b.build();\n"
            "            if (!got.getPayload().equals(\"hello\")) System.exit(3);\n"
            "            // courier is push-only (many-to-*): ORIGINATOR should be\n"
            "            // stamped with the sender's runtime-unique id, non-empty.\n"
            "            if (got.getORIGINATOR().isEmpty()) System.exit(4);\n"
            "            if (!got.getORIGINATOR().equals(sender.origin())) System.exit(5);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.ZmqPushPull"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "ZMQ push/pull round trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_pub_sub_roundtrip(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/ZmqPubSub.java":
            "package smoke;\n"
            "import com.harpia.generated.users;\n"
            "import com.harpia.generated.zmq.users_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqPubSub {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            String endpoint = \"inproc://users-test\";\n"
            "            HarpiaZmq.Sender pub = users_zmq.newPublisher(ctx, endpoint);\n"
            "            HarpiaZmq.Receiver sub = users_zmq.newSubscriber(ctx, endpoint);\n"
            "            sub.socket().setReceiveTimeOut(5000);\n"
            "            Thread.sleep(200);  // avoid the classic PUB/SUB \"slow joiner\"\n"
            "            users msg = users.newBuilder().setAddress(\"matrix\").setName(\"neo\").build();\n"
            "            users.Builder b = users.newBuilder();\n"
            "            boolean got = false;\n"
            "            for (int i = 0; i < 10 && !got; i++) {\n"
            "                pub.send(msg);\n"
            "                got = sub.receive(b);\n"
            "            }\n"
            "            if (!got || !b.getName().equals(\"neo\")) System.exit(1);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.ZmqPubSub"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "ZMQ pub/sub round trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
