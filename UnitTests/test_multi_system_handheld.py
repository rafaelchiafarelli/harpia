"""multi-system-reference / reference-system task 5 -- `handheld`
(`HarpiaTest/app_example/multi_system/handheld/`): a plain-Java core, a JVM
CLI over it, and a thin Android app over it.

  * the CLI runs against `station` (SQLite) + `edge` for ~6 s and every
    direction moves: samples received from edge (CURVE ZMQ, allowlisted
    key), field notes written to station (gRPC, mTLS + session; edge then
    sees them), readings listed from station;
  * `core` uses no Android API (checked: no `android.` import);
  * the Android app module assembles into an APK (`-PwithAndroid`), with the
    Android SDK baked into the harpia image. The on-device run is task 6's
    emulator entry.
"""
import glob
import os
import sqlite3
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import (  # noqa: E402
    CPP_SKIP, HAVE_CPP, HAVE_JAVA, JAVA_SKIP, MS, build_cpp, build_handheld, free_port,
    generate, provision, read, running, station_cmd)

pytestmark = [pytest.mark.skipif(not HAVE_CPP, reason=CPP_SKIP),
              pytest.mark.skipif(not HAVE_JAVA, reason=JAVA_SKIP)]


def _counters(line):
    return dict(kv.split("=") for kv in line.split() if "=" in kv)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ms_handheld")
    gen = generate(tmp / "gen")
    return {"tmp": tmp, "gen": gen,
            "station": build_cpp("station", gen, str(tmp / "b_station")),
            "edge": build_cpp("edge", gen, str(tmp / "b_edge")),
            "cli": build_handheld(gen, tmp),
            "pki": provision(tmp / "pki")}


def test_core_has_no_android_api():
    for path in glob.glob(os.path.join(MS, "handheld", "core", "src", "**", "*.java"), recursive=True):
        with open(path) as f:
            assert "import android." not in f.read(), path


def test_cli_moves_data_in_all_three_directions(built, tmp_path):
    b = built
    pki, zk, env = b["pki"]["pki"], b["pki"]["zmq"], b["pki"]["env"]
    sport, pport = free_port(), free_port()
    db = str(tmp_path / "station.db")
    endpoint = "tcp://127.0.0.1:{}".format(pport)
    with running(station_cmd(b["station"], sport, "sqlite:" + db, pki), env,
                 str(tmp_path / "station.log"), ready_port=sport):
        with running([b["edge"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                      "--certs", pki, "--identity", "edge", "--pub", endpoint, "--zmq-keys", zk,
                      "--interval", "100", "--notes-every", "10", "--id-base", "1",
                      "--duration", "20"],
                     env, str(tmp_path / "edge.log")) as edge:
            r = subprocess.run(
                [b["cli"], "--station", "127.0.0.1:{}".format(sport), "--authority", "localhost",
                 "--certs", pki, "--identity", "handheld", "--sub", endpoint, "--zmq-keys", zk,
                 "--notes-every", "5", "--list-every", "1000", "--id-base", "500000",
                 "--duration", "6"],
                env=env, capture_output=True, text=True, timeout=180)
            edge_log = edge.log_path
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    done = [ln for ln in out.splitlines() if ln.startswith("handheld: done ")]
    assert done, out
    k = _counters(done[-1])
    assert int(k["samples"]) >= 10, out                 # edge -> handheld (ZMQ)
    assert int(k["notes"]) >= 2, out                    # handheld -> station (gRPC)
    assert int(k["readings_listed"]) >= 1, out          # station -> handheld (gRPC)
    assert int(k["errors"]) == 0, out
    with sqlite3.connect(db) as c:
        notes = c.execute("SELECT COUNT(*), MIN(author) FROM field_note_table").fetchone()
    assert notes == (int(k["notes"]), "handheld")
    # ... and edge, listing field notes from station, saw some of them
    seen = [int(ln.rsplit(" ", 1)[1]) for ln in read(edge_log).splitlines()
            if ln.startswith("edge: field_notes on station: ")]
    assert seen and max(seen) >= 1, read(edge_log)


@pytest.mark.skipif(not os.path.isdir(os.environ.get("ANDROID_HOME", "/nonexistent")),
                    reason="needs the Android SDK (ANDROID_HOME, harpia Docker image)")
def test_android_app_assembles(built):
    b = built
    work = os.path.join(str(b["tmp"]), "handheld")      # build_handheld's copy
    env = dict(os.environ, GRADLE_USER_HOME=os.environ.get("GRADLE_USER_HOME", "/tmp/.gradle"))
    r = subprocess.run(["gradle", "-q", ":app:assembleDebug", "-PwithAndroid",
                        "-PharpiaGenDir=" + b["gen"], "-PharpiaPkiDir=" + b["pki"]["pki"]],
                       cwd=work, env=env, capture_output=True, text=True, timeout=2400)
    assert r.returncode == 0, (r.stdout + r.stderr)[-5000:]
    apks = glob.glob(os.path.join(work, "app", "build", "outputs", "apk", "debug", "*.apk"))
    assert apks, "no APK produced"
