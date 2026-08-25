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


def generate(tmp_path, lang=None, harpia_file=None, include_folder=None,
            db_backend=None):
    """Run main.py into tmp_path, optionally with HARPIA_GEN_LANG=<lang>
    (omit for the default/cpp path). Defaults to the shared HarpiaTest
    fixture; pass harpia_file/include_folder to generate from a different
    (e.g. inline, per-test) .harpia file instead. Returns the output dir."""
    out = str(tmp_path)
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out,
              HARPIA_INPUT_FILE=harpia_file or "./HarpiaTest/test.harpia",
              HARPIA_INCLUDE_FOLDER=include_folder or "./HarpiaTest/Include")
    if lang is not None:
        env["HARPIA_GEN_LANG"] = lang
    else:
        env.pop("HARPIA_GEN_LANG", None)
    if db_backend is not None:
        env["HARPIA_DB_BACKEND"] = db_backend
    else:
        env.pop("HARPIA_DB_BACKEND", None)
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

    # Daemon kept ON (not --no-daemon): ~10 test files each run their own
    # `gradle build` from a fresh tmp_path project. A live daemon persists
    # for the life of the container's pytest process (dies with the
    # container on --rm, no orphaned host process), so invocation 2+ reuse
    # an already-warm JVM instead of paying full Gradle bootstrap every time.
    build = subprocess.run(["gradle", "build"], cwd=java_root,
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, "gradle build failed:\n" + build.stdout + build.stderr

    jars = glob.glob(os.path.join(java_root, "build", "libs", "*.jar"))
    assert jars, "gradle build produced no jar under build/libs"

    cp = subprocess.run(
        ["gradle", "-q", "--console=plain", "harpiaRuntimeClasspath"],
        cwd=java_root, capture_output=True, text=True, timeout=120,
    )
    assert cp.returncode == 0, "harpiaRuntimeClasspath failed:\n" + cp.stdout + cp.stderr
    line = next((l for l in cp.stdout.splitlines()
                if l.startswith("HARPIA_RUNTIME_CLASSPATH=")), None)
    assert line, "no HARPIA_RUNTIME_CLASSPATH= line in:\n" + cp.stdout
    runtime_classpath = line[len("HARPIA_RUNTIME_CLASSPATH="):]

    return os.pathsep.join(jars) + os.pathsep + runtime_classpath


def wait_for_listening(server, marker="LISTENING", max_lines=50):
    """Read `server`'s (stdout+stderr merged) output line by line looking
    for `marker`, tolerating noise lines before it -- e.g. SLF4J's
    "Failed to load class StaticLoggerBinder" static-init warning, which
    genuinely does print before the marker line (confirmed by hand: a
    naive single `server.stdout.readline()` grabs that warning instead,
    the `"LISTENING" in line` assert fails, and building its failure
    message via `server.stdout.read()` then blocks forever, since the
    server process never exits and its stdout pipe never EOFs -- a
    deadlock disguised as a hang, not an actual server startup failure).
    Bounded by max_lines so a server that genuinely never starts fails
    fast; on failure, kills the process FIRST so any further stdout read
    can't block the same way."""
    lines = []
    for _ in range(max_lines):
        line = server.stdout.readline()
        if not line:
            break
        lines.append(line)
        if marker in line:
            return
    server.kill()
    server.wait(timeout=10)
    raise AssertionError(
        "server never printed {!r} within {} lines:\n{}".format(
            marker, max_lines, "".join(lines)))
