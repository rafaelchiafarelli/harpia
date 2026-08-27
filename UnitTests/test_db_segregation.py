"""Track K / Session K.1 -- public/private DB segregation.

The generator emits one project-wide header,
``generated/cpp/db/harpia_db_registry.h`` (``DbRegistryAdapter``): the
environment-level registry of every table this project owns, each tagged
PUBLIC or PRIVATE (the message's trailing ``;`` -> ``visibility``), stamped
with the owning project name (``project.harpia.yaml`` -> ``project:``), plus a
``db_access_check(requesting_project, target_table)`` that denies a PRIVATE
table to any other project while leaving a PUBLIC one reachable.

- Structural (pure Python, always run): the header is emitted, lists exactly
  the table-bearing messages with the right visibility, stamps the project
  name, and re-keys every owner when the project name changes.
- Unit (g++-gated): the access check compiles and decides correctly --
  PRIVATE denied cross-project, allowed same-project, PUBLIC always allowed,
  unknown table denied.
- Integration (g++-gated): a second, separately generated project reads the
  first's registry and is refused its PRIVATE table but served its PUBLIC one
  -- while its own registry is a distinct artifact keyed to its own name.

Acceptance gate (existing single-project tests unaffected) is covered by the
rest of the suite: this adapter is purely additive -- no per-message
SQL/DAO/proto output changes -- and the golden snapshot only gains the one
new file.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
REGISTRY_REL = os.path.join("generated", "cpp", "db", "harpia_db_registry.h")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _run_pipeline(out_dir, project=None):
    """Run the full pipeline into ``out_dir``; return ``(build_dir, dump_dir)``
    where ``build_dir`` holds the generated tree and ``dump_dir`` holds the
    snapshot artifacts (``messages.txt`` etc.)."""
    env = dict(os.environ)
    if project is not None:
        cfg = os.path.join(out_dir, "project.harpia.yaml")
        os.makedirs(out_dir, exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("project: {}\n".format(project))
        env["HARPIA_COMPLIANCE_CONFIG"] = cfg
    dump = os.path.join(out_dir, "dump")
    r = subprocess.run([sys.executable, RUNNER, dump],
                       cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(dump, "build"), dump


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


_ENTRY_RE = re.compile(
    r'RegistryEntry\{"(?P<table>[^"]+)",\s*'
    r'harpia::db::Visibility::(?P<vis>PUBLIC|PRIVATE),\s*'
    r'"(?P<owner>[^"]+)"\}')


def _parse_registry(header_text):
    project = re.search(r'kProjectName\s*=\s*"([^"]+)"', header_text).group(1)
    entries = {m.group("table"): (m.group("vis"), m.group("owner"))
               for m in _ENTRY_RE.finditer(header_text)}
    return project, entries


_MSG_RE = re.compile(
    r'name:(?P<name>\S+) variables:.* tableName:(?P<table>\S*) '
    r'visibility:(?P<vis>PUBLIC|PRIVATE)')


def _expected_tables(dump_dir):
    """``{tableName: {VISIBILITY, ...}}`` for every table-bearing message,
    parsed off the ``messages.txt`` the harness already dumps -- so the test
    tracks the shared fixture without re-implementing the front-end."""
    out = {}
    with open(os.path.join(dump_dir, "messages.txt"), encoding="utf-8") as f:
        for line in f:
            m = _MSG_RE.search(line)
            if not m or not m.group("table"):
                continue
            out.setdefault(m.group("table"), set()).add(m.group("vis"))
    return out


# --------------------------------------------------------------------------
# structural -- pure Python, always run
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def default_run(tmp_path_factory):
    build, dump = _run_pipeline(str(tmp_path_factory.mktemp("seg_default")))
    text = _read(os.path.join(build, REGISTRY_REL))
    return text, dump


def test_registry_header_is_emitted(default_run):
    text, _ = default_run
    assert "#ifndef HARPIA_DB_REGISTRY_H" in text
    assert "namespace harpia {" in text and "namespace db {" in text
    assert "AccessDecision db_access_check(" in text


def test_registry_lists_every_table_with_its_visibility(default_run):
    text, dump = default_run
    _, entries = _parse_registry(text)
    declared = _expected_tables(dump)

    # every distinct table name in the schema is registered exactly once
    assert set(entries) == set(declared)

    # each with a visibility some message actually declared for that table
    for tbl, (vis, _owner) in entries.items():
        assert vis in declared[tbl], (tbl, vis, declared[tbl])

    # both kinds present, so the deny/allow split is actually exercised
    assert {vis for vis, _ in entries.values()} == {"PUBLIC", "PRIVATE"}


def test_enums_and_tableless_messages_are_absent(default_run):
    text, _ = default_run
    _, entries = _parse_registry(text)
    # enums / table-less composed messages from the fixture
    for absent in ("grow", "grower", "baba", "prince", "queen", "waypoint"):
        assert absent not in entries


def test_project_name_defaults_and_stamps_every_owner(default_run):
    text, _ = default_run
    project, entries = _parse_registry(text)
    assert project == "default"
    assert entries, "registry has no entries"
    assert {owner for _v, owner in entries.values()} == {"default"}


def test_custom_project_name_rekeys_the_whole_registry(tmp_path):
    build, _ = _run_pipeline(str(tmp_path), project="cardio-cloud")
    project, entries = _parse_registry(_read(os.path.join(build, REGISTRY_REL)))
    assert project == "cardio-cloud"
    assert {owner for _v, owner in entries.values()} == {"cardio-cloud"}


def test_same_name_visibility_conflict_is_surfaced_not_hidden(default_run):
    text, _ = default_run
    # users (PUBLIC) and top_users (PRIVATE) both map to user_table in the
    # fixture -- the first declaration wins and the loser is called out.
    assert 'note: table "user_table" is also declared' in text
    _, entries = _parse_registry(text)
    assert entries["user_table"][0] == "PUBLIC"


# --------------------------------------------------------------------------
# unit + integration -- need a C++ compiler
# --------------------------------------------------------------------------
_needs_gpp = pytest.mark.skipif(
    shutil.which("g++") is None,
    reason="access-check compile test needs g++ (harpia Docker image)")

_CXXFLAGS = ["-std=c++17", "-Wall", "-Wextra", "-Werror"]


def _compile_run(tmp_path, header_dir, src):
    src_path = tmp_path / "main.cpp"
    src_path.write_text(src)
    exe = str(tmp_path / "a.out")
    c = subprocess.run(["g++", *_CXXFLAGS, "-I", header_dir, str(src_path),
                        "-o", exe], capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, c.stderr
    r = subprocess.run([exe], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


@_needs_gpp
def test_access_check_decides_correctly(tmp_path):
    build, _ = _run_pipeline(str(tmp_path / "gen"), project="clinic")
    header_dir = os.path.join(build, "generated", "cpp")
    src = r'''
#include "db/harpia_db_registry.h"
#include <cassert>
#include <iostream>
using namespace harpia::db;
int main() {
    // PUBLIC table: reachable from any project, and from the owner
    assert(db_access_check("stranger", "user_table") == AccessDecision::ALLOWED);
    assert(db_access_check("clinic",   "user_table") == AccessDecision::ALLOWED);
    // PRIVATE table: owner yes, everyone else no
    assert(db_access_check("clinic",   "patient_vitals_table") == AccessDecision::ALLOWED);
    assert(db_access_check("stranger", "patient_vitals_table") == AccessDecision::DENIED_PRIVATE_CROSS_PROJECT);
    // unknown table: denied, distinctly
    assert(db_access_check("clinic",   "no_such_table") == AccessDecision::DENIED_UNKNOWN_TABLE);
    // this-build convenience overload uses kProjectName ("clinic")
    assert(db_access_check("patient_vitals_table") == AccessDecision::ALLOWED);
    // decidable at compile time
    static_assert(db_access_check("x", "user_table") == AccessDecision::ALLOWED, "");
    static_assert(db_access_check("x", "patient_vitals_table") == AccessDecision::DENIED_PRIVATE_CROSS_PROJECT, "");
    std::cout << "ok\n";
}
'''
    assert _compile_run(tmp_path, header_dir, src).strip() == "ok"


@_needs_gpp
def test_two_projects_cross_access(tmp_path):
    # Project A ("clinic") owns the tables; project B ("billing") is a
    # separate generation with its own registry.
    a_build, _ = _run_pipeline(str(tmp_path / "clinic"), project="clinic")
    b_build, _ = _run_pipeline(str(tmp_path / "billing"), project="billing")

    a_project, a_entries = _parse_registry(_read(os.path.join(a_build, REGISTRY_REL)))
    b_project, b_entries = _parse_registry(_read(os.path.join(b_build, REGISTRY_REL)))
    assert (a_project, b_project) == ("clinic", "billing")
    # genuinely distinct artifacts: same tables, different stamped owner
    assert set(a_entries) == set(b_entries)
    assert {o for _v, o in a_entries.values()} == {"clinic"}
    assert {o for _v, o in b_entries.values()} == {"billing"}

    # Billing code consults clinic's registry, passing its own project name.
    header_dir = os.path.join(a_build, "generated", "cpp")
    src = r'''
#include "db/harpia_db_registry.h"      // clinic's registry
#include <cassert>
#include <iostream>
using namespace harpia::db;
int main() {
    const char* me = "billing";         // a different project
    assert(db_access_check(me, "user_table") == AccessDecision::ALLOWED);                       // PUBLIC: served
    assert(db_access_check(me, "patient_vitals_table") == AccessDecision::DENIED_PRIVATE_CROSS_PROJECT); // PRIVATE: refused
    assert(db_access_check("clinic", "patient_vitals_table") == AccessDecision::ALLOWED);       // owner still in
    std::cout << "ok\n";
}
'''
    assert _compile_run(tmp_path, header_dir, src).strip() == "ok"
