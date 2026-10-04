"""multi-system-reference / load-harness task 1 -- load mode in `edge` and
`handheld` (`--load --identity --rate --duration --mix --report`).

Each client runs 5 s at 20 ops/s against `station` (SQLite) and writes one
JSON line per operation: {t, client_kind, identity, op, ok, grpc_code,
latency_us} -- plus, for the session issue, op "session", and for handheld
one {t, identity, op: "sub_recv", seq_gap} per live sample received from an
ordinary edge's stream. Checked: every line parses with exactly those keys,
the operation count is within 10% of rate x duration, every op is ok, and the
ops follow the mix (create / list / read; the generated gRPC surface has no
update RPC).
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    CPP_SKIP, HAVE_CPP, HAVE_JAVA, JAVA_SKIP, build_cpp, build_handheld, free_port,
    generate, provision, running, station_cmd)

pytestmark = [pytest.mark.skipif(not HAVE_CPP, reason=CPP_SKIP),
              pytest.mark.skipif(not HAVE_JAVA, reason=JAVA_SKIP)]

RATE, DURATION = 20, 5
OP_KEYS = {"t", "client_kind", "identity", "op", "ok", "grpc_code", "latency_us"}
SUB_KEYS = {"t", "client_kind", "identity", "op", "seq_gap"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_load_mode")
    gen = generate(tmp / "gen")
    return {"tmp": tmp, "gen": gen,
            "station": build_cpp("station", gen, str(tmp / "b_station")),
            "edge": build_cpp("edge", gen, str(tmp / "b_edge")),
            "cli": build_handheld(gen, tmp),
            "pki": provision(tmp / "pki", extra_clients=("edge-load main", "handheld-load main"))}


def _records(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _check_ops(recs, kind, identity):
    session = [r for r in recs if r["op"] == "session"]
    ops = [r for r in recs if r["op"] in ("create", "list", "read")]
    assert len(session) == 1 and session[0]["ok"], session
    for r in session + ops:
        assert set(r) == OP_KEYS, r
        assert r["client_kind"] == kind and r["identity"] == identity, r
        assert isinstance(r["t"], float) and isinstance(r["latency_us"], int), r
    want = RATE * DURATION
    assert abs(len(ops) - want) <= 0.1 * want, "{} ops, want ~{}".format(len(ops), want)
    bad = [r for r in ops if not r["ok"] or r["grpc_code"] != "OK"]
    assert not bad, bad[:5]
    counts = {o: sum(1 for r in ops if r["op"] == o) for o in ("create", "list", "read")}
    assert counts["create"] > counts["list"] and counts["create"] > counts["read"], counts
    assert counts["list"] >= 1 and counts["read"] >= 1, counts
    return ops


def test_edge_and_handheld_load_mode(built, tmp_path):
    b = built
    pki, zk, env = b["pki"]["pki"], b["pki"]["zmq"], b["pki"]["env"]
    sport, pport = free_port(), free_port()
    endpoint = "tcp://127.0.0.1:{}".format(pport)
    edge_rep = str(tmp_path / "edge-load.jsonl")
    hh_rep = str(tmp_path / "handheld-load.jsonl")
    common = ["--station", "127.0.0.1:{}".format(sport), "--authority", "localhost", "--certs", pki,
              "--rate", str(RATE), "--duration", str(DURATION), "--mix", "6:2:2"]
    with running(station_cmd(b["station"], sport, "sqlite:" + str(tmp_path / "st.db"), pki), env,
                 str(tmp_path / "station.log"), ready_port=sport):
        # an ordinary edge supplies the live stream the load handheld subscribes to
        with running([b["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                      "--certs", pki, "--identity", "edge", "--pub", endpoint, "--zmq-keys", zk,
                      "--interval", "50", "--notes-every", "0", "--id-base", "1", "--duration", "30"],
                     env, str(tmp_path / "edge.log")):
            hh = subprocess.Popen([b["cli"], "--load", "--identity", "handheld-load", "--sub", endpoint,
                                   "--zmq-keys", zk, "--id-base", "700000", "--report", hh_rep] + common,
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            e = subprocess.run([b["edge"], "--load", "--identity", "edge-load", "--id-base", "300000",
                                "--report", edge_rep] + common,
                               env=env, capture_output=True, text=True, timeout=120)
            hh_out = hh.communicate(timeout=120)[0]
    assert e.returncode == 0, e.stdout + e.stderr
    assert hh.returncode == 0, hh_out
    _check_ops(_records(edge_rep), "edge", "edge-load")

    recs = _records(hh_rep)
    _check_ops(recs, "handheld", "handheld-load")
    subs = [r for r in recs if r["op"] == "sub_recv"]
    assert len(subs) >= 20, "only {} samples received".format(len(subs))
    for r in subs:
        assert set(r) == SUB_KEYS and isinstance(r["seq_gap"], int) and r["seq_gap"] >= 0, r


def test_load_mode_argument_errors(built, tmp_path):
    r = subprocess.run([built["edge"], "--load", "--identity", "edge-load", "--duration", "5"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "--report" in r.stderr
    r = subprocess.run([built["edge"], "--load", "--identity", "edge-load", "--duration", "5",
                        "--report", str(tmp_path / "x.jsonl"), "--mix", "1:2"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "--mix" in r.stderr
    r = subprocess.run([built["cli"], "--load", "--identity", "x", "--rate", "5"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2, r.stdout + r.stderr
