"""Hardened C++ servers for the Android emulator tests (multi-system-reference /
java-hardened-client task 4). Not a test module: a harness, like
run_pipeline.py, started in the background by
Docker/_android_emulator_test_entrypoint.sh in the SAME container as the
emulator (the emulator reaches this container's loopback as 10.0.2.2).

    python3 UnitTests/run_android_hardened_servers.py <work_dir> <assets_dir>

Builds and starts, from the HarpiaTest fixture (hardened profile):
  * the generated C++ GrpcServer on 0.0.0.0:<grpc port>: mTLS required and
    verified, RBAC (`handheld` -> main), bearer sessions (HARPIA_SESSION_KEY);
  * a C++ publisher on tcp://0.0.0.0:<zmq port>: the generated
    `users_publisher`, CURVE server + ZAP allowlist (only the `handheld` key),
    publishing a `users` message (name "edge") every 100 ms.

Writes into <assets_dir> what HardenedLinksAndroidTest reads as androidTest
assets (app/build.gradle adds it via -PharpiaHardenedDir): ca.pem,
client.pem, client_key.pem (identity `handheld`), zmq_server_public.key,
zmq_handheld_{public,secret}.key, and harpia_hardened.properties
(grpc.port, zmq.port). Then touches <work_dir>/READY and serves until
SIGTERM / SIGINT, stopping both servers on the way out.
"""
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
ZMQ_PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "zmq_zap_provision.sh")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_grpc_server_helpers import (  # noqa: E402
    HASH, build_server, provision, free_port)

_PUB_CC = r"""
#include "zmq/users_{h}_zmq.h"
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
// argv: bind_endpoint server_secret_z85. Publishes until killed.
int main(int, char** argv) {{
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::users_publisher pub(
        ctx, argv[1], "edge-android-test",
        harpia::zmq_transport::CurveServerKeys{{argv[2]}});
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::cout << "LISTENING" << std::endl;
    for (;;) {{
        ::users out; out.set_name("edge"); out.set_address("linux");
        pub.publish(out);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }}
}}
"""


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _read_key(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _start(cmd, env, name, log_path):
    """Start a server with its output going to `log_path` (never an undrained
    pipe) and wait until it prints LISTENING."""
    log = open(log_path, "w")
    # stdin stays an open pipe: the gRPC server serves until its stdin closes
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log,
                            stderr=subprocess.STDOUT, env=env)
    for _ in range(300):
        with open(log_path) as fh:
            if "LISTENING" in fh.read():
                return proc
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    proc.kill()
    with open(log_path) as fh:
        raise SystemExit("{} never started:\n{}".format(name, fh.read()))


def main(work_dir, assets_dir):
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    print("building the C++ gRPC server ...", flush=True)
    grpc_bin = build_server(work_dir)

    print("building the C++ ZMQ publisher ...", flush=True)
    cpp_root = os.path.join(work_dir, "build", "generated", "cpp")
    src = os.path.join(work_dir, "zmq_pub.cc")
    with open(src, "w") as f:
        f.write(_PUB_CC.format(h=HASH))
    pub_bin = os.path.join(work_dir, "zmq_pub")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"), src,
         os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH)),
         "-o", pub_bin, *_pkgconfig("--libs"), "-lpthread"],
        capture_output=True, text=True)
    if c.returncode != 0:
        raise SystemExit("publisher failed to build:\n" + c.stderr)

    print("provisioning mTLS + CURVE identities ...", flush=True)
    pki = os.path.join(work_dir, "pki")
    provision(pki, "handheld")
    rbac_map = os.path.join(work_dir, "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write("handheld main\n")
    zmq_keys = os.path.join(work_dir, "zmq")
    p = subprocess.run(["sh", ZMQ_PROVISION, zmq_keys, "handheld"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("zmq provisioning failed:\n" + p.stdout + p.stderr)

    grpc_port, zmq_port = free_port(), free_port()
    servers = []

    def stop(*_):
        for s in servers:
            if s.poll() is None:
                s.terminate()
        for s in servers:
            try:
                s.wait(timeout=10)
            except subprocess.TimeoutExpired:
                s.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    servers.append(_start(
        [grpc_bin, "0.0.0.0:{}".format(grpc_port), os.path.join(pki, "ca.pem"),
         os.path.join(pki, "server.pem"), os.path.join(pki, "server_key.pem")],
        {**os.environ, "HARPIA_RBAC_MAP": rbac_map,
         "HARPIA_SESSION_KEY": "android-emulator-test-key"},
        "gRPC server", os.path.join(work_dir, "grpc_server.log")))
    servers.append(_start(
        [pub_bin, "tcp://0.0.0.0:{}".format(zmq_port),
         _read_key(os.path.join(zmq_keys, "zmq_server_secret.key"))],
        {**os.environ, "HARPIA_ZMQ_ALLOWLIST": os.path.join(zmq_keys, "allowlist.txt")},
        "ZMQ publisher", os.path.join(work_dir, "zmq_publisher.log")))

    for name in ("ca.pem", "client.pem", "client_key.pem"):
        shutil.copy(os.path.join(pki, name), os.path.join(assets_dir, name))
    for name in ("zmq_server_public.key", "zmq_handheld_public.key",
                 "zmq_handheld_secret.key"):
        shutil.copy(os.path.join(zmq_keys, name), os.path.join(assets_dir, name))
    with open(os.path.join(assets_dir, "harpia_hardened.properties"), "w") as fh:
        fh.write("grpc.port={}\nzmq.port={}\n".format(grpc_port, zmq_port))

    open(os.path.join(work_dir, "READY"), "w").close()
    print("SERVERS_READY grpc={} zmq={}".format(grpc_port, zmq_port), flush=True)
    while True:
        for s in servers:
            if s.poll() is not None:
                print("a server exited (rc={}); logs in {}".format(s.returncode, work_dir),
                      flush=True)
                stop()
        time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
