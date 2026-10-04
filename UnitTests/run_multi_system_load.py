"""multi-system-reference / load-harness task 4 -- the smoke-at-scale gate.

Run by Docker/run_multi_system_load.sh inside the harpia image, with
HARPIA_PG_DSN pointing at a throwaway PostgreSQL. Not a pytest module: it
runs ~2 minutes and is opt-in.

  1. generate the reference system for PostgreSQL; build station, edge and
     the handheld CLI; provision a PKI with EDGES + HANDHELDS load
     identities (role main) and GUESTS guest identities;
  2. start station (pooled, PostgreSQL) and one ordinary edge that publishes
     the live stream the handhelds subscribe to (device "stream");
  3. spawn.py: EDGES edge + HANDHELDS handheld JVM load clients + GUESTS guest
     clients, DURATION s each, ramped over RAMP s;
  4. report.py, then the gate:
       - zero crashed clients, zero malformed records;
       - zero errors other than the guests' PERMISSION_DENIED creates, and
         every guest create was denied;
       - zero rows lost: reading rows (except the stream edge's) equal the
         edges' successful creates, field_note rows equal the handhelds'
         successful creates (counted over libpq, no client library needed);
       - every handheld received samples.

Exit 0 = pass. The out dir (summary.md, every JSONL and log) is kept under
build/multi_system_load/ for a look afterwards.

    EDGES / HANDHELDS / GUESTS / DURATION / RAMP / RATE env vars override the
    defaults (50 / 50 / 2 / 60 / 15 / 5).
"""
import ctypes
import ctypes.util
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    MS, build_cpp, build_handheld, free_port, generate, provision, read, running, station_cmd)

LOAD = os.path.join(MS, "load")
EDGES = int(os.environ.get("EDGES", "50"))
HANDHELDS = int(os.environ.get("HANDHELDS", "50"))
GUESTS = int(os.environ.get("GUESTS", "2"))
DURATION = int(os.environ.get("DURATION", "60"))
RAMP = int(os.environ.get("RAMP", "15"))
RATE = os.environ.get("RATE", "5")


def pg_count(dsn, sql):
    """One integer from PostgreSQL through libpq via ctypes (the image has
    libpq for SOCI, but no Python driver)."""
    lib = ctypes.CDLL(ctypes.util.find_library("pq") or "libpq.so.5")
    lib.PQconnectdb.restype = ctypes.c_void_p
    lib.PQconnectdb.argtypes = [ctypes.c_char_p]
    lib.PQstatus.argtypes = [ctypes.c_void_p]
    lib.PQerrorMessage.restype = ctypes.c_char_p
    lib.PQerrorMessage.argtypes = [ctypes.c_void_p]
    lib.PQexec.restype = ctypes.c_void_p
    lib.PQexec.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.PQresultStatus.argtypes = [ctypes.c_void_p]
    lib.PQgetvalue.restype = ctypes.c_char_p
    lib.PQgetvalue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.PQclear.argtypes = [ctypes.c_void_p]
    lib.PQfinish.argtypes = [ctypes.c_void_p]
    conn = lib.PQconnectdb(dsn.encode())
    try:
        if lib.PQstatus(conn) != 0:   # CONNECTION_OK
            raise RuntimeError("libpq: " + lib.PQerrorMessage(conn).decode())
        res = lib.PQexec(conn, sql.encode())
        try:
            if lib.PQresultStatus(res) != 2:   # PGRES_TUPLES_OK
                raise RuntimeError("libpq: {}: {}".format(sql, lib.PQerrorMessage(conn).decode()))
            return int(lib.PQgetvalue(res, 0, 0))
        finally:
            lib.PQclear(res)
    finally:
        lib.PQfinish(conn)


def records(out):
    recs = []
    for name in sorted(os.listdir(out)):
        if name.endswith(".jsonl"):
            with open(os.path.join(out, name)) as f:
                recs += [json.loads(l) for l in f if l.strip()]
    return recs


def main():
    dsn = os.environ.get("HARPIA_PG_DSN")
    if not dsn:
        print("run_multi_system_load: HARPIA_PG_DSN is not set (use Docker/run_multi_system_load.sh)")
        return 2
    work = os.path.join(REPO_ROOT, "build", "multi_system_load")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    out = os.path.join(work, "out")

    t = time.monotonic()
    gen = generate(os.path.join(work, "gen"), db_backend="postgresql")
    station = build_cpp("station", gen, os.path.join(work, "b_station"))
    edge = build_cpp("edge", gen, os.path.join(work, "b_edge"))
    cli = build_handheld(gen, work)
    extra = (["ld-e{:03d} main".format(i) for i in range(EDGES)]
             + ["ld-h{:03d} main".format(i) for i in range(HANDHELDS)]
             + ["ld-g{:03d} guest".format(i) for i in range(GUESTS)])
    pki = provision(os.path.join(work, "pki"), extra_clients=extra)
    print("gate: built + provisioned {} identities in {:.0f} s".format(len(extra), time.monotonic() - t),
          flush=True)
    certs, zk, env = pki["pki"], pki["zmq"], pki["env"]

    # spawn.py takes `main` identities in rbac_map order: skip the reference
    # system's own (edge, handheld) so the load clients are exactly ld-*.
    with open(os.path.join(certs, "rbac_map.txt")) as f:
        rows = [l.split() for l in f if l.strip() and not l.startswith("#")]
    offset = sum(1 for r in rows if r[1] == "main" and not r[0].startswith("ld-"))
    guests_before = sum(1 for r in rows if r[1] == "guest" and not r[0].startswith("ld-"))
    assert guests_before == 1, rows   # clients.txt's `guest`; drop it from the pool below
    rows = [r for r in rows if not (r[1] == "guest" and not r[0].startswith("ld-"))]
    with open(os.path.join(certs, "rbac_map.spawn.txt"), "w") as f:
        f.write("".join("{} {}\n".format(*r) for r in rows))

    sport, pport = free_port(), free_port()
    endpoint = "tcp://127.0.0.1:{}".format(pport)
    with running(station_cmd(station, sport, dsn, certs, pool=16, stats_every=10), env,
                 os.path.join(work, "station.log"), ready_port=sport) as st:
        with running([edge, "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                      "--certs", certs, "--identity", "edge", "--device", "stream", "--pub", endpoint,
                      "--zmq-keys", zk, "--interval", "100", "--notes-every", "0", "--id-base", "1"],
                     env, os.path.join(work, "stream_edge.log")):
            time.sleep(1)
            r = subprocess.run(
                [sys.executable, os.path.join(LOAD, "spawn.py"),
                 "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                 "--edge-pub", endpoint, "--zmq-keys", zk, "--pki", certs,
                 "--identities", os.path.join(certs, "rbac_map.spawn.txt"),
                 "--identity-offset", str(offset),
                 "--edges", str(EDGES), "--handhelds", str(HANDHELDS), "--guests", str(GUESTS),
                 "--ramp", str(RAMP), "--duration", str(DURATION), "--rate", RATE,
                 "--edge-bin", edge, "--handheld-bin", cli, "--out", out],
                env=env, timeout=RAMP + DURATION + 300)
    print(read(st.log_path)[-1500:])
    if r.returncode != 0:
        print("gate: FAIL spawn.py exited {}".format(r.returncode))
        return 1
    subprocess.run([sys.executable, os.path.join(LOAD, "report.py"), out], check=True)

    with open(os.path.join(out, "summary.json")) as f:
        s = json.load(f)
    recs = records(out)
    ops = [x for x in recs if x["op"] != "sub_recv"]
    guest = lambda x: x["identity"].startswith("ld-g")   # noqa: E731
    fails = []
    if s["clients"].get("crashed"):
        fails.append("crashed clients: {}".format(s["clients"]["crashed"]))
    if s["clients"].get("spawned") != EDGES + HANDHELDS + GUESTS:
        fails.append("spawned {} clients, want {}".format(s["clients"].get("spawned"), EDGES + HANDHELDS + GUESTS))
    if s["malformed"]:
        fails.append("{} malformed records".format(s["malformed"]))
    unexpected = [x for x in ops if not x["ok"] and not (
        guest(x) and x["op"] == "create" and x["grpc_code"] == "PERMISSION_DENIED")]
    if unexpected:
        fails.append("{} unexpected errors, e.g. {}".format(len(unexpected), unexpected[:3]))
    guest_creates = [x for x in ops if guest(x) and x["op"] == "create"]
    if GUESTS and (not guest_creates or any(x["ok"] for x in guest_creates)):
        fails.append("guest creates: {} made, {} allowed (want >0 made, 0 allowed)".format(
            len(guest_creates), sum(1 for x in guest_creates if x["ok"])))
    edge_ok = sum(1 for x in ops if x["client_kind"] == "edge" and x["op"] == "create" and x["ok"])
    hh_ok = sum(1 for x in ops if x["client_kind"] == "handheld" and x["op"] == "create" and x["ok"])
    readings = pg_count(dsn, "SELECT COUNT(*) FROM reading_table WHERE device_id <> 'stream'")
    notes = pg_count(dsn, "SELECT COUNT(*) FROM field_note_table")
    if readings != edge_ok:
        fails.append("rows lost: {} reading rows, {} successful edge creates".format(readings, edge_ok))
    if notes != hh_ok:
        fails.append("rows lost: {} field_note rows, {} successful handheld creates".format(notes, hh_ok))
    starving = [i for i in ("ld-h{:03d}".format(k) for k in range(HANDHELDS))
                if s["subscribers"].get(i, {}).get("samples", 0) == 0]
    if starving:
        fails.append("handhelds that received no samples: {}".format(starving))

    print("gate: {} ops ({} ok edge creates = {} rows, {} ok handheld creates = {} rows), "
          "{} guest denials".format(len(ops), edge_ok, readings, hh_ok, notes, len(guest_creates)))
    for f_ in fails:
        print("gate: FAIL " + f_)
    print("gate: {}  (details: {})".format("FAIL" if fails else "PASS", os.path.join(out, "summary.md")))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
