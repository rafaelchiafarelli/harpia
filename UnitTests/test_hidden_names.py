"""stable-hidden-names-DEFECT task 1: the front-end-injected fields are
``HARPIA_ID`` / ``HARPIA_STATUS`` / ``HARPIA_ERROR`` / ``HARPIA_ORIGINATOR``,
independent of the root file's text.

The same Include module is generated under two roots that differ only by an
extra ``import`` line (so their md5 differs); the shared message's ``.proto``
field names and SQL column names must be identical. A user field whose name
collides with a hidden one (protoc's JSON-name rule), or takes the reserved
``HARPIA_`` prefix that every hidden-field recogniser keys off, is a
front-end error.

Pure Python (runs main.py / run_frontend.py in subprocesses).
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

MOD = ("message p_rec {\n    required unique string id;\n    optional string note;\n} p_table;\n\n"
       "pull message p_feed {\n    required string text;\n} p_feed_table;\n")
OTHER = "message q_rec {\n    required string label;\n} q_table;\n"
HIDDEN = {"HARPIA_ID", "HARPIA_STATUS", "HARPIA_ERROR", "HARPIA_ORIGINATOR"}


def _generate(root, inc, out):
    env = dict(os.environ, HARPIA_OUTPUT_DIR=str(out), HARPIA_INPUT_FILE=str(root),
               HARPIA_INCLUDE_FOLDER=str(inc))
    env.pop("HARPIA_GEN_LANG", None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]


def _names(out, root, msg):
    h = hashlib.md5(open(root, "rb").read()).hexdigest()
    proto = open(os.path.join(out, "proto", "protofiles", "%s_%s.proto" % (msg, h))).read()
    body = proto[proto.index("message %s" % msg):]
    fields = re.findall(r"^\s*(?:optional\s+|repeated\s+)?[\w.<>, ]+?\s+(\w+)\s*=\s*\d+\s*;",
                        body, re.M)
    sql = open(os.path.join(out, "database", "%s_%s_table.sql" % (msg, h))).read()
    cols = re.findall(r'^\s*"?(\w+)"?\s+(?:INTEGER|TEXT|REAL|BIGINT|DOUBLE)', sql, re.M)
    return fields, cols


@pytest.fixture(scope="module")
def gens(tmp_path_factory):
    d = tmp_path_factory.mktemp("hidden")
    inc = d / "Include"
    inc.mkdir()
    (inc / "mod.harpia").write_text(MOD)
    (inc / "other.harpia").write_text(OTHER)
    r1, r2 = d / "root1.harpia", d / "root2.harpia"
    r1.write_text('import "mod.harpia";\n')
    r2.write_text('import "mod.harpia";\nimport "other.harpia";\n')
    _generate(r1, inc, d / "g1")
    _generate(r2, inc, d / "g2")
    return [(str(d / "g1"), str(r1)), (str(d / "g2"), str(r2))]


@pytest.mark.parametrize("msg", ["p_rec", "p_feed"])
def test_hidden_names_independent_of_root_hash(gens, msg):
    (g1, r1), (g2, r2) = gens
    f1, c1 = _names(g1, r1, msg)
    f2, c2 = _names(g2, r2, msg)
    assert f1 == f2
    assert c1 == c2
    assert HIDDEN <= set(f1)
    assert "HARPIA_ID" in c1
    assert not any(re.search(r"_[0-9a-f]{32}$", n) for n in f1 + c1)


@pytest.mark.parametrize("field", ["harpia_id", "HARPIA_STATUS", "harpiaerror", "harpia_originator",
                                   "Harpia_note"])
def test_user_field_colliding_with_hidden_name_is_refused(tmp_path, field):
    f = tmp_path / "bad.harpia"
    f.write_text("message bad {\n    required string %s;\n} bad_table;\n" % field)
    r = subprocess.run([sys.executable, os.path.join(HERE, "run_frontend.py"), str(f),
                        str(tmp_path / "out")], cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=120)
    assert "RESULT MSG RESERVED_HIDDEN_FIELD_NAME" in r.stdout, r.stdout[-2000:]
