"""python-target / py-tests tasks 1-2: the generated Python suite
(``PyTestAdapter`` → ``<dest>/python/tests/test_<name>_<hash>.py`` per table
message + ``test_app_<hash>.py`` + ``harpia_runtime.testing``).

- structural: one test module per table-bearing message (= the C++
  ``tests/<name>_<hash>_test.cpp`` set), each with the six checks, a
  ``conftest.py``, and ``pytest`` as the ``test`` extra in ``pyproject.toml``
  [pure Python];
- task 2: access rights / modifiers, REST and SOAP bodies per message --
  flat or RBAC exactly as ``Database.auth_gate.effective_rbac`` decides --
  plus the app-level module on ``TestAdapter._pick_rep``'s message;
- the emitted suite passes when run with pytest in its own project, every
  test collected (nothing silently skipped), under the repo's hardened
  profile **and** a low-risk one (flat gates) [image-gated];
- ``sample()`` really fills every column (no default left in a scalar,
  repeated, map or composed field) and variants a / b differ.

The golden snapshot of the emitted tests is part of ``test_golden_python``.
"""
import importlib
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
CHECKS = ("test_field_access", "test_json_round_trip", "test_xml_round_trip",
          "test_yaml_round_trip", "test_to_string", "test_crudl_round_trip",
          "test_access_modifiers", "test_access_rights", "test_rest_api", "test_soap_api")
APP_CHECKS = ("test_slower", "test_non_parseable", "test_crash", "test_all_good")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_gen_tests"))


@pytest.fixture(scope="module")
def low(tmp_path_factory):
    from UnitTests.test_py_rest import generate_low_risk
    tmp = tmp_path_factory.mktemp("py_gen_tests_low")
    os.makedirs(os.path.join(str(tmp), "out"))
    return generate_low_risk(tmp)


def _tests_dir(gen):
    return os.path.join(P.py_root(gen), "tests")


def test_one_module_per_table_message(gen):
    cpp = {f[:-len("_test.cpp")] for f in os.listdir(os.path.join(gen, "tests"))
           if f.endswith("_test.cpp") and not f.startswith("app_")}
    py = {f[len("test_"):-len(".py")] for f in os.listdir(_tests_dir(gen))
          if f.startswith("test_") and f.endswith(".py") and not f.startswith("test_app_")}
    assert py == cpp and cpp
    for stem in py:
        body = open(os.path.join(_tests_dir(gen), "test_%s.py" % stem)).read()
        assert re.findall(r"^def (test_\w+)\(", body, re.M) == list(CHECKS), stem
    app = open(os.path.join(_tests_dir(gen), "test_app_%s.py" % HASH)).read()
    assert re.findall(r"^def (test_\w+)\(", app, re.M) == list(APP_CHECKS)
    assert os.path.exists(os.path.join(_tests_dir(gen), "conftest.py"))
    pyproject = open(os.path.join(P.py_root(gen), "pyproject.toml")).read()
    assert 'test = ["pytest>=7"]' in pyproject and 'testpaths = ["tests"]' in pyproject


def test_gate_variant_follows_effective_rbac(gen, low):
    for g, rbac_set in ((gen, None), (low, {"vault"})):
        for f in os.listdir(_tests_dir(g)):
            if not f.startswith("test_") or f.startswith("test_app_"):
                continue
            name = f[len("test_"):-len("_%s.py" % HASH)]
            rbac = "from harpia_runtime.rbac import" in open(os.path.join(_tests_dir(g), f)).read()
            want = (name != "reception_desk") if rbac_set is None else (name in rbac_set)
            assert rbac == want, (g, name)


@pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)
@pytest.mark.parametrize("profile", ["hardened", "low_risk"])
def test_emitted_suite_passes(profile, gen, low):
    root = P.py_root(gen if profile == "hardened" else low)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-p", "no:warnings", "-rs"], cwd=root,
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-5000:] + r.stderr[-2000:]
    tests = os.path.join(root, "tests")
    n_modules = len([f for f in os.listdir(tests)
                     if f.startswith("test_") and not f.startswith("test_app_")])
    want = n_modules * len(CHECKS) + len(APP_CHECKS)
    assert re.search(r"\b%d passed\b" % want, r.stdout), r.stdout[-500:]
    assert "skipped" not in r.stdout


@pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)
def test_sample_fills_every_field(gen):
    P.fixture_messages(P.py_root(gen))
    P.activate(P.py_root(gen))
    testing = importlib.import_module("harpia_runtime.testing")
    for name in ("users", "data", "shipment", "telemetry", "top_users", "journey"):
        cls = getattr(importlib.import_module(
            "harpia_generated.protofiles.%s_%s_pb2" % (name, HASH)), name)
        a, b = testing.sample(cls, "a"), testing.sample(cls, "b")
        for f in cls.DESCRIPTOR.fields:
            value = getattr(a, f.name)
            if f.label == f.LABEL_REPEATED:
                assert len(value) == 2, (name, f.name)
            elif f.message_type is not None:
                assert a.HasField(f.name), (name, f.name)
            else:
                assert value != f.default_value or f.name.startswith("ID_"), (name, f.name)
        assert a != b
