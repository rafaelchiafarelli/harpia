"""multi-system-reference / reference-system task 6 -- the end-to-end gate for
the reference system (`HarpiaTest/app_example/multi_system/`): three programs
generated from one `.harpia`, hardened on every link, all running at once.

Default suite (SQLite station; PostgreSQL with HARPIA_PG_DSN via
Docker/run_pg_tests.sh):
  * `station` + `edge` + two `handheld` CLIs (handheld, handheld2) run together;
    every flow moves: edge -> station readings (gRPC), edge -> handhelds live
    samples (CURVE ZMQ), handhelds -> station field notes (gRPC), station ->
    handhelds readings (gRPC), station -> edge field notes (gRPC);
  * negatives in the same run: a `guest` handheld receives the stream but is
    denied every field-note create (RBAC), and `stranger` -- a valid gRPC
    identity whose CURVE key is not in edge's allowlist -- receives nothing.

Emulator entry (`Docker/run_android_emulator_tests.sh multi_system`, which
sets HARPIA_MS_EMULATOR=1 once an emulator is up): the real Android app takes
one handheld's place, reaching station and edge as 10.0.2.2 -- the address
the dev PKI's `--san` puts in station's certificate, so no authority override
is needed. Its counters are read back from logcat.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    CPP_SKIP, HAVE_CPP, HAVE_JAVA, JAVA_SKIP, build_cpp, build_handheld, free_port,
    generate, provision, read, running, station_cmd)

pytestmark = [pytest.mark.skipif(not HAVE_CPP, reason=CPP_SKIP),
              pytest.mark.skipif(not HAVE_JAVA, reason=JAVA_SKIP)]

PG_DSN = os.environ.get("HARPIA_PG_DSN")
EMULATOR = os.environ.get("HARPIA_MS_EMULATOR") == "1"
BACKENDS = ["sqlite"] + (["postgresql"] if PG_DSN else [])


def _counters(text):
    done = [ln for ln in text.splitlines() if ln.startswith("handheld: done ")]
    assert done, text
    return {k: int(v) for k, v in (kv.split("=") for kv in done[-1].split() if "=" in kv)}


def _system(tmp, backend):
    gen = generate(tmp / "gen", db_backend=None if backend == "sqlite" else backend)
    pki = provision(tmp / "pki", extra_clients=("handheld2 main", "stranger main"),
                    sans=("10.0.2.2",))
    allow = os.path.join(pki["zmq"], "allowlist.txt")
    with open(allow) as f:
        rows = [r for r in f.read().splitlines() if not r.endswith(" stranger")]
    with open(allow, "w") as f:
        f.write("\n".join(rows) + "\n")
    return {"gen": gen, "pki": pki,
            "station": build_cpp("station", gen, str(tmp / "b_station")),
            "edge": build_cpp("edge", gen, str(tmp / "b_edge")),
            "cli": build_handheld(gen, tmp),
            "handheld_dir": os.path.join(str(tmp), "handheld")}   # build_handheld's copy


@pytest.fixture(scope="module", params=BACKENDS)
def system(request, tmp_path_factory):
    return dict(_system(tmp_path_factory.mktemp("ms_e2e_" + request.param), request.param),
                backend=request.param)


def _station_db(system, tmp_path):
    return ("sqlite:" + str(tmp_path / "station.db")) if system["backend"] == "sqlite" else PG_DSN


def _handheld(system, sport, endpoint, who, id_base, duration):
    pki, zk = system["pki"]["pki"], system["pki"]["zmq"]
    return subprocess.Popen(
        [system["cli"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
         "--certs", pki, "--identity", who, "--sub", endpoint, "--zmq-keys", zk,
         "--notes-every", "5", "--list-every", "1000", "--id-base", str(id_base),
         "--duration", str(duration)],
        env=system["pki"]["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_all_flows_and_negatives(system, tmp_path):
    s = system
    pki, zk, env = s["pki"]["pki"], s["pki"]["zmq"], s["pki"]["env"]
    sport, pport = free_port(), free_port()
    endpoint = "tcp://127.0.0.1:{}".format(pport)
    with running(station_cmd(s["station"], sport, _station_db(s, tmp_path), pki, pool=8), env,
                 str(tmp_path / "station.log"), ready_port=sport) as station:
        with running([s["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                      "--certs", pki, "--identity", "edge", "--pub", endpoint, "--zmq-keys", zk,
                      "--interval", "100", "--notes-every", "10", "--id-base", "1",
                      "--duration", "30"],
                     env, str(tmp_path / "edge.log")) as edge:
            hh = {who: _handheld(s, sport, endpoint, who, base, 8) for who, base in (
                ("handheld", 500000), ("handheld2", 600000),
                ("guest", 700000), ("stranger", 800000))}
            out = {who: p.communicate(timeout=240)[0] for who, p in hh.items()}
    station_log, edge_log = read(station.log_path), read(edge.log_path)
    for who, p in hh.items():
        assert p.returncode == 0, "{}:\n{}".format(who, out[who])

    # every flow moves for both real handhelds
    for who in ("handheld", "handheld2"):
        k = _counters(out[who])
        assert k["samples"] >= 10, out[who]             # edge -> handheld (ZMQ)
        assert k["notes"] >= 2, out[who]                # handheld -> station (gRPC)
        assert k["readings_listed"] >= 1, out[who]      # station -> handheld (gRPC)
        assert k["errors"] == 0, out[who]
    assert "readings_failed=0" in edge_log, edge_log
    seen = [int(ln.rsplit(" ", 1)[1]) for ln in edge_log.splitlines()
            if ln.startswith("edge: field_notes on station: ")]
    assert seen and max(seen) >= 1, edge_log            # station -> edge (gRPC)
    assert "station: last 2s calls=" in station_log

    # negatives: guest gets the stream but every create is denied ...
    g = _counters(out["guest"])
    assert g["samples"] >= 5 and g["notes"] == 0 and g["errors"] >= 1, out["guest"]
    assert "PERMISSION_DENIED" in out["guest"] or "forbidden" in out["guest"], out["guest"]
    # ... and a key edge doesn't allowlist receives nothing at all
    st = _counters(out["stranger"])
    assert st["samples"] == 0 and st["notes"] == 0, out["stranger"]

    if s["backend"] == "sqlite":
        with sqlite3.connect(str(tmp_path / "station.db")) as c:
            authors = dict(c.execute("SELECT author, COUNT(*) FROM field_note_table GROUP BY author"))
        assert authors == {"handheld": _counters(out["handheld"])["notes"],
                           "handheld2": _counters(out["handheld2"])["notes"]}


# --------------------------------------------------------------------------
# emulator entry: the real Android app in place of one handheld
# --------------------------------------------------------------------------

def _adb(*args, check=True, timeout=120):
    r = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if check:
        assert r.returncode == 0, "adb {}: {}".format(" ".join(args), r.stdout + r.stderr)
    return r.stdout


@pytest.mark.skipif(not EMULATOR or shutil.which("adb") is None,
                    reason="emulator entry: Docker/run_android_emulator_tests.sh multi_system")
def test_android_app_on_emulator(tmp_path_factory, tmp_path):
    s = _system(tmp_path_factory.mktemp("ms_emu"), "sqlite")
    pki, zk, env = s["pki"]["pki"], s["pki"]["zmq"], s["pki"]["env"]
    sport, pport = free_port(), free_port()

    # the app's assets: the handheld identity + where station/edge are, as the
    # emulator sees them (10.0.2.2 = this container's loopback; it is in the
    # server cert's SAN, so no authority override)
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("ca.pem", "client_handheld.pem", "client_handheld_key.pem"):
        shutil.copy(os.path.join(pki, name), assets / name)
    for name in ("zmq_server_public.key", "zmq_handheld_public.key", "zmq_handheld_secret.key"):
        shutil.copy(os.path.join(zk, name), assets / name)
    (assets / "handheld.properties").write_text(
        "station.host=10.0.2.2\nstation.port={}\nsub.endpoint=tcp://10.0.2.2:{}\n"
        "id.base=900000\nnotes.every=5\n".format(sport, pport), encoding="ascii")
    work = s["handheld_dir"]
    r = subprocess.run(["gradle", "-q", ":app:assembleDebug", "-PwithAndroid",
                        "-PharpiaGenDir=" + s["gen"], "-PharpiaPkiDir=" + str(assets)],
                       cwd=work, capture_output=True, text=True, timeout=2400)
    assert r.returncode == 0, (r.stdout + r.stderr)[-5000:]
    apk = os.path.join(work, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    _adb("install", "-r", "-t", apk, timeout=300)
    pkg = "com.harpia.multisystem.handheld.app"

    db = str(tmp_path / "station.db")
    with running(station_cmd(s["station"], sport, "sqlite:" + db, pki), env,
                 str(tmp_path / "station.log"), ready_port=sport):
        with running([s["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                      "--certs", pki, "--identity", "edge", "--pub", "tcp://0.0.0.0:{}".format(pport),
                      "--zmq-keys", zk, "--interval", "100", "--notes-every", "10",
                      "--id-base", "1", "--duration", "120"],
                     env, str(tmp_path / "edge.log")):
            time.sleep(0.5)
            _adb("logcat", "-c")
            _adb("shell", "am", "start", "-n", pkg + "/.MainActivity")
            pat = re.compile(r"handheld: samples=(\d+) notes=(\d+) readings_listed=(\d+) "
                             r"list_calls=\d+ errors=(\d+)")
            best = None
            end = time.monotonic() + 90
            while time.monotonic() < end:
                log = _adb("logcat", "-d", "-s", "harpia-handheld:I", check=False)
                hits = pat.findall(log)
                if hits:
                    best = tuple(int(x) for x in hits[-1])
                    if best[0] >= 10 and best[1] >= 2 and best[2] >= 1:
                        break
                time.sleep(2)
            _adb("shell", "am", "force-stop", pkg, check=False)
    assert best is not None, _adb("logcat", "-d", check=False)[-5000:]
    samples, notes, listed, errors = best
    assert samples >= 10 and notes >= 2 and listed >= 1, best
    assert errors == 0, _adb("logcat", "-d", "-s", "harpia-handheld", check=False)[-3000:]
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM field_note_table WHERE author='handheld-android'"
                         ).fetchone()[0] >= 2
