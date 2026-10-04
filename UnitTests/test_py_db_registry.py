"""The Python public/private DB registry (python-target / py-database task 4):
the generated, stdlib-only ``harpia_generated/db/registry.py``.

Pure Python (runs main.py, imports the module by path): the entries and the
``users``/``top_users`` conflict note match the C++ header; every decision
branch (unknown table, PUBLIC from anywhere, PRIVATE for the owner, PRIVATE
cross-project) and the one-argument form; ``PROJECT_NAME`` follows
``project.harpia.yaml``; a second project ("billing") loads the first
("clinic") project's module and is served its PUBLIC table but refused its
PRIVATE one.

g++: the decisions equal the C++ ``db_access_check`` for every fixture table
and two requesting projects.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate  # noqa: E402


def _gen(tmp, project=None):
    old = os.environ.get("HARPIA_COMPLIANCE_CONFIG")
    if project is not None:
        os.makedirs(tmp, exist_ok=True)
        cfg = os.path.join(tmp, "project.harpia.yaml")
        with open(cfg, "w") as f:
            f.write("project: {}\n".format(project))
        os.environ["HARPIA_COMPLIANCE_CONFIG"] = cfg
    try:
        return generate(os.path.join(tmp, "out"), lang="python")
    finally:
        if project is not None:
            if old is None:
                os.environ.pop("HARPIA_COMPLIANCE_CONFIG", None)
            else:
                os.environ["HARPIA_COMPLIANCE_CONFIG"] = old


def _load(gen, alias):
    path = os.path.join(gen, "python", "harpia_generated", "db", "registry.py")
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def default_gen(tmp_path_factory):
    return _gen(str(tmp_path_factory.mktemp("reg_default")))


@pytest.fixture(scope="module")
def reg(default_gen):
    return _load(default_gen, "registry_default")


def _cpp_entries(gen):
    text = open(os.path.join(gen, "generated", "cpp", "db", "harpia_db_registry.h")).read()
    return re.findall(r'RegistryEntry\{"([^"]+)", harpia::db::Visibility::(\w+), "([^"]+)"\}',
                      text), re.findall(r'// note: table "([^"]+)"', text)


def test_entries_and_notes_match_cpp(default_gen, reg):
    entries, notes = _cpp_entries(default_gen)
    assert [(e.table, e.visibility.value, e.owner_project) for e in reg.REGISTRY] == entries
    text = open(reg.__file__).read()
    for table in notes:
        assert "# note: table {!r}".format(table) in text
    assert notes == ["user_table"]


def test_decision_branches(reg):
    A = reg.AccessDecision
    public = next(e.table for e in reg.REGISTRY if e.visibility is reg.Visibility.PUBLIC)
    private = next(e.table for e in reg.REGISTRY if e.visibility is reg.Visibility.PRIVATE)
    assert reg.PROJECT_NAME == "default"
    assert reg.db_access_check("anyone", "no_such_table") is A.DENIED_UNKNOWN_TABLE
    assert reg.db_access_check("anyone", public) is A.ALLOWED
    assert reg.db_access_check("default", private) is A.ALLOWED
    assert reg.db_access_check("billing", private) is A.DENIED_PRIVATE_CROSS_PROJECT
    # one-argument form: the requesting project is PROJECT_NAME
    assert reg.db_access_check(private) is A.ALLOWED
    assert reg.db_access_check("no_such_table") is A.DENIED_UNKNOWN_TABLE
    assert reg.find_entry("no_such_table") is None


def test_second_project_imports_the_first(tmp_path):
    clinic = _load(_gen(str(tmp_path / "clinic"), project="clinic"), "registry_clinic")
    billing = _load(_gen(str(tmp_path / "billing"), project="billing"), "registry_billing")
    assert clinic.PROJECT_NAME == "clinic" and billing.PROJECT_NAME == "billing"
    assert {e.owner_project for e in clinic.REGISTRY} == {"clinic"}
    A = clinic.AccessDecision
    public = next(e.table for e in clinic.REGISTRY if e.visibility.value == "PUBLIC")
    private = next(e.table for e in clinic.REGISTRY if e.visibility.value == "PRIVATE")
    # billing's code asks clinic's registry about clinic's tables
    assert clinic.db_access_check(billing.PROJECT_NAME, public) is A.ALLOWED
    assert clinic.db_access_check(billing.PROJECT_NAME, private) is A.DENIED_PRIVATE_CROSS_PROJECT
    assert clinic.db_access_check(private) is A.ALLOWED


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_decisions_match_cpp(default_gen, reg, tmp_path):
    tables = [e.table for e in reg.REGISTRY] + ["no_such_table"]
    projects = ["default", "billing"]
    prog = tmp_path / "reg.cpp"
    calls = "".join(
        '    std::printf("%d\\n", static_cast<int>(harpia::db::db_access_check("{}", "{}")));\n'
        .format(p, t) for p in projects for t in tables)
    prog.write_text('#include <cstdio>\n#include "db/harpia_db_registry.h"\n'
                    "int main() {\n" + calls + "    return 0;\n}\n")
    exe = tmp_path / "reg"
    c = subprocess.run(["g++", "-std=c++17", "-I",
                        os.path.join(default_gen, "generated", "cpp"), str(prog), "-o", str(exe)],
                       capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, c.stderr
    cpp = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30).stdout.split()
    order = list(reg.AccessDecision)  # same declaration order as the C++ enum
    py = [str(order.index(reg.db_access_check(p, t))) for p in projects for t in tables]
    assert py == cpp
