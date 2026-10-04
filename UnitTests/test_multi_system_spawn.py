"""multi-system-reference / load-harness task 2 -- spawn.py.

10 edge + 10 handheld load clients (the handhelds subscribed to an ordinary
edge's stream) for 10 s against station (SQLite): 20 JSONL reports and
spawn.json with no crash, and no client process outlives spawn.py. The same
for a run stopped early with SIGINT (Ctrl-C). Too few identities fails
before anything starts.
"""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    CPP_SKIP, HAVE_CPP, HAVE_JAVA, JAVA_SKIP, MS, build_cpp, build_handheld, free_port,
    generate, provision, running, station_cmd)

pytestmark = [pytest.mark.skipif(not HAVE_CPP, reason=CPP_SKIP),
              pytest.mark.skipif(not HAVE_JAVA, reason=JAVA_SKIP)]

SPAWN = os.path.join(MS, "load", "spawn.py")
N = 10


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_spawn")
    gen = generate(tmp / "gen")
    extra = (["ld-e{:02d} main".format(i) for i in range(N)]
             + ["ld-h{:02d} main".format(i) for i in range(N)])
    pki = provision(tmp / "pki", extra_clients=extra)
    # only the ld-* identities, so spawn.py's pool is exactly the load clients
    ids = str(tmp / "load_ids.txt")
    with open(ids, "w") as f:
        f.write("".join(r + "\n" for r in extra))
    return {"station": build_cpp("station", gen, str(tmp / "b_station")),
            "edge": build_cpp("edge", gen, str(tmp / "b_edge")),
            "cli": build_handheld(gen, tmp), "pki": pki, "ids": ids}


def _orphans(out):
    """PIDs whose command line mentions this run's out dir (every client's
    --report does)."""
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            with open("/proc/{}/cmdline".format(pid), "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if out in cmd and "spawn.py" not in cmd:
            found.append((pid, cmd[:200]))
    return found


def _spawn(b, sport, endpoint, out, duration, **kw):
    pki = b["pki"]
    return subprocess.Popen(
        [sys.executable, SPAWN, "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
         "--edge-pub", endpoint, "--zmq-keys", pki["zmq"], "--pki", pki["pki"], "--identities", b["ids"],
         "--edges", str(N), "--handhelds", str(N), "--ramp", "2", "--duration", str(duration),
         "--rate", "5", "--xmx", "64m", "--edge-bin", b["edge"], "--handheld-bin", b["cli"], "--out", out],
        env=pki["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)


def _system(b, tmp_path):
    pki = b["pki"]
    sport, pport = free_port(), free_port()
    endpoint = "tcp://127.0.0.1:{}".format(pport)
    st = running(station_cmd(b["station"], sport, "sqlite:" + str(tmp_path / "st.db"), pki["pki"], pool=8),
                 pki["env"], str(tmp_path / "station.log"), ready_port=sport)
    ed = running([b["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                  "--certs", pki["pki"], "--identity", "edge", "--pub", endpoint, "--zmq-keys", pki["zmq"],
                  "--interval", "100", "--notes-every", "0", "--id-base", "1"],
                 pki["env"], str(tmp_path / "edge.log"))
    return sport, endpoint, st, ed


def _spawn_json(out):
    with open(os.path.join(out, "spawn.json")) as f:
        return json.load(f)


def test_spawn_10_plus_10(built, tmp_path):
    out = str(tmp_path / "out")
    sport, endpoint, st, ed = _system(built, tmp_path)
    with st, ed:
        p = _spawn(built, sport, endpoint, out, 10)
        log = p.communicate(timeout=180)[0]
    assert p.returncode == 0, log
    reports = sorted(n for n in os.listdir(out) if n.endswith(".jsonl"))
    assert reports == sorted(["ld-e{:02d}.jsonl".format(i) for i in range(N)]
                             + ["ld-h{:02d}.jsonl".format(i) for i in range(N)])
    sj = _spawn_json(out)
    assert len(sj["clients"]) == 2 * N and not sj["interrupted"]
    assert [c for c in sj["clients"] if c["crashed"] or c["exit_code"] != 0] == [], sj["clients"]
    for name in reports:
        with open(os.path.join(out, name)) as f:
            ops = [json.loads(l) for l in f if l.strip()]
        assert any(r["op"] == "create" and r["ok"] for r in ops), (name, ops[:3])
        if name.startswith("ld-h"):
            assert any(r["op"] == "sub_recv" for r in ops), name
    # distinct primary-key ranges: no client hit another's ids
    assert "ALREADY_EXISTS" not in "".join(open(os.path.join(out, n)).read() for n in reports)
    assert _orphans(out) == []


def test_sigint_stops_everything(built, tmp_path):
    out = str(tmp_path / "out")
    sport, endpoint, st, ed = _system(built, tmp_path)
    with st, ed:
        p = _spawn(built, sport, endpoint, out, 120)
        time.sleep(8)
        p.send_signal(signal.SIGINT)
        log = p.communicate(timeout=60)[0]
    assert p.returncode == 130, log
    sj = _spawn_json(out)
    assert sj["interrupted"] and len(sj["clients"]) == 2 * N, log
    assert [c for c in sj["clients"] if c["crashed"]] == [], sj["clients"]
    assert _orphans(out) == []


def test_too_few_identities_fails_first(built, tmp_path):
    out = str(tmp_path / "out")
    t = time.monotonic()
    r = subprocess.run([sys.executable, SPAWN, "--station", "127.0.0.1:1", "--pki", built["pki"]["pki"],
                        "--identities", built["ids"], "--edges", str(N), "--handhelds", str(N + 1),
                        "--duration", "5", "--out", out, "--edge-bin", built["edge"],
                        "--handheld-bin", built["cli"]],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "need 21 `main` identities, 20 available" in r.stderr, r.stderr
    assert not os.path.exists(out) and time.monotonic() - t < 10
