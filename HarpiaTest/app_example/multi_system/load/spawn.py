#!/usr/bin/env python3
"""Start many load clients against one station (load-harness task 2).

    spawn.py --station host:port --edges N --handhelds M --duration S --ramp S
             --pki DIR --out DIR --edge-bin PATH --handheld-bin PATH
             [--edge-pub tcp://host:port --zmq-keys DIR] [--guests G]
             [--emulators K] [--rate R] [--mix C:L:R] [--authority NAME]
             [--identity-offset I] [--id-base B] [--id-stride S] [--xmx SIZE]

Python 3 stdlib only, so it runs on a load machine without harpia's Docker
image; POSIX and Windows.

Each client is one `edge --load` or `handheld --load` process with its own
identity: the identities come from <pki>/rbac_map.txt (written by
mtls_provision.sh --clients-file; --identities names another file in the
same format), role `main` for edges and handhelds, role
`guest` for --guests (edge-type clients whose creates are refused -- a
deliberate denial, so a run shows the RBAC gate working under load). Too few
identities fails before anything starts. --identity-offset skips the first I
`main` identities, so several load machines each run spawn.py on a disjoint
slice; the primary-key ranges (--id-base + index * --id-stride) follow the
same index, so the slices never collide on ids either.

Starts are staggered evenly over --ramp seconds so the TLS and CURVE
handshakes don't all land at once; every client then runs --duration
seconds. Nothing is restarted: a client that exits non-zero before it is
told to stop is recorded as crashed. Everything is stopped at the end (or on
Ctrl-C): SIGINT, then SIGKILL after a grace period, by process group on
POSIX, so no process outlives spawn.py.

Out dir: one <identity>.jsonl report + <identity>.log per client, and
spawn.json ({"args", "clients": [{identity, kind, role, exit_code, crashed,
report, log}]}) -- report.py reads all of it.

--emulators K additionally starts the handheld app in load mode on the first
K devices `adb devices` lists (intent extras, see the app's MainActivity),
and pulls each one's files/load.jsonl into <out>/emulator-<serial>.jsonl
when the run ends. The app uses its bundled identity.

Host limits checked before starting (warnings, not errors):
  - open files (ulimit -n): ~8 per client here, plus the clients' own;
  - ephemeral ports (/proc/sys/net/ipv4/ip_local_port_range) vs clients;
  - available RAM vs M handheld JVMs at --xmx (default 96m) + ~80 MB each.
The handheld JVMs get JAVA_OPTS="-Xmx<xmx> -XX:+UseSerialGC
-XX:TieredStopAtLevel=1" unless JAVA_OPTS is already set.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

POSIX = os.name == "posix"
APP_PKG = "com.harpia.multisystem.handheld.app"


def read_identities(pki, path=None):
    path = path or os.path.join(pki, "rbac_map.txt")
    if not os.path.exists(path):
        raise SystemExit("spawn: no {} -- provision with mtls_provision.sh --clients-file".format(path))
    by_role = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                if os.path.exists(os.path.join(pki, "client_{}.pem".format(parts[0]))):
                    by_role.setdefault(parts[1], []).append(parts[0])
    return by_role


def plan(a, by_role):
    """[(identity, kind, role, index)]; SystemExit if there aren't enough."""
    mains = by_role.get("main", [])[a.identity_offset:]
    guests = by_role.get("guest", [])
    need = a.edges + a.handhelds
    if len(mains) < need:
        raise SystemExit("spawn: {} edges + {} handhelds need {} `main` identities, {} available "
                         "(after --identity-offset {}) in {}".format(
                             a.edges, a.handhelds, need, len(mains), a.identity_offset,
                             a.identities or os.path.join(a.pki, "rbac_map.txt")))
    if len(guests) < a.guests:
        raise SystemExit("spawn: --guests {} needs {} `guest` identities, {} available".format(
            a.guests, a.guests, len(guests)))
    out = []
    for i, ident in enumerate(mains[:need]):
        out.append((ident, "edge" if i < a.edges else "handheld", "main", a.identity_offset + i))
    for j, ident in enumerate(guests[:a.guests]):
        out.append((ident, "edge", "guest", a.identity_offset + need + j))
    return out


def check_limits(a, n):
    warn = []
    try:
        import resource
        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft != resource.RLIM_INFINITY and soft < 8 * n + 64:
            warn.append("ulimit -n is {}; {} clients want ~{} (raise it: ulimit -n 65536)".format(
                soft, n, 8 * n + 64))
    except ImportError:
        pass
    try:
        with open("/proc/sys/net/ipv4/ip_local_port_range") as f:
            lo, hi = (int(x) for x in f.read().split())
        if hi - lo < 4 * n:
            warn.append("ephemeral port range {}-{} is small for {} clients".format(lo, hi, n))
    except (OSError, ValueError):
        pass
    try:
        with open("/proc/meminfo") as f:
            avail = next(int(l.split()[1]) for l in f if l.startswith("MemAvailable:")) // 1024
        want = a.handhelds * (_mb(a.xmx) + 80) + (a.edges + a.guests) * 20
        if want > avail:
            warn.append("{} handheld JVMs at -Xmx{} + edges want ~{} MB, {} MB available".format(
                a.handhelds, a.xmx, want, avail))
    except (OSError, StopIteration, ValueError):
        pass
    for w in warn:
        print("spawn: WARNING: " + w, file=sys.stderr)
    return warn


def _mb(size):
    s = size.lower()
    mult = {"k": 1.0 / 1024, "m": 1, "g": 1024}.get(s[-1:], None)
    return int(float(s[:-1]) * mult) if mult else int(s) // (1024 * 1024)


def client_cmd(a, ident, kind, index):
    common = ["--load", "--identity", ident, "--station", a.station, "--certs", a.pki,
              "--rate", str(a.rate), "--duration", str(a.duration), "--mix", a.mix,
              "--id-base", str(a.id_base + index * a.id_stride),
              "--report", os.path.join(a.out, ident + ".jsonl")]
    if a.authority:
        common += ["--authority", a.authority]
    if kind == "edge":
        return [a.edge_bin] + common
    cmd = [a.handheld_bin] + common
    if a.edge_pub:
        cmd += ["--sub", a.edge_pub, "--zmq-keys", a.zmq_keys]
    return cmd


class Proc:
    def __init__(self, ident, kind, role, cmd, log_path, env):
        self.ident, self.kind, self.role, self.log_path = ident, kind, role, log_path
        self.log = open(log_path, "w")
        kw = {"start_new_session": True} if POSIX else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        self.stopped = False   # we asked it to stop: a non-zero exit after that isn't a crash
        try:
            self.p = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT, env=env, **kw)
        except OSError as e:
            self.log.write("spawn: cannot start {}: {}\n".format(cmd[0], e))
            self.p = None

    def signal(self, kill=False):
        if self.p is None or self.p.poll() is not None:
            return
        self.stopped = True
        try:
            if POSIX:
                os.killpg(self.p.pid, signal.SIGKILL if kill else signal.SIGINT)
            elif kill:
                self.p.kill()
            else:
                self.p.send_signal(signal.CTRL_BREAK_EVENT)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def result(self):
        code = None if self.p is None else self.p.poll()
        crashed = self.p is None or (code not in (0, None) and not self.stopped)
        if POSIX and self.p is not None:
            try:   # anything left in its group (a JVM's children) goes too
                os.killpg(self.p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        self.log.close()
        return {"identity": self.ident, "kind": self.kind, "role": self.role,
                "exit_code": code if self.p is not None else "not-started", "crashed": crashed,
                "report": self.ident + ".jsonl", "log": os.path.basename(self.log_path)}


def adb(*args, timeout=60):
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)


def emulators_start(a):
    if a.emulators <= 0:
        return []
    if shutil.which("adb") is None:
        raise SystemExit("spawn: --emulators needs adb on PATH")
    serials = [l.split()[0] for l in adb("devices").stdout.splitlines()[1:]
               if l.strip().endswith("device")][:a.emulators]
    if len(serials) < a.emulators:
        raise SystemExit("spawn: --emulators {} but adb lists {} device(s)".format(a.emulators, len(serials)))
    for s in serials:
        adb("-s", s, "shell", "am", "force-stop", APP_PKG)
        adb("-s", s, "shell", "run-as", APP_PKG, "rm", "-f", "files/load.jsonl")
        r = adb("-s", s, "shell", "am", "start", "-n", APP_PKG + "/.MainActivity",
                "--ez", "load", "true", "--ef", "load.rate", str(a.rate),
                "--ei", "load.duration", str(a.duration), "--es", "load.mix", a.mix)
        if r.returncode != 0:
            raise SystemExit("spawn: am start on {} failed: {}".format(s, r.stdout + r.stderr))
    return serials


def emulators_collect(a, serials):
    out = []
    for s in serials:
        path = os.path.join(a.out, "emulator-{}.jsonl".format(s))
        r = subprocess.run(["adb", "-s", s, "exec-out", "run-as", APP_PKG, "cat", "files/load.jsonl"],
                           capture_output=True, timeout=120)
        with open(path, "wb") as f:
            f.write(r.stdout if r.returncode == 0 else b"")
        adb("-s", s, "shell", "am", "force-stop", APP_PKG)
        out.append({"identity": "emulator-" + s, "kind": "handheld-android", "role": "main",
                    "exit_code": r.returncode, "crashed": r.returncode != 0,
                    "report": os.path.basename(path), "log": None})
    return out


def parse(argv):
    ap = argparse.ArgumentParser(description="Start many load clients against one station.")
    ap.add_argument("--station", required=True, help="host:port of station")
    ap.add_argument("--authority", help="TLS name to verify when --station isn't in the cert's SAN")
    ap.add_argument("--edge-pub", help="an ordinary edge's ZMQ endpoint; handhelds subscribe to it")
    ap.add_argument("--zmq-keys", help="CURVE key dir (zmq_zap_provision.sh); needed with --edge-pub")
    ap.add_argument("--edges", type=int, default=0)
    ap.add_argument("--handhelds", type=int, default=0)
    ap.add_argument("--guests", type=int, default=0, help="edge-type clients with role guest (denied creates)")
    ap.add_argument("--emulators", type=int, default=0)
    ap.add_argument("--ramp", type=float, default=10.0)
    ap.add_argument("--duration", type=int, required=True)
    ap.add_argument("--rate", type=float, default=5.0, help="ops/s per client (default 5)")
    ap.add_argument("--mix", default="8:1:1", help="create:list:read weights (default 8:1:1)")
    ap.add_argument("--pki", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--edge-bin", default="edge")
    ap.add_argument("--handheld-bin", default="handheld")
    ap.add_argument("--identities", help="'<identity> <role>' file (default <pki>/rbac_map.txt)")
    ap.add_argument("--identity-offset", type=int, default=0)
    ap.add_argument("--id-base", type=int, default=10000000)
    ap.add_argument("--id-stride", type=int, default=100000)
    ap.add_argument("--xmx", default="96m", help="heap per handheld JVM (default 96m)")
    ap.add_argument("--grace", type=float, default=30.0, help="seconds past the end before SIGINT")
    a = ap.parse_args(argv)
    if a.edges < 0 or a.handhelds < 0 or a.guests < 0 or a.edges + a.handhelds + a.guests + a.emulators == 0:
        ap.error("nothing to spawn: give --edges / --handhelds / --guests / --emulators")
    if a.duration <= 0 or a.rate <= 0 or a.ramp < 0:
        ap.error("--duration and --rate must be > 0, --ramp >= 0")
    if a.edge_pub and not a.zmq_keys:
        ap.error("--edge-pub needs --zmq-keys")
    if a.id_base + (a.identity_offset + a.edges + a.handhelds + a.guests) * a.id_stride > 2**31 - 1:
        ap.error("--id-base + clients * --id-stride overflows the int32 primary key")
    return a


def main(argv=None):
    a = parse(argv)
    a.pki, a.out = os.path.abspath(a.pki), os.path.abspath(a.out)
    for b in ("edge_bin", "handheld_bin"):
        p = getattr(a, b)
        if os.path.sep in p or (os.altsep and os.altsep in p):
            setattr(a, b, os.path.abspath(p))
    clients = plan(a, read_identities(a.pki, a.identities))   # fails fast, before anything starts
    os.makedirs(a.out, exist_ok=True)
    warnings = check_limits(a, len(clients))

    env = dict(os.environ)
    env.setdefault("JAVA_OPTS", "-Xmx{} -XX:+UseSerialGC -XX:TieredStopAtLevel=1".format(a.xmx))

    stop = {"now": False}

    def on_signal(signum, frame):
        stop["now"] = True
    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    procs = []
    t0 = time.monotonic()
    step = a.ramp / max(1, len(clients) - 1) if len(clients) > 1 else 0.0
    print("spawn: {} clients ({} edge, {} handheld, {} guest) over {} s ramp, {} s each".format(
        len(clients), a.edges, a.handhelds, a.guests, a.ramp, a.duration), flush=True)
    serials = []
    try:
        serials = emulators_start(a)
        for i, (ident, kind, role, index) in enumerate(clients):
            due = t0 + i * step
            while not stop["now"] and time.monotonic() < due:
                time.sleep(min(0.05, due - time.monotonic()))
            if stop["now"]:
                break
            procs.append(Proc(ident, kind, role, client_cmd(a, ident, kind, index),
                              os.path.join(a.out, ident + ".log"), env))
        deadline = t0 + a.ramp + a.duration + a.grace
        # the emulators stop themselves after --duration; give them a moment to flush
        emu_done = t0 + a.ramp + a.duration + 5 if serials else t0
        while not stop["now"] and time.monotonic() < deadline:
            if all(p.p is None or p.p.poll() is not None for p in procs) and time.monotonic() >= emu_done:
                break
            time.sleep(0.2)
    finally:
        for p in procs:
            p.signal()
        end = time.monotonic() + 15
        while time.monotonic() < end and any(p.p is not None and p.p.poll() is None for p in procs):
            time.sleep(0.1)
        for p in procs:
            p.signal(kill=True)
        for p in procs:
            if p.p is not None:
                p.p.wait()
        results = [p.result() for p in procs] + emulators_collect(a, serials)
        with open(os.path.join(a.out, "spawn.json"), "w", encoding="utf-8") as f:
            json.dump({"args": {k: v for k, v in vars(a).items()}, "interrupted": stop["now"],
                       "warnings": warnings, "clients": results}, f, indent=2, sort_keys=True)
            f.write("\n")
    crashed = [r["identity"] for r in results if r["crashed"]]
    print("spawn: done, {} clients, {} crashed{}".format(
        len(results), len(crashed), (": " + ", ".join(crashed)) if crashed else ""), flush=True)
    return 130 if stop["now"] else 0


if __name__ == "__main__":
    sys.exit(main())
