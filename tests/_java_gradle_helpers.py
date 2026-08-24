"""Shared helpers for the Java target's gradle+JDK-gated integration tests
(test_java_gradle_wiring.py, test_java_json_pass_through.py, and future
sessions' Java tests). Not itself a test module (no test_ prefix).
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

SKIP_REASON = ("needs gradle+JDK (Java target -- not part of the harpia "
              "Docker image yet)")


def generate(tmp_path, lang=None):
    """Run main.py into tmp_path, optionally with HARPIA_GEN_LANG=<lang>
    (omit for the default/cpp path). Returns the output dir."""
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


def build_and_classpath(java_root, extra_source):
    """Drop `extra_source` (relative path under src/main/java -> content)
    into the generated Gradle project, `gradle build` it (protobuf-gradle-
    plugin's generateProto runs first, so the smoke source compiles against
    the generated message/stub classes in the same pass), then resolve a
    runnable classpath via the harpiaRuntimeClasspath task GradleAdapter
    wires into every generated build.gradle -- no hand-guessing which
    transitive dependency jars landed in the Gradle cache under which
    version."""
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

    cp = subprocess.run(
        ["gradle", "--no-daemon", "-q", "--console=plain", "harpiaRuntimeClasspath"],
        cwd=java_root, capture_output=True, text=True, timeout=120,
    )
    assert cp.returncode == 0, "harpiaRuntimeClasspath failed:\n" + cp.stdout + cp.stderr
    line = next((l for l in cp.stdout.splitlines()
                if l.startswith("HARPIA_RUNTIME_CLASSPATH=")), None)
    assert line, "no HARPIA_RUNTIME_CLASSPATH= line in:\n" + cp.stdout
    runtime_classpath = line[len("HARPIA_RUNTIME_CLASSPATH="):]

    return os.pathsep.join(jars) + os.pathsep + runtime_classpath
