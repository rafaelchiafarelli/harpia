"""Session J.4 (Initiatives/multi-language-targets/thread-1-java-target/
histories/JSON/pass-through.md) -- JSON pass-through for the Java target.

Unlike C++'s JsonAdapter (one generated wrapper header per message), the
Java target ships a single hand-written runtime class
(JavaJsonAdapter/runtime/HarpiaJson.java, com.harpia.runtime.json.HarpiaJson)
and generates nothing per message -- see JavaJsonAdapter/CLAUDE.md for why
that's not a shortcut, but the actually-correct shape once protobuf-java's
common Message/Builder interfaces make JsonFormat generic already.

  - Structural (pure Python, always run): HARPIA_GEN_LANG=java copies the
    runtime class in and wires protobuf-java-util into build.gradle.
  - Integration (gradle+JDK-gated): a real JSON round trip through the
    generated builder API, confirming protobuf's canonical camelCase field
    mapping (patient_id -> "patientId") -- the literal J.4 test bar.
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

from UnitTests._java_gradle_helpers import generate, build_and_classpath, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


# -- structural -------------------------------------------------------------

def test_json_runtime_is_wired_into_the_gradle_project(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "json", "HarpiaJson.java")
    assert os.path.isfile(runtime_path)
    text = open(runtime_path).read()
    assert "package com.harpia.runtime.json;" in text
    assert "JsonFormat" in text


def test_build_gradle_depends_on_protobuf_java_util(tmp_path):
    out = generate(tmp_path, lang="java")
    build_gradle = open(os.path.join(out, "java", "build.gradle")).read()
    assert "protobuf-java-util" in build_gradle


# -- integration: a real gradle+JDK build ------------------------------------

@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_json_roundtrip_uses_canonical_camelcase_mapping(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/JsonRoundTrip.java":
            "package smoke;\n"
            "import com.harpia.generated.patient_vitals;\n"
            "import com.harpia.runtime.json.HarpiaJson;\n"
            "public class JsonRoundTrip {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        patient_vitals p = patient_vitals.newBuilder()\n"
            "            .setPatientId(\"p-42\").setHeartRate(72.5f).build();\n"
            "        String json = HarpiaJson.toJson(p);\n"
            "        if (!json.contains(\"patientId\")) { System.out.println(json); System.exit(1); }\n"
            "        if (json.contains(\"patient_id\")) { System.out.println(json); System.exit(2); }\n"
            "        patient_vitals.Builder b = patient_vitals.newBuilder();\n"
            "        HarpiaJson.fromJson(json, b);\n"
            "        patient_vitals back = b.build();\n"
            "        if (!back.getPatientId().equals(\"p-42\") || back.getHeartRate() != 72.5f) {\n"
            "            System.exit(3);\n"
            "        }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.JsonRoundTrip"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "JSON round trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
