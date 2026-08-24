"""Sessions J.2/J.3 (initiatives/multi-language-targets/thread-1-java-target)
-- message-class + gRPC stub generation for the Java target.

Per the codegen-timing decision (build-time, see histories/gRPC-wiring/
codegen-timing-decision.md), harpia doesn't shell out to protoc/
protoc-gen-grpc-java for Java itself -- it stands up a self-contained Gradle
project under <dest>/java/, wired with protobuf-gradle-plugin (+ its grpc
plugin, J.3), and the *consumer's* Gradle build resolves both and generates
the message + stub classes.

Selected via HARPIA_GEN_LANG=java (default "cpp", unchanged pipeline):
  - Structural checks (no extra toolchain beyond what every other test here
    already needs) confirm the default run does NOT create a java/ tree at
    all, and that HARPIA_GEN_LANG=java produces a self-contained Gradle
    project wired to every message .proto AND _service.proto, plus the two
    framework protos (errorCode/heartBeat) those import -- NOT
    capabilities_service.proto, an unrelated whole-project gRPC capability
    advertisement out of scope here.
  - The real integration tests (gradle+JDK-gated, not part of the harpia
    Docker image yet) actually build the generated project: J.2's proves a
    message round-trips through its generated builder API, J.3's proves the
    generated gRPC stub compiles and links against those message classes.
"""
import glob
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


def _generate(tmp_path, lang=None):
    out = str(tmp_path)
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out,
              HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
              HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include")
    if lang is not None:
        env["HARPIA_GEN_LANG"] = lang
    else:
        env.pop("HARPIA_GEN_LANG", None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return out


# -- structural: HARPIA_GEN_LANG gating -----------------------------------

def test_default_lang_does_not_create_java_project(tmp_path):
    out = _generate(tmp_path)
    assert not os.path.exists(os.path.join(out, "java"))


def test_cpp_lang_does_not_create_java_project(tmp_path):
    out = _generate(tmp_path, lang="cpp")
    assert not os.path.exists(os.path.join(out, "java"))


# -- structural: the Gradle project itself ---------------------------------

def test_java_lang_creates_gradle_project(tmp_path):
    out = _generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")
    assert os.path.isfile(os.path.join(java_root, "build.gradle"))
    assert os.path.isfile(os.path.join(java_root, "settings.gradle"))

    build_gradle = open(os.path.join(java_root, "build.gradle")).read()
    assert "com.google.protobuf" in build_gradle
    assert "protobuf-java" in build_gradle
    assert "grpc" in build_gradle
    assert "protoc-gen-grpc-java" in build_gradle


def test_java_lang_wires_message_and_service_protos(tmp_path):
    out = _generate(tmp_path, lang="java")
    proto_dir = os.path.join(out, "java", "src", "main", "proto", "protofiles")
    protos = sorted(os.path.basename(p) for p in glob.glob(
        os.path.join(proto_dir, "*.proto")))
    assert protos, "no .proto files wired into the Gradle project"

    # A known message and its service proto both made it across.
    assert "prince_{}.proto".format(HASH) in protos
    assert "prince_{}_service.proto".format(HASH) in protos
    # The framework protos _service.proto imports.
    assert "errorCode.proto" in protos
    assert "heartBeat.proto" in protos
    # NOT the unrelated whole-project capability-advertisement service.
    assert "capabilities_service.proto" not in protos


def test_java_lang_wired_protos_carry_java_options(tmp_path):
    out = _generate(tmp_path, lang="java")
    proto_dir = os.path.join(out, "java", "src", "main", "proto", "protofiles")
    for fileName in ("prince_{}.proto".format(HASH),
                     "prince_{}_service.proto".format(HASH),
                     "errorCode.proto", "heartBeat.proto"):
        text = open(os.path.join(proto_dir, fileName)).read()
        assert "option java_multiple_files = true;" in text, fileName
        assert 'option java_package = "com.harpia.generated";' in text, fileName


def test_java_gradle_wiring_is_write_if_different(tmp_path):
    out = _generate(tmp_path, lang="java")
    build_gradle_path = os.path.join(out, "java", "build.gradle")
    mtime1 = os.path.getmtime(build_gradle_path)
    _generate(tmp_path, lang="java")
    mtime2 = os.path.getmtime(build_gradle_path)
    assert mtime1 == mtime2


# -- integration: a real gradle+JDK build ----------------------------------

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None
_SKIP_REASON = ("needs gradle+JDK (Java target -- not part of the harpia "
               "Docker image yet)")


def _build(tmp_path, java_root, extra_source):
    """Drop `extra_source` (relative path -> content) into src/main/java,
    then `gradle build` -- protobuf-gradle-plugin's generateProto runs first
    (compileJava depends on it), so the smoke source compiles against the
    generated message/stub classes in the same pass. Returns the classpath
    (assembled jar + resolved runtime deps) to run a class from it."""
    for relpath, content in extra_source.items():
        path = os.path.join(java_root, "src", "main", "java", relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    build = subprocess.run(["gradle", "--no-daemon", "build"], cwd=java_root,
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, "gradle build failed:\n" + build.stdout + build.stderr

    jars = glob.glob(os.path.join(java_root, "build", "libs", "*.jar"))
    assert jars, "gradle build produced no jar under build/libs"

    gradle_cache = os.path.join(os.path.expanduser("~"), ".gradle", "caches",
                                "modules-2", "files-2.1")

    def _cached_jar(group, artifact, version):
        found = glob.glob(os.path.join(gradle_cache, group, artifact, version,
                                       "*", "{}-{}.jar".format(artifact, version)))
        assert found, "{}:{}:{} not found in the Gradle cache".format(
            group, artifact, version)
        return found

    runtime_jars = (
        _cached_jar("com.google.protobuf", "protobuf-java", "3.25.3")
        + _cached_jar("io.grpc", "grpc-protobuf", "1.62.2")
        + _cached_jar("io.grpc", "grpc-stub", "1.62.2")
        + _cached_jar("io.grpc", "grpc-api", "1.62.2")
    )
    return os.pathsep.join(jars + runtime_jars)


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=_SKIP_REASON)
def test_generated_message_classes_compile_and_roundtrip(tmp_path):
    out = _generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    # A tiny JUnit-free smoke program: construct a `prince` via its generated
    # builder, set fields, build, and read them back -- the same round-trip
    # test_stage7.py's C++ side proves via a real compile, not a text check.
    classpath = _build(tmp_path, java_root, {
        "smoke/RoundTrip.java":
            "package smoke;\n"
            "import com.harpia.generated.prince;\n"
            "public class RoundTrip {\n"
            "    public static void main(String[] args) {\n"
            "        prince p = prince.newBuilder().setVar(42).build();\n"
            "        if (p.getVar() != 42) { System.exit(1); }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.RoundTrip"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "generated message class round-trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=_SKIP_REASON)
def test_generated_grpc_stub_compiles_and_links(tmp_path):
    out = _generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    # Instantiating the generated ImplBase (an anonymous subclass, no
    # methods overridden) proves the grpc-plugin-generated stub for
    # `prince_Service` compiles and links against grpc-stub/grpc-protobuf,
    # without needing a running server -- exactly J.3's "compiles and
    # links" bar, not a live RPC round trip.
    classpath = _build(tmp_path, java_root, {
        "smoke/GrpcLink.java":
            "package smoke;\n"
            "import com.harpia.generated.prince_ServiceGrpc;\n"
            "public class GrpcLink {\n"
            "    public static void main(String[] args) {\n"
            "        prince_ServiceGrpc.prince_ServiceImplBase impl =\n"
            "            new prince_ServiceGrpc.prince_ServiceImplBase() {};\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.GrpcLink"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "generated gRPC stub link check failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
