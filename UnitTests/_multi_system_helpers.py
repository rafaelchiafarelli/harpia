"""Shared harness for the multi-system reference tests (not a test module).

multi-system-reference / reference-system: the three programs under
`HarpiaTest/app_example/multi_system/` (station, edge, handheld) built from one
generated project and run against one dev PKI. Used by
test_multi_system_station.py / _edge.py / _handheld.py / _example.py and the
load-harness tests.
"""
import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
MS = os.path.join(REPO_ROOT, "HarpiaTest", "app_example", "multi_system")
SCHEMA_DIR = os.path.join(MS, "harpia")
CLIENTS = os.path.join(SCHEMA_DIR, "clients.txt")
MTLS = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
ZAP = os.path.join(REPO_ROOT, "Assets", "cmake", "zmq_zap_provision.sh")


def _have_pkg(pkg):
    return (shutil.which("pkg-config") is not None
            and subprocess.run(["pkg-config", "--exists", pkg]).returncode == 0)


HAVE_CPP = (all(shutil.which(t) for t in ("protoc", "grpc_cpp_plugin", "g++", "cmake", "openssl", "cc"))
            and _have_pkg("grpc++") and _have_pkg("libzmq")
            and os.path.exists("/usr/include/soci/sqlite3/soci-sqlite3.h"))
CPP_SKIP = "needs cmake + g++ + protoc + grpc++ + libzmq + SOCI sqlite3 + openssl (harpia Docker image)"
HAVE_JAVA = shutil.which("gradle") is not None and shutil.which("java") is not None
JAVA_SKIP = "needs gradle + a JDK (harpia Docker image)"


def generate(out, lang="java", db_backend=None):
    """main.py on the reference schema + its own compliance profile. Java is
    generated alongside C++ (HARPIA_GEN_LANG=java keeps the C++ pipeline)."""
    env = dict(os.environ, HARPIA_OUTPUT_DIR=str(out),
               HARPIA_INPUT_FILE=os.path.join(SCHEMA_DIR, "multi_system.harpia"),
               HARPIA_INCLUDE_FOLDER=os.path.join(SCHEMA_DIR, "Include"),
               HARPIA_COMPLIANCE_CONFIG=os.path.join(SCHEMA_DIR, "project.harpia.yaml"))
    for k, v in (("HARPIA_GEN_LANG", lang), ("HARPIA_DB_BACKEND", db_backend)):
        if v:
            env[k] = v
        else:
            env.pop(k, None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return str(out)


def schema_hash(gen):
    for name in os.listdir(os.path.join(gen, "proto", "protofiles")):
        if name.startswith("reading_") and not name.endswith("_service.proto"):
            return name[len("reading_"):-len(".proto")]
    raise AssertionError("no reading_<hash>.proto generated")


def build_cpp(program, gen, build_dir):
    """cmake configure + build HarpiaTest/app_example/multi_system/<program>;
    returns the executable path."""
    src = os.path.join(MS, program)
    c = subprocess.run(["cmake", "-S", src, "-B", build_dir, "-DHARPIA_GEN=" + gen,
                        "-DCMAKE_BUILD_TYPE=Release"],
                       capture_output=True, text=True, timeout=600)
    assert c.returncode == 0, "{} configure failed:\n{}{}".format(program, c.stdout[-3000:], c.stderr[-3000:])
    b = subprocess.run(["cmake", "--build", build_dir, "-j", str(os.cpu_count() or 4)],
                       capture_output=True, text=True, timeout=1800)
    assert b.returncode == 0, "{} build failed:\n{}".format(program, (b.stdout + b.stderr)[-6000:])
    return os.path.join(build_dir, program)


def provision(base, extra_clients=(), sans=()):
    """Dev PKI + CURVE keys for clients.txt (+ extra "<id> <role>" rows).
    Returns {"pki", "zmq", "env"} -- env carries HARPIA_RBAC_MAP,
    HARPIA_SESSION_KEY and HARPIA_ZMQ_ALLOWLIST."""
    base = str(base)
    os.makedirs(base, exist_ok=True)
    clients = os.path.join(base, "clients.txt")
    with open(CLIENTS) as f:
        text = f.read()
    with open(clients, "w") as f:
        f.write(text + "".join("{}\n".format(r) for r in extra_clients))
    pki, zk = os.path.join(base, "pki"), os.path.join(base, "zmq")
    args = ["sh", MTLS, pki, "localhost", "--clients-file", clients]
    for s in sans:
        args += ["--san", s]
    r = subprocess.run(args, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run(["sh", ZAP, zk, "--clients-file", clients],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    env = dict(os.environ,
               HARPIA_RBAC_MAP=os.path.join(pki, "rbac_map.txt"),
               HARPIA_SESSION_KEY="multi-system-test-session-key",
               HARPIA_ZMQ_ALLOWLIST=os.path.join(zk, "allowlist.txt"))
    return {"pki": pki, "zmq": zk, "env": env}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@contextlib.contextmanager
def running(cmd, env, log_path, ready_port=None):
    """Start a long-running program; on exit SIGINT it and collect its log.
    Yields the Popen (with .log_path)."""
    log = open(log_path, "w")
    p = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    p.log_path = log_path
    try:
        if ready_port is not None and not wait_for_port(ready_port):
            p.kill()
            p.wait()
            log.close()
            raise AssertionError("{} never listened on {}:\n{}".format(
                os.path.basename(cmd[0]), ready_port, read(log_path)))
        yield p
    finally:
        if p.poll() is None:
            p.send_signal(signal.SIGINT)
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        log.close()


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def station_cmd(binary, port, db, pki, pool=4, stats_every=2):
    return [binary, "--listen", "127.0.0.1:{}".format(port), "--db", db,
            "--pool", str(pool), "--certs", pki, "--stats-every", str(stats_every)]


def build_handheld(gen, work):
    """The generated Java jar, then handheld's :cli:installDist; returns the
    cli launcher. The handheld sources are copied to `work` so the build output
    never lands in the repo tree."""
    env = dict(os.environ, GRADLE_USER_HOME=os.environ.get("GRADLE_USER_HOME", "/tmp/.gradle"))
    r = subprocess.run(["gradle", "-q", "build", "-x", "test"], cwd=os.path.join(gen, "java"),
                       env=env, capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, "generated java build failed:\n" + (r.stdout + r.stderr)[-4000:]
    dst = os.path.join(str(work), "handheld")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(MS, "handheld"), dst,
                    ignore=shutil.ignore_patterns("build", ".gradle"))
    r = subprocess.run(["gradle", "-q", ":cli:installDist", "-PharpiaGenDir=" + gen],
                       cwd=dst, env=env, capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, "handheld build failed:\n" + (r.stdout + r.stderr)[-4000:]
    return os.path.join(dst, "cli", "build", "install", "cli", "bin", "cli")
