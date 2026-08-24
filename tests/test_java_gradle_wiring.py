"""Session J.2 (initiatives/multi-language-targets/thread-1-java-target/
histories/gRPC-wiring/java_out-wiring-message-classes-only.md) -- message-
class generation for the Java target.

Per the codegen-timing decision (build-time, see histories/gRPC-wiring/
codegen-timing-decision.md), harpia doesn't shell out to protoc for Java
itself -- it stands up a self-contained Gradle project under
<dest>/java/, wired with protobuf-gradle-plugin, and the *consumer's*
Gradle build resolves protoc and generates the message classes.

Selected via HARPIA_GEN_LANG=java (default "cpp", unchanged pipeline):
  - Structural checks (no extra toolchain beyond what every other test here
    already needs) confirm the default run does NOT create a java/ tree at
    all, and that HARPIA_GEN_LANG=java produces a self-contained Gradle
    project wired to exactly the plain per-message .proto files (no
    *_service.proto, no framework protos -- gRPC is J.3's scope).
  - The real integration test (gradle+JDK-gated, not part of the harpia
    Docker image yet) actually builds the generated project and round-trips
    a message's fields through the generated builder API, proving the
    Gradle/protobuf-gradle-plugin wiring -- not just its presence -- is
    correct.
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


def test_java_lang_wires_only_plain_message_protos(tmp_path):
    out = _generate(tmp_path, lang="java")
    proto_dir = os.path.join(out, "java", "src", "main", "proto", "protofiles")
    protos = sorted(os.path.basename(p) for p in glob.glob(
        os.path.join(proto_dir, "*.proto")))
    assert protos, "no message .proto files wired into the Gradle project"
    # No gRPC yet (J.3): no service protos, no framework protos.
    assert not any(p.endswith("_service.proto") for p in protos)
    assert "errorCode.proto" not in protos
    assert "heartBeat.proto" not in protos
    assert "capabilities_service.proto" not in protos
    # A known message from HarpiaTest/test.harpia made it across.
    assert "prince_{}.proto".format(HASH) in protos


def test_java_lang_wired_protos_carry_java_options(tmp_path):
    out = _generate(tmp_path, lang="java")
    proto_path = os.path.join(out, "java", "src", "main", "proto",
                              "protofiles", "prince_{}.proto".format(HASH))
    text = open(proto_path).read()
    assert "option java_multiple_files = true;" in text
    assert 'option java_package = "com.harpia.generated";' in text


def test_java_gradle_wiring_is_write_if_different(tmp_path):
    out = _generate(tmp_path, lang="java")
    build_gradle_path = os.path.join(out, "java", "build.gradle")
    mtime1 = os.path.getmtime(build_gradle_path)
    _generate(tmp_path, lang="java")
    mtime2 = os.path.getmtime(build_gradle_path)
    assert mtime1 == mtime2


# -- integration: a real gradle+JDK build ----------------------------------

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN,
                    reason="needs gradle+JDK (Java target -- not part of the "
                          "harpia Docker image yet)")
def test_generated_message_classes_compile_and_roundtrip(tmp_path):
    out = _generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    # A tiny JUnit-free smoke program: construct a `prince` via its generated
    # builder, set fields, build, and read them back -- the same round-trip
    # test_stage7.py's C++ side proves via a real compile, not a text check.
    # Dropped into src/main/java so plain `gradle build` compiles it together
    # with the protobuf-gradle-plugin-generated message classes in one pass
    # (compileJava already depends on generateProto) and bundles both into
    # the assembled jar -- no extra Gradle task/plugin needed beyond what
    # GradleAdapter itself emits.
    smoke_dir = os.path.join(java_root, "src", "main", "java", "smoke")
    os.makedirs(smoke_dir, exist_ok=True)
    with open(os.path.join(smoke_dir, "RoundTrip.java"), "w") as f:
        f.write(
            "package smoke;\n"
            "import com.harpia.generated.prince;\n"
            "public class RoundTrip {\n"
            "    public static void main(String[] args) {\n"
            "        prince p = prince.newBuilder().setVar(42).build();\n"
            "        if (p.getVar() != 42) { System.exit(1); }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n"
        )

    build = subprocess.run(["gradle", "--no-daemon", "build"], cwd=java_root,
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, "gradle build failed:\n" + build.stdout + build.stderr

    jars = glob.glob(os.path.join(java_root, "build", "libs", "*.jar"))
    assert jars, "gradle build produced no jar under build/libs"

    protobuf_jars = glob.glob(os.path.join(
        os.path.expanduser("~"), ".gradle", "caches", "modules-2",
        "files-2.1", "com.google.protobuf", "protobuf-java", "3.25.3",
        "*", "protobuf-java-3.25.3.jar"))
    assert protobuf_jars, "protobuf-java-3.25.3.jar not found in the Gradle cache"

    classpath = os.pathsep.join(jars + protobuf_jars)
    run = subprocess.run(["java", "-cp", classpath, "smoke.RoundTrip"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "generated message class round-trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
