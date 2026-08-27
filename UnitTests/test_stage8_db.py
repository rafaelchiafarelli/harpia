"""Stage 8 (database) tests.

  - the generated SQL schema executes in SQLite (needs g++ to compile the
    vendored sqlite3.c), and
  - the generated CRUDL DAO does a real round-trip against an in-memory database
    (additionally needs protoc for the message C++).

Skipped when the toolchain is absent so the host suite stays green; runs fully in
the Docker image.
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None or shutil.which("cc") is None,
    reason="needs a C/C++ compiler for the vendored sqlite (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def sqlite_obj(tmp_path_factory):
    """Compile the vendored sqlite3.c once (it is C; g++ would reject it)."""
    out = tmp_path_factory.mktemp("sqlite_obj")
    obj = os.path.join(str(out), "sqlite3.o")
    c = subprocess.run(
        ["cc", "-c", "-I", SQLITE, os.path.join(SQLITE, "sqlite3.c"), "-o", obj],
        capture_output=True, text=True, timeout=300,
    )
    assert c.returncode == 0, "sqlite3.c failed to compile:\n" + c.stderr
    return obj


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_db")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build")


def test_generated_schema_is_valid_sqlite(generated, sqlite_obj, tmp_path):
    checker_src = tmp_path / "checker.cpp"
    checker_src.write_text(
        '#include "sqlite3.h"\n#include <fstream>\n#include <sstream>\n'
        '#include <string>\nint main(int c,char**v){if(c<2)return 2;'
        'std::ifstream f(v[1]);std::stringstream s;s<<f.rdbuf();'
        'sqlite3*db=nullptr;if(sqlite3_open(":memory:",&db))return 3;'
        'char*e=nullptr;if(sqlite3_exec(db,s.str().c_str(),0,0,&e)){'
        'fprintf(stderr,"%s\\n",e);return 1;}return 0;}\n')
    checker = str(tmp_path / "checker")
    c = subprocess.run(["g++", "-std=c++17", "-I", SQLITE, str(checker_src),
                        sqlite_obj, "-o", checker, "-lpthread", "-ldl"],
                       capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, c.stderr

    db_dir = os.path.join(generated, "database")
    files = [p for p in sorted(glob.glob(os.path.join(db_dir, "*_table.sql")))
             if "CREATE TABLE" in open(p).read()]
    assert len(files) >= 4
    for path in files:
        r = subprocess.run([checker, path], capture_output=True, text=True,
                           timeout=15)
        assert r.returncode == 0, "invalid schema {}:\n{}".format(
            os.path.basename(path), r.stderr)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="CRUDL round-trip needs protoc + protobuf")
def test_crudl_roundtrip(generated, sqlite_obj, tmp_path):
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "crudl.cpp"
    prog.write_text(
        '#include "db/users_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "#include <vector>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::users_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
        "    if (!dao.create(a)) return 3;\n"
        "    ::users got;\n"
        "    if (!dao.read(1, &got)) return 4;\n"
        '    if (got.name() != "neo" || got.address() != "matrix") return 5;\n'
        "    ::users b = a; b.set_name(\"trinity\");\n"
        "    if (!dao.update(b)) return 6;\n"
        "    ::users got2; dao.read(1, &got2);\n"
        '    if (got2.name() != "trinity") return 7;\n'
        "    ::users a2; a2.set_id_{h}(2); a2.set_name(\"morpheus\");\n"
        "    if (!dao.create(a2)) return 8;\n"
        "    std::vector<::users> all;\n"
        "    if (!dao.list(&all) || all.size() != 2) return 9;\n"
        "    if (!dao.remove(1)) return 10;\n"
        "    ::users gone;\n"
        "    if (dao.read(1, &gone)) return 11;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "crudl")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "CRUDL program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "CRUDL round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="CRUDL pagination needs protoc + protobuf")
def test_crudl_pagination(generated, sqlite_obj, tmp_path):
    """The paginated list(offset, limit) overload returns the right subset in
    insertion order, and an unpaginated list() still returns everything."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "pagination.cpp"
    prog.write_text(
        '#include "db/users_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "#include <vector>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::users_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    for (int i = 1; i <= 5; ++i) {{\n"
        "        ::users u; u.set_id_{h}(i); u.set_name(\"n\" + std::to_string(i));\n"
        "        if (!dao.create(u)) return 3;\n"
        "    }}\n"
        "    std::vector<::users> page;\n"
        "    if (!dao.list(&page, 1, 2) || page.size() != 2) return 4;\n"
        '    if (page[0].name() != "n2" || page[1].name() != "n3") return 5;\n'
        "    std::vector<::users> last;\n"
        "    if (!dao.list(&last, 4, 2) || last.size() != 1) return 6;\n"
        '    if (last[0].name() != "n5") return 7;\n'
        "    std::vector<::users> all;\n"
        "    if (!dao.list(&all) || all.size() != 5) return 8;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "pagination")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "pagination program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "pagination round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration needs protoc + protobuf")
def test_migration_additive(generated, sqlite_obj, tmp_path):
    """migrate_<name> brings an older table (missing columns) up to the current
    schema without losing rows, and stamps the version."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "migrate.cpp"
    prog.write_text(
        '#include "migrate/users_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    auto exec = [&db](const char* s) {{ try {{ db << s; return true; }} catch (...) {{ return false; }} }};\n"
        "    // an older generated version: only the PK + one column, with a row\n"
        '    if (!exec("CREATE TABLE \\"user_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY, \\"address\\" TEXT);")) return 2;\n'
        "    if (!exec(\"INSERT INTO \\\"user_table\\\" (\\\"ID_{h}\\\", \\\"address\\\") VALUES (1, 'matrix');\")) return 3;\n"
        "    if (!::harpia::db::migrate_users(db)) return 4;\n"
        "    ::harpia::db::users_dao dao(db);\n"
        "    // the added columns now exist: a full row round-trips\n"
        '    ::users a; a.set_id_{h}(2); a.set_address("zion"); a.set_name("neo");\n'
        "    if (!dao.create(a)) return 5;\n"
        "    ::users got; if (!dao.read(2, &got)) return 6;\n"
        '    if (got.name() != "neo" || got.address() != "zion") return 7;\n'
        "    // the pre-existing row survived the migration\n"
        "    ::users old; if (!dao.read(1, &old)) return 8;\n"
        '    if (old.address() != "matrix") return 9;\n'
        "    // the version was stamped\n"
        "    std::string v; ::soci::indicator vi;\n"
        '    db << "SELECT \\"version\\" FROM \\"_harpia_schema_version\\" WHERE \\"name\\" = \'user_table\'", ::soci::into(v, vi);\n'
        "    if (!db.got_data() || vi != ::soci::i_ok) return 11;\n"
        '    if (v != "{h}") return 12;\n'
        "    if (!::harpia::db::migrate_users(db)) return 13;  // idempotent\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "migrate")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "migration program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "migration failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_drop_and_rename(generated, sqlite_obj, tmp_path):
    """migrate_<name> RENAMEs a column carrying renamed_from[<old>] (data
    survives, beacon_log.label <- an older "handle" column) and DROPs a live
    column the current schema no longer declares ("legacy_note"), and a
    second call is idempotent."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "migrate_nonadditive.cpp"
    prog.write_text(
        '#include "migrate/beacon_log_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    auto exec = [&db](const char* s) {{ try {{ db << s; return true; }} catch (...) {{ return false; }} }};\n"
        "    // an older generated version: the field under its old name, plus\n"
        "    // a stray column the current schema no longer declares\n"
        '    if (!exec("CREATE TABLE \\"beacon_log_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY, '
        '\\"handle\\" TEXT, \\"strength\\" INTEGER, \\"legacy_note\\" TEXT);")) return 2;\n'
        "    if (!exec(\"INSERT INTO \\\"beacon_log_table\\\" (\\\"ID_{h}\\\", \\\"handle\\\", "
        "\\\"strength\\\", \\\"legacy_note\\\") VALUES (1, 'north', 5, 'obsolete');\")) return 3;\n"
        "    if (!::harpia::db::migrate_beacon_log(db)) return 4;\n"
        "    ::harpia::db::beacon_log_dao dao(db);\n"
        "    // the renamed column carried its data over\n"
        "    ::beacon_log got;\n"
        "    if (!dao.read(1, &got)) return 5;\n"
        '    if (got.label() != "north") return 6;\n'
        "    if (got.strength() != 5) return 7;\n"
        "    // the stray column is gone\n"
        "    int seen = 0; ::soci::indicator si;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('beacon_log_table') "
        "WHERE name = 'legacy_note'\", ::soci::into(seen, si);\n"
        "    if (seen != 0) return 8;\n"
        "    // idempotent: a second call does not corrupt the row or re-add legacy_note\n"
        "    if (!::harpia::db::migrate_beacon_log(db)) return 9;\n"
        "    ::beacon_log got2;\n"
        "    if (!dao.read(1, &got2)) return 10;\n"
        '    if (got2.label() != "north" || got2.strength() != 5) return 11;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "beacon_log_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "migrate_nonadditive")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "non-additive migration program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "non-additive migration failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_data_transform(generated, sqlite_obj, tmp_path):
    """migrate_<name> takes an optional caller-supplied data_transform hook
    (std::function<void(session&)>), run AFTER add and BEFORE drop -- proven
    here by deriving beacon_log.label from a retiring "full_label" column
    that the current schema doesn't declare at all: label must already exist
    (added) and full_label must still exist (not yet dropped) when the hook
    runs. Also proves the hook is genuinely optional (the default nullptr
    doesn't crash) and idempotent (a second call with the same hook doesn't
    corrupt the already-transformed value)."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "migrate_data_transform.cpp"
    prog.write_text(
        '#include "migrate/beacon_log_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    auto exec = [&db](const char* s) {{ try {{ db << s; return true; }} catch (...) {{ return false; }} }};\n"
        "    // an older generated version: the data lives under a column\n"
        "    // (\"full_label\") the current schema doesn't declare at all --\n"
        "    // no renamed_from marker applies here, only a value derivation.\n"
        '    if (!exec("CREATE TABLE \\"beacon_log_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY, '
        '\\"full_label\\" TEXT, \\"strength\\" INTEGER);")) return 2;\n'
        "    if (!exec(\"INSERT INTO \\\"beacon_log_table\\\" (\\\"ID_{h}\\\", \\\"full_label\\\", "
        "\\\"strength\\\") VALUES (1, 'north-station', 5);\")) return 3;\n"
        "    // the hook: copy the old column into the new one. Guarded so a\n"
        "    // second run is a no-op -- callers are responsible for their own\n"
        "    // idempotency, same as migrate_beacon_log itself may run on every startup.\n"
        "    auto transform = [](::soci::session& db) {{\n"
        "        db << \"UPDATE \\\"beacon_log_table\\\" SET \\\"label\\\" = \\\"full_label\\\" \"\n"
        "              \"WHERE \\\"label\\\" IS NULL OR \\\"label\\\" = ''\";\n"
        "    }};\n"
        "    if (!::harpia::db::migrate_beacon_log(db, transform)) return 4;\n"
        "    ::harpia::db::beacon_log_dao dao(db);\n"
        "    // label was added (by the add step) and then derived (by the hook)\n"
        "    // from full_label, which was still present when the hook ran\n"
        "    ::beacon_log got;\n"
        "    if (!dao.read(1, &got)) return 5;\n"
        '    if (got.label() != "north-station") return 6;\n'
        "    if (got.strength() != 5) return 7;\n"
        "    // full_label is gone -- the hook ran BEFORE drop, not after, so\n"
        "    // this only proves drop still ran, not that the hook read it late\n"
        "    int seen = 0; ::soci::indicator si;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('beacon_log_table') "
        "WHERE name = 'full_label'\", ::soci::into(seen, si);\n"
        "    if (seen != 0) return 8;\n"
        "    // the hook is genuinely optional: a second row, migrated with NO\n"
        "    // hook argument at all, must not crash (std::bad_function_call on\n"
        "    // an empty std::function) and must leave that row untouched\n"
        '    ::beacon_log b; b.set_id_{h}(2); b.set_label("untouched"); b.set_strength(9);\n'
        "    if (!dao.create(b)) return 9;\n"
        "    if (!::harpia::db::migrate_beacon_log(db)) return 10;\n"
        "    ::beacon_log got2;\n"
        "    if (!dao.read(2, &got2)) return 11;\n"
        '    if (got2.label() != "untouched" || got2.strength() != 9) return 12;\n'
        "    // idempotent: calling with the same hook again does not corrupt\n"
        "    // the already-transformed row (the hook's own WHERE guard is now\n"
        "    // false for it)\n"
        "    if (!::harpia::db::migrate_beacon_log(db, transform)) return 13;\n"
        "    ::beacon_log got3;\n"
        "    if (!dao.read(1, &got3)) return 14;\n"
        '    if (got3.label() != "north-station") return 15;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "beacon_log_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "migrate_data_transform")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "data-transform migration program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "data-transform migration failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_retype_column(generated, sqlite_obj, tmp_path):
    """migrate_<name> RETYPEs a column whose live SQL type no longer matches
    the current schema (beacon_log.strength: an older TEXT column, current
    schema is INTEGER) -- detected purely by runtime introspection, no DSL
    marker needed, since (unlike rename) the name is unchanged. SQLite has no
    ALTER COLUMN TYPE, so this exercises the create/copy(with CAST)/drop/
    rename table-rebuild path; data survives via CAST, and a second call is
    idempotent (no rebuild, since the type already matches)."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "migrate_retype.cpp"
    prog.write_text(
        '#include "migrate/beacon_log_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    auto exec = [&db](const char* s) {{ try {{ db << s; return true; }} catch (...) {{ return false; }} }};\n"
        "    // an older generated version: strength stored as TEXT, not INTEGER\n"
        '    if (!exec("CREATE TABLE \\"beacon_log_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY, '
        '\\"label\\" TEXT, \\"strength\\" TEXT);")) return 2;\n'
        "    if (!exec(\"INSERT INTO \\\"beacon_log_table\\\" (\\\"ID_{h}\\\", \\\"label\\\", "
        "\\\"strength\\\") VALUES (1, 'north', '7');\")) return 3;\n"
        "    if (!::harpia::db::migrate_beacon_log(db)) return 4;\n"
        "    // the column's declared type is now INTEGER\n"
        "    int seen = 0; ::soci::indicator si;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('beacon_log_table') "
        "WHERE name = 'strength' AND type = 'INTEGER'\", ::soci::into(seen, si);\n"
        "    if (seen != 1) return 5;\n"
        "    // the value survived the CAST\n"
        "    ::harpia::db::beacon_log_dao dao(db);\n"
        "    ::beacon_log got;\n"
        "    if (!dao.read(1, &got)) return 6;\n"
        '    if (got.label() != "north" || got.strength() != 7) return 7;\n'
        "    // idempotent: the type already matches, so a second call does not rebuild\n"
        "    if (!::harpia::db::migrate_beacon_log(db)) return 8;\n"
        "    ::beacon_log got2;\n"
        "    if (!dao.read(1, &got2)) return 9;\n"
        '    if (got2.label() != "north" || got2.strength() != 7) return 10;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "beacon_log_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "migrate_retype")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "retype migration program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "retype migration failed at check #{}".format(
        run.returncode)


# -- Track H.1: repeated-scalar child-table schema migration ----------------
#
# telemetry (HarpiaTest/Include/file3.harpia) -> table "telemetry_table" with
# two repeated-scalar child tables: "telemetry_table__samples" (value INTEGER)
# and "telemetry_table__notes" (value TEXT), the latter carrying
# renamed_from[old_notes]. migrate_telemetry must rename/add/drop/retype these
# child tables the same way it does the main table's own columns.

def _compile_run(tmp_path, cpp_root, name, source, pb_ccs):
    """Compile a single migration program against the generated tree + the
    named protobuf .cc files, run it, and assert a zero exit."""
    prog = tmp_path / (name + ".cpp")
    prog.write_text(source)
    binary = str(tmp_path / name)
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
         str(prog), *pb_ccs, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "{} failed at check #{}".format(
        name, run.returncode)


def _telemetry_pb(cpp_root):
    # telemetry's DAO pulls in trace_row (the table-less target of its
    # repeated-composed `traces` field), so both .pb.cc must be linked.
    return [os.path.join(cpp_root, "protofiles", "telemetry_{}.pb.cc".format(HASH)),
            os.path.join(cpp_root, "protofiles", "trace_row_{}.pb.cc".format(HASH))]


_TELEMETRY_HEAD = (
    '#include "migrate/telemetry_{h}_migrate.h"\n'
    "#include <soci/soci.h>\n"
    "#include <soci/sqlite3/soci-sqlite3.h>\n"
    "#include <string>\n"
    "int main() {{\n"
    '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
    "    auto exec = [&db](const char* s) {{ try {{ db << s; return true; }}"
    " catch (...) {{ return false; }} }};\n"
    "    auto has_table = [&db](const std::string& t) {{ int n = 0;"
    " ::soci::indicator i;"
    " db << (\"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='\""
    " + t + \"'\"), ::soci::into(n, i);"
    " return n; }};\n"
)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_child_scalar_add(generated, sqlite_obj, tmp_path):
    """A repeated-scalar field with no live child table yet: migrate_telemetry
    stands "telemetry_table__samples" up (via create_table) and it is
    immediately usable through the DAO."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_child_add", _TELEMETRY_HEAD.format(h=HASH) + (
        "    // an older version: parent + the 'notes' child table only, no 'samples'\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("CREATE TABLE \\"telemetry_table__notes\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 3;\n"
        "    if (has_table(\"telemetry_table__samples\")) return 4;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 5;\n"
        "    if (!has_table(\"telemetry_table__samples\")) return 6;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        '    ::telemetry t; t.set_id_{h}(1); t.set_label("dev");\n'
        "    t.add_samples(11); t.add_samples(22); t.add_samples(33);\n"
        "    if (!dao.create(t)) return 7;\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 8;\n"
        "    if (got.samples_size() != 3 || got.samples(2) != 33) return 9;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_child_scalar_rename(generated, sqlite_obj, tmp_path):
    """The repeated field 'notes' carries renamed_from[old_notes]:
    migrate_telemetry moves "telemetry_table__old_notes" (with its rows) to
    "telemetry_table__notes" instead of leaving it orphaned beside an empty
    new one, and a second call is idempotent."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_child_rename", _TELEMETRY_HEAD.format(h=HASH) + (
        "    // an older version: the repeated child table under its old name\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_notes\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__old_notes\\" VALUES (1, 0, \'alpha\'),'
        " (1, 1, 'beta');\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    if (has_table(\"telemetry_table__old_notes\")) return 7;\n"
        "    if (!has_table(\"telemetry_table__notes\")) return 8;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 9;\n"
        '    if (got.notes_size() != 2 || got.notes(0) != "alpha" || got.notes(1) != "beta")'
        " return 10;\n"
        "    // idempotent: a second call is a no-op (old name already gone)\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 11;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.notes_size() != 2) return 12;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_child_scalar_drop(generated, sqlite_obj, tmp_path):
    """A "telemetry_table__*" child table the current schema no longer
    declares (a repeated field removed between versions) is reaped, while the
    child tables that ARE still declared are left intact."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_child_drop", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        "    // a child table for a repeated field that no longer exists\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__ghost\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 3;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__ghost\\" VALUES (1, 0, \'stale\');"))'
        " return 4;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 5;\n"
        "    if (has_table(\"telemetry_table__ghost\")) return 6;\n"
        "    // the declared child tables were created, not reaped\n"
        "    if (!has_table(\"telemetry_table__samples\")) return 7;\n"
        "    if (!has_table(\"telemetry_table__notes\")) return 8;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_child_scalar_retype(generated, sqlite_obj, tmp_path):
    """The element type of a repeated-scalar field changed: an older
    "telemetry_table__samples" stored value as TEXT, the current schema is
    INTEGER. migrate_telemetry rebuilds the child table (create/CAST-copy/
    drop/rename), the values survive, and a second call is a no-op."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_child_retype", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        "    // older child table: value typed TEXT, not INTEGER\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__samples\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__samples\\" VALUES (1, 0, \'11\'),'
        " (1, 1, '22');\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    int typed = 0; ::soci::indicator ti;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__samples')"
        " WHERE name = 'value' AND type = 'INTEGER'\", ::soci::into(typed, ti);\n"
        "    if (typed != 1) return 7;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 8;\n"
        "    if (got.samples_size() != 2 || got.samples(0) != 11 || got.samples(1) != 22)"
        " return 9;\n"
        "    // idempotent: the type already matches, so no rebuild the 2nd time\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 10;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.samples_size() != 2) return 11;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_child_scalar_roundtrip(generated, sqlite_obj, tmp_path):
    """Integration: one old-database snapshot exercising all four child-table
    transforms in a single migrate_telemetry call -- a renamed child table
    ("old_notes"->"notes") with rows, a retyped one ("samples" TEXT->INTEGER)
    with rows, an orphan one ("ghost") to reap, and the parent row -- then
    verify every surviving value round-trips through the DAO."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_child_roundtrip", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'unit-7');\")) return 3;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_notes\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__old_notes\\" VALUES (1, 0, \'boot\'),'
        " (1, 1, 'ready');\")) return 5;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__samples\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 6;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__samples\\" VALUES (1, 0, \'5\'),'
        " (1, 1, '9');\")) return 7;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__ghost\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 8;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 9;\n"
        "    if (has_table(\"telemetry_table__old_notes\")) return 10;\n"
        "    if (has_table(\"telemetry_table__ghost\")) return 11;\n"
        "    int typed = 0; ::soci::indicator ti;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__samples')"
        " WHERE name = 'value' AND type = 'INTEGER'\", ::soci::into(typed, ti);\n"
        "    if (typed != 1) return 12;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 13;\n"
        '    if (got.label() != "unit-7") return 14;\n'
        '    if (got.notes_size() != 2 || got.notes(0) != "boot" || got.notes(1) != "ready")'
        " return 15;\n"
        "    if (got.samples_size() != 2 || got.samples(0) != 5 || got.samples(1) != 9)"
        " return 16;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


# -- Track H.2: map child-table schema migration ---------------------------
#
# telemetry also has two map fields -> child tables "telemetry_table__gauges"
# (map<string,int> -> key TEXT, value INTEGER) and "telemetry_table__flags"
# (map<int,string> -> key INTEGER, value TEXT, carrying renamed_from[old_flags]).
# A map child table is (owner, key, value) PRIMARY KEY(owner, key), so a retype
# has to check BOTH the key and the value column.

@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_map_child_add(generated, sqlite_obj, tmp_path):
    """A map field with no live child table yet: migrate_telemetry stands
    "telemetry_table__gauges" up (via create_table) and it round-trips
    through the DAO."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_map_add", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        "    if (has_table(\"telemetry_table__gauges\")) return 3;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 4;\n"
        "    if (!has_table(\"telemetry_table__gauges\")) return 5;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        '    ::telemetry t; t.set_id_{h}(1); t.set_label("dev");\n'
        '    (*t.mutable_gauges())["cpu"] = 5; (*t.mutable_gauges())["mem"] = 8;\n'
        "    if (!dao.create(t)) return 6;\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 7;\n"
        '    if (got.gauges_size() != 2 || got.gauges().at("cpu") != 5) return 8;\n'
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_map_child_rename(generated, sqlite_obj, tmp_path):
    """The map field 'flags' carries renamed_from[old_flags]: migrate_telemetry
    moves "telemetry_table__old_flags" (with its rows) to
    "telemetry_table__flags", and a second call is idempotent."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_map_rename", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        "    // the map child table under its old name (map<int,string>)\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_flags\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__old_flags\\" VALUES (1, 1, \'on\'),'
        " (1, 2, 'off');\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    if (has_table(\"telemetry_table__old_flags\")) return 7;\n"
        "    if (!has_table(\"telemetry_table__flags\")) return 8;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 9;\n"
        '    if (got.flags_size() != 2 || got.flags().at(1) != "on" || got.flags().at(2) != "off")'
        " return 10;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 11;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.flags_size() != 2) return 12;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_map_child_drop(generated, sqlite_obj, tmp_path):
    """A map "telemetry_table__*" child table the current schema no longer
    declares is reaped; the declared map child tables are left intact."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_map_drop", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("CREATE TABLE \\"telemetry_table__phantom\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" TEXT, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 3;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__phantom\\" VALUES (1, \'k\', \'v\');"))'
        " return 4;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 5;\n"
        "    if (has_table(\"telemetry_table__phantom\")) return 6;\n"
        "    if (!has_table(\"telemetry_table__gauges\")) return 7;\n"
        "    if (!has_table(\"telemetry_table__flags\")) return 8;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_map_child_retype(generated, sqlite_obj, tmp_path):
    """The map's key AND value types changed: an older
    "telemetry_table__gauges" stored key INTEGER / value TEXT, the current
    schema is key TEXT / value INTEGER. migrate_telemetry rebuilds the child
    table (both columns CAST), the entries survive, and a second call is a
    no-op."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_map_retype", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        "    // older child table: key INTEGER / value TEXT, now TEXT / INTEGER\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__gauges\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__gauges\\" VALUES (1, 7, \'42\'),'
        " (1, 8, '99');\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    int kt = 0, vt = 0; ::soci::indicator ki, vi;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__gauges')"
        " WHERE name = 'key' AND type = 'TEXT'\", ::soci::into(kt, ki);\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__gauges')"
        " WHERE name = 'value' AND type = 'INTEGER'\", ::soci::into(vt, vi);\n"
        "    if (kt != 1 || vt != 1) return 7;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 8;\n"
        '    if (got.gauges_size() != 2 || got.gauges().at("7") != 42 || got.gauges().at("8") != 99)'
        " return 9;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 10;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.gauges_size() != 2) return 11;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_map_child_roundtrip(generated, sqlite_obj, tmp_path):
    """Integration: one old-database snapshot exercising all four map
    child-table transforms in a single migrate_telemetry call -- a renamed
    child table ("old_flags"->"flags") with rows, a retyped one ("gauges",
    key/value types swapped) with rows, an orphan ("phantom") to reap, and
    the parent row -- then verify every surviving entry round-trips."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_map_roundtrip", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'unit-9');\")) return 3;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_flags\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 4;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__old_flags\\" VALUES (1, 1, \'yes\'),'
        " (1, 2, 'no');\")) return 5;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__gauges\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" INTEGER, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 6;\n"
        '    if (!exec("INSERT INTO \\"telemetry_table__gauges\\" VALUES (1, 3, \'30\'),'
        " (1, 4, '40');\")) return 7;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__phantom\\" (\\"owner\\" INTEGER,'
        ' \\"key\\" TEXT, \\"value\\" TEXT, PRIMARY KEY(\\"owner\\", \\"key\\"));"))'
        " return 8;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 9;\n"
        "    if (has_table(\"telemetry_table__old_flags\")) return 10;\n"
        "    if (has_table(\"telemetry_table__phantom\")) return 11;\n"
        "    int vt = 0; ::soci::indicator vi;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__gauges')"
        " WHERE name = 'value' AND type = 'INTEGER'\", ::soci::into(vt, vi);\n"
        "    if (vt != 1) return 12;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 13;\n"
        '    if (got.label() != "unit-9") return 14;\n'
        '    if (got.flags_size() != 2 || got.flags().at(1) != "yes" || got.flags().at(2) != "no")'
        " return 15;\n"
        '    if (got.gauges_size() != 2 || got.gauges().at("3") != 30 || got.gauges().at("4") != 40)'
        " return 16;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


# -- Track H.3: repeated-composed child-table schema migration ------------
#
# telemetry.traces -> trace_row (table-less {kind string, weight int}) ->
# child table "telemetry_table__traces" (owner, ordinal, kind, weight),
# carrying renamed_from[old_traces]. Unlike a repeated-scalar / map child
# table, the data columns (one per trace_row field) evolve independently:
# a field ADDed / DROPped / RETYPEd on trace_row is an add/drop/retype of a
# child-table column.

@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_composed_child_add(generated, sqlite_obj, tmp_path):
    """A repeated-composed field with no live child table yet:
    migrate_telemetry stands "telemetry_table__traces" up (via
    create_table) and it round-trips through the DAO."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_comp_add", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        "    if (has_table(\"telemetry_table__traces\")) return 3;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 4;\n"
        "    if (!has_table(\"telemetry_table__traces\")) return 5;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        '    ::telemetry t; t.set_id_{h}(1); t.set_label("dev");\n'
        '    auto* r = t.add_traces(); r->set_kind("boot"); r->set_weight(3);\n'
        "    if (!dao.create(t)) return 6;\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 7;\n"
        '    if (got.traces_size() != 1 || got.traces(0).kind() != "boot"'
        " || got.traces(0).weight() != 3) return 8;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_composed_child_rename(generated, sqlite_obj, tmp_path):
    """The repeated-composed field 'traces' carries renamed_from[old_traces]:
    migrate_telemetry moves "telemetry_table__old_traces" (with its rows) to
    "telemetry_table__traces", and a second call is idempotent."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_comp_rename", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_traces\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"kind\\" TEXT, \\"weight\\" INTEGER,'
        ' PRIMARY KEY(\\"owner\\", \\"ordinal\\"));")) return 4;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table__old_traces\\" VALUES'
        " (1, 0, 'boot', 3), (1, 1, 'ready', 7);\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    if (has_table(\"telemetry_table__old_traces\")) return 7;\n"
        "    if (!has_table(\"telemetry_table__traces\")) return 8;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 9;\n"
        '    if (got.traces_size() != 2 || got.traces(0).kind() != "boot"'
        ' || got.traces(1).weight() != 7) return 10;\n'
        "    if (!::harpia::db::migrate_telemetry(db)) return 11;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.traces_size() != 2) return 12;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_composed_child_drop(generated, sqlite_obj, tmp_path):
    """A repeated-composed "telemetry_table__*" child table the current
    schema no longer declares is reaped; the declared child tables stay."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_comp_drop", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("CREATE TABLE \\"telemetry_table__spans\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"name\\" TEXT, \\"dur\\" INTEGER,'
        ' PRIMARY KEY(\\"owner\\", \\"ordinal\\"));")) return 3;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table__spans\\" VALUES (1, 0, \'x\', 9);"))'
        " return 4;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 5;\n"
        "    if (has_table(\"telemetry_table__spans\")) return 6;\n"
        "    if (!has_table(\"telemetry_table__traces\")) return 7;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_composed_child_retype(generated, sqlite_obj, tmp_path):
    """The table-less target's fields evolved: an older
    "telemetry_table__traces" had "kind" as INTEGER and an extra "note"
    column and no "weight". migrate_telemetry ADDs "weight", DROPs "note",
    and RETYPEs "kind" to TEXT (one child-table rebuild), the surviving
    values carry across, and a second call is a no-op."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_comp_retype", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'dev');\")) return 3;\n"
        "    // older shape: kind INTEGER, stray note, no weight\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__traces\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"kind\\" INTEGER, \\"note\\" TEXT,'
        ' PRIMARY KEY(\\"owner\\", \\"ordinal\\"));")) return 4;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table__traces\\" VALUES'
        " (1, 0, 5, 'legacy'), (1, 1, 8, 'stale');\")) return 5;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 6;\n"
        "    int kt = 0, wc = 0, nc = 0; ::soci::indicator i0, i1, i2;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__traces')"
        " WHERE name = 'kind' AND type = 'TEXT'\", ::soci::into(kt, i0);\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__traces')"
        " WHERE name = 'weight'\", ::soci::into(wc, i1);\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__traces')"
        " WHERE name = 'note'\", ::soci::into(nc, i2);\n"
        "    if (kt != 1 || wc != 1 || nc != 0) return 7;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 8;\n"
        '    if (got.traces_size() != 2 || got.traces(0).kind() != "5"'
        ' || got.traces(1).kind() != "8") return 9;\n'
        "    if (!::harpia::db::migrate_telemetry(db)) return 10;\n"
        "    ::telemetry got2;\n"
        "    if (!dao.read(1, &got2) || got2.traces_size() != 2) return 11;\n"
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="migration round-trip needs protoc + protobuf")
def test_migration_composed_child_roundtrip(generated, sqlite_obj, tmp_path):
    """Integration: one old snapshot exercising every repeated-composed
    child-table transform in a single migrate_telemetry call -- a renamed
    child table ("old_traces"->"traces") whose data columns also need
    evolving (kind INTEGER->TEXT, +weight, -note), an orphan ("spans") to
    reap, and the parent row -- then verify the survivors round-trip."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    _compile_run(tmp_path, cpp_root, "mig_comp_roundtrip", _TELEMETRY_HEAD.format(h=HASH) + (
        '    if (!exec("CREATE TABLE \\"telemetry_table\\" (\\"ID_{h}\\" INTEGER PRIMARY KEY,'
        ' \\"label\\" TEXT);")) return 2;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table\\" (\\"ID_{h}\\", \\"label\\")'
        " VALUES (1, 'unit-3');\")) return 3;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__old_traces\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"kind\\" INTEGER, \\"note\\" TEXT,'
        ' PRIMARY KEY(\\"owner\\", \\"ordinal\\"));")) return 4;\n'
        '    if (!exec("INSERT INTO \\"telemetry_table__old_traces\\" VALUES'
        " (1, 0, 11, 'a'), (1, 1, 22, 'b');\")) return 5;\n"
        '    if (!exec("CREATE TABLE \\"telemetry_table__spans\\" (\\"owner\\" INTEGER,'
        ' \\"ordinal\\" INTEGER, \\"name\\" TEXT, PRIMARY KEY(\\"owner\\", \\"ordinal\\"));"))'
        " return 6;\n"
        "    if (!::harpia::db::migrate_telemetry(db)) return 7;\n"
        "    if (has_table(\"telemetry_table__old_traces\")) return 8;\n"
        "    if (has_table(\"telemetry_table__spans\")) return 9;\n"
        "    int wc = 0, nc = 0; ::soci::indicator i1, i2;\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__traces')"
        " WHERE name = 'weight'\", ::soci::into(wc, i1);\n"
        "    db << \"SELECT count(*) FROM pragma_table_info('telemetry_table__traces')"
        " WHERE name = 'note'\", ::soci::into(nc, i2);\n"
        "    if (wc != 1 || nc != 0) return 10;\n"
        "    ::harpia::db::telemetry_dao dao(db);\n"
        "    ::telemetry got;\n"
        "    if (!dao.read(1, &got)) return 11;\n"
        '    if (got.label() != "unit-3") return 12;\n'
        '    if (got.traces_size() != 2 || got.traces(0).kind() != "11"'
        ' || got.traces(1).kind() != "22") return 13;\n'
        "    return 0;\n"
        "}}\n").format(h=HASH), _telemetry_pb(cpp_root))


# -- Track A / A.1: field-level `phi` column encryption -------------------
#
# patient_vitals (HarpiaTest/Include/file3.harpia) has phi columns
# patient_id (string) and heart_rate (float). CrudlAdapter routes those
# through harpia::crypto::encrypt_field on write / decrypt_field on read,
# via a KeyProvider the DAO holds; the ciphertext is a marked hex blob that
# stays in the column's existing type. Non-phi columns are untouched.

def test_a1_encryption_runtime_copied(generated):
    """The phi-column encryption runtime + its transitive deps are copied
    into generated output when a message has a phi column."""
    crypto_dir = os.path.join(generated, "generated", "cpp", "crypto")
    for name in ("harpia_encrypted_column.h", "harpia_key_provider.h",
                 "harpia_audit_sink.h"):
        assert os.path.isfile(os.path.join(crypto_dir, name)), \
            "{} not copied into generated crypto/".format(name)


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_a1_encrypt_field_roundtrip(generated, tmp_path):
    """encrypt_field/decrypt_field round-trip every supported kind through a
    real KeyProvider; the stored form is marker-prefixed and not plaintext;
    a crypto-shredded DEK decrypts to "" rather than throwing (Rule 5)."""
    crypto_dir = os.path.join(generated, "generated", "cpp", "crypto")
    prog = tmp_path / "enc.cpp"
    prog.write_text(
        '#include "harpia_encrypted_column.h"\n'
        "#include <string>\n"
        "int main() {\n"
        "    ::harpia::crypto::InMemoryKeyProvider kp;\n"
        "    // text\n"
        '    std::string blob = ::harpia::crypto::encrypt_field(kp, "the-mrn-42");\n'
        '    if (blob.rfind("enc:v1:", 0) != 0) return 2;\n'
        '    if (blob.find("the-mrn-42") != std::string::npos) return 3;\n'
        '    if (::harpia::crypto::decrypt_field(kp, blob) != "the-mrn-42") return 4;\n'
        "    // numeric kinds go through the *_double / *_ll helpers\n"
        '    std::string d = ::harpia::crypto::encrypt_field(kp, std::to_string(98.6));\n'
        "    if (::harpia::crypto::decrypt_field_double(kp, d) != 98.6) return 5;\n"
        '    std::string n = ::harpia::crypto::encrypt_field(kp, std::to_string(-7));\n'
        "    if (::harpia::crypto::decrypt_field_ll(kp, n) != -7) return 6;\n"
        "    // an unmarked value passes through unchanged\n"
        '    if (::harpia::crypto::decrypt_field(kp, "plain") != "plain") return 7;\n'
        "    // a shredded DEK -> empty, never a throw (Rule 5)\n"
        "    ::harpia::crypto::Dek dek = kp.generate_dek();\n"
        '    ::harpia::crypto::WrappedDek w = kp.wrap_dek(dek);\n'
        "    kp.shred_dek(w);\n"
        "    std::string frame;\n"
        "    ::harpia::crypto::detail::put_u64(frame, w.kek_version);\n"
        "    ::harpia::crypto::detail::put_u32(frame, (uint32_t)w.bytes.size());\n"
        '    frame += w.bytes; frame += dek.seal("x");\n'
        '    std::string shredded = std::string("enc:v1:") + ::harpia::crypto::detail::to_hex(frame);\n'
        '    if (!::harpia::crypto::decrypt_field(kp, shredded).empty()) return 8;\n'
        "    return 0;\n"
        "}\n")
    binary = str(tmp_path / "enc")
    c = subprocess.run(
        ["g++", "-std=c++17", "-Werror", "-I", crypto_dir,
         "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
         str(prog), "-o", binary],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "enc program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "encrypt round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="phi encrypt-on-write needs protoc + protobuf")
def test_a1_phi_persisted_as_ciphertext(generated, sqlite_obj, tmp_path):
    """patient_vitals written through the DAO: a raw SQL query bypassing the
    DAO shows ciphertext (marker-prefixed, not the plaintext) in every phi
    column; a non-phi column (device_note) stays plaintext; and reading
    back through the DAO decrypts to the original values."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "phi_write.cpp"
    prog.write_text(
        '#include "db/patient_vitals_{h}_crudl.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    ::harpia::db::patient_vitals_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    ::patient_vitals a; a.set_id_{h}(1);\n"
        '    a.set_patient_id("mrn-90210"); a.set_heart_rate(72.5f);\n'
        '    a.set_device_note("sensor B");\n'
        "    if (!dao.create(a)) return 3;\n"
        "    // raw read, bypassing the DAO\n"
        "    std::string pid, note; double hr = 0; ::soci::indicator i0, i1, i2;\n"
        '    db << "SELECT \\"patient_id\\", \\"heart_rate\\", \\"device_note\\" '
        'FROM \\"patient_vitals_table\\" WHERE \\"ID_{h}\\" = 1",\n'
        "        ::soci::into(pid, i0), ::soci::into(hr, i1), ::soci::into(note, i2);\n"
        '    if (pid.rfind("enc:v1:", 0) != 0) return 4;   // phi string is ciphertext\n'
        '    if (pid.find("mrn-90210") != std::string::npos) return 5;\n'
        "    // heart_rate column holds the marker text, not 72.5\n"
        "    std::string hr_txt; ::soci::indicator i3;\n"
        '    db << "SELECT CAST(\\"heart_rate\\" AS TEXT) FROM \\"patient_vitals_table\\" '
        'WHERE \\"ID_{h}\\" = 1", ::soci::into(hr_txt, i3);\n'
        '    if (hr_txt.rfind("enc:v1:", 0) != 0) return 6;\n'
        '    if (note != "sensor B") return 7;            // non-phi untouched\n'
        "    // DAO read decrypts\n"
        "    ::patient_vitals got;\n"
        "    if (!dao.read(1, &got)) return 8;\n"
        '    if (got.patient_id() != "mrn-90210") return 9;\n'
        "    if (got.heart_rate() != 72.5f) return 10;\n"
        '    if (got.device_note() != "sensor B") return 11;\n'
        "    // update re-encrypts\n"
        '    got.set_patient_id("mrn-00001");\n'
        "    if (!dao.update(got)) return 12;\n"
        "    std::string pid2; ::soci::indicator i4;\n"
        '    db << "SELECT \\"patient_id\\" FROM \\"patient_vitals_table\\" '
        'WHERE \\"ID_{h}\\" = 1", ::soci::into(pid2, i4);\n'
        '    if (pid2.rfind("enc:v1:", 0) != 0 || pid2.find("mrn-00001") != std::string::npos) return 13;\n'
        "    ::patient_vitals got2; dao.read(1, &got2);\n"
        '    if (got2.patient_id() != "mrn-00001") return 14;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))
    pb_cc = os.path.join(cpp_root, "protofiles", "patient_vitals_{}.pb.cc".format(HASH))
    binary = str(tmp_path / "phi_write")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
         str(prog), pb_cc, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "phi-write program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "phi encrypt-on-write failed at check #{}".format(
        run.returncode)


# -- Track A / A.2: decrypt-on-read -- persist / restart / read ------------
#
# The DAO's default KeyProvider is an in-process dummy, so a genuine
# "restart" test needs a persistent one: Track O's LocalKeyProvider
# (file-backed KEKs), passed explicitly to the DAO ctor. CrudlAdapter ships
# harpia_key_provider_local.h alongside for exactly this.

def test_a2_key_provider_backends_shipped(generated):
    """The Local + KMS KeyProvider backend headers ship alongside the
    encryption runtime, so a deployment can hand the phi DAO a real,
    persistent KeyProvider."""
    crypto_dir = os.path.join(generated, "generated", "cpp", "crypto")
    for name in ("harpia_key_provider_local.h", "harpia_key_provider_kms.h"):
        assert os.path.isfile(os.path.join(crypto_dir, name)), \
            "{} not shipped into generated crypto/".format(name)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="phi persist/restart needs protoc + protobuf")
def test_a2_persist_restart_decrypt(generated, sqlite_obj, tmp_path):
    """write -> persist (file DB + file-backed LocalKeyProvider) -> a
    SEPARATE reader process opens the same DB + the same key store and
    reads back the decrypted phi values; a reader pointed at a DIFFERENT
    key store cannot recover the plaintext (the key, not the DB, gates the
    data) and does not crash -- non-phi columns stay readable."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    pb_cc = os.path.join(cpp_root, "protofiles",
                         "patient_vitals_{}.pb.cc".format(HASH))
    db_path = str(tmp_path / "pv.db")
    keks = str(tmp_path / "keks.store")
    other_keks = str(tmp_path / "other.store")

    common_head = (
        '#include "db/patient_vitals_{h}_crudl.h"\n'
        '#include "crypto/harpia_key_provider_local.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <string>\n"
    ).format(h=HASH)

    def build(name, body):
        prog = tmp_path / (name + ".cpp")
        prog.write_text(common_head + "int main() {\n" + body + "}\n")
        binary = str(tmp_path / name)
        c = subprocess.run(
            ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
             str(prog), pb_cc, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
             *_pkgconfig("--libs"), "-lpthread", "-ldl"],
            capture_output=True, text=True, timeout=180)
        assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
        return binary

    writer = build("a2_writer", (
        '    ::soci::session db(::soci::sqlite3, "{db}");\n'
        '    ::harpia::crypto::LocalKeyProvider kp({{"{keks}"}});\n'
        "    ::harpia::db::patient_vitals_dao dao(db, kp);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    ::patient_vitals a; a.set_id_{h}(1);\n"
        '    a.set_patient_id("mrn-55"); a.set_heart_rate(66.25f);\n'
        '    a.set_device_note("bay 3");\n'
        "    if (!dao.create(a)) return 3;\n"
        "    return 0;\n"
    ).format(db=db_path, keks=keks, h=HASH))

    reader = build("a2_reader", (
        '    ::soci::session db(::soci::sqlite3, "{db}");\n'
        '    ::harpia::crypto::LocalKeyProvider kp({{"{keks}"}});\n'
        "    ::harpia::db::patient_vitals_dao dao(db, kp);\n"
        "    ::patient_vitals got;\n"
        "    if (!dao.read(1, &got)) return 2;\n"
        '    if (got.patient_id() != "mrn-55") return 3;\n'
        "    if (got.heart_rate() != 66.25f) return 4;\n"
        '    if (got.device_note() != "bay 3") return 5;\n'
        "    return 0;\n"
    ).format(db=db_path, keks=keks, h=HASH))

    wrongkey = build("a2_wrongkey", (
        '    ::soci::session db(::soci::sqlite3, "{db}");\n'
        '    ::harpia::crypto::LocalKeyProvider kp({{"{other}"}});\n'
        "    ::harpia::db::patient_vitals_dao dao(db, kp);\n"
        "    ::patient_vitals got;\n"
        "    if (!dao.read(1, &got)) return 2;\n"
        '    if (got.patient_id() == "mrn-55") return 3;   // wrong key cannot recover it\n'
        '    if (got.device_note() != "bay 3") return 4;   // non-phi still readable\n'
        "    return 0;\n"
    ).format(db=db_path, other=other_keks, h=HASH))

    for name, binary in (("writer", writer), ("reader", reader),
                         ("wrongkey", wrongkey)):
        r = subprocess.run([binary], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, \
            "a2 {} process failed at check #{}".format(name, r.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="FK round-trip needs protoc + protobuf")
def test_fk_roundtrip(generated, sqlite_obj, tmp_path):
    """A singular composed field whose target owns a table (top_users.myUsers ->
    vip_users) persists via the child DAO and is reloaded on read."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")

    prog = tmp_path / "fk.cpp"
    prog.write_text(
        '#include "db/top_users_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::top_users_dao pdao(db);\n"
        "    harpia::db::vip_users_dao cdao(db);\n"
        "    if (!pdao.create_table() || !cdao.create_table()) return 2;\n"
        "    ::top_users t; t.set_id_{h}(1); t.set_name(\"boss\");\n"
        "    auto* u = t.mutable_myusers(); u->set_id_{h}(7);\n"
        "    u->set_name(\"vippy\"); u->set_family(\"fam\");\n"
        "    if (!pdao.create(t)) return 3;\n"            # creates child + parent
        "    ::top_users got;\n"
        "    if (!pdao.read(1, &got)) return 4;\n"
        "    if (!got.has_myusers()) return 5;\n"
        "    if (got.myusers().id_{h}() != 7) return 6;\n"
        "    if (got.myusers().name() != \"vippy\") return 7;\n"
        "    if (got.myusers().family() != \"fam\") return 8;\n"
        "    // the child row is independently present in its own table\n"
        "    ::vip_users c; if (!cdao.read(7, &c) || c.family() != \"fam\") return 9;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb = [os.path.join(proto_dir, "top_users_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "vip_users_{}.pb.cc".format(HASH))]
    binary = str(tmp_path / "fk")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), *pb, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "FK program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "FK round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="repeated-FK round-trip needs protoc + protobuf")
def test_repeated_fk_roundtrip(generated, sqlite_obj, tmp_path):
    """A repeated composed field whose target owns a table (top_users.members ->
    vip_users, 1-to-many) persists each child via its DAO through a link table and
    reloads them in order on read."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")

    prog = tmp_path / "repfk.cpp"
    prog.write_text(
        '#include "db/top_users_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::top_users_dao pdao(db);\n"
        "    harpia::db::vip_users_dao cdao(db);\n"
        "    if (!pdao.create_table() || !cdao.create_table()) return 2;\n"
        '    ::top_users t; t.set_id_{h}(1); t.set_name("boss");\n'
        "    auto* m1 = t.add_members(); m1->set_id_{h}(11);\n"
        '    m1->set_name("neo"); m1->set_family("anderson");\n'
        "    auto* m2 = t.add_members(); m2->set_id_{h}(22);\n"
        '    m2->set_name("trinity"); m2->set_family("moss");\n'
        "    if (!pdao.create(t)) return 3;\n"
        "    ::top_users got;\n"
        "    if (!pdao.read(1, &got)) return 4;\n"
        "    if (got.members_size() != 2) return 5;\n"
        "    // order preserved by the link table's ordinal\n"
        '    if (got.members(0).name() != "neo" || got.members(0).family() != "anderson") return 6;\n'
        '    if (got.members(1).name() != "trinity") return 7;\n'
        "    // each child is independently present in its own table\n"
        "    ::vip_users c; if (!cdao.read(22, &c) || c.family() != \"moss\") return 8;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb = [os.path.join(proto_dir, "top_users_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "vip_users_{}.pb.cc".format(HASH))]
    binary = str(tmp_path / "repfk")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), *pb, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "repeated-FK program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "repeated-FK round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="repeated-composed round-trip needs protoc + protobuf")
def test_repeated_composed_roundtrip(generated, sqlite_obj, tmp_path):
    """A repeated composed field whose target has no table of its own
    (shipment.cargo -> parcel, table-less) persists one child-table row per
    element (one column per parcel's own flattened fields) and reloads them
    in order on read -- no child DAO involved, unlike the repeated-FK case."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")

    prog = tmp_path / "repcomposed.cpp"
    prog.write_text(
        '#include "db/shipment_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::shipment_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        '    ::shipment s; s.set_id_{h}(1); s.set_tag("crate");\n'
        "    auto* p1 = s.add_cargo();\n"
        '    p1->set_label("books"); p1->set_weight(3);\n'
        "    auto* p2 = s.add_cargo();\n"
        '    p2->set_label("tools"); p2->set_weight(7);\n'
        "    if (!dao.create(s)) return 3;\n"
        "    ::shipment got;\n"
        "    if (!dao.read(1, &got)) return 4;\n"
        "    if (got.cargo_size() != 2) return 5;\n"
        "    // order preserved by the child table's ordinal\n"
        '    if (got.cargo(0).label() != "books" || got.cargo(0).weight() != 3) return 6;\n'
        '    if (got.cargo(1).label() != "tools" || got.cargo(1).weight() != 7) return 7;\n'
        "    // update replaces the child rows (delete-then-reinsert)\n"
        "    ::shipment s2 = s; s2.clear_cargo();\n"
        "    auto* p3 = s2.add_cargo();\n"
        '    p3->set_label("solo"); p3->set_weight(1);\n'
        "    if (!dao.update(s2)) return 8;\n"
        "    ::shipment got2; if (!dao.read(1, &got2)) return 9;\n"
        '    if (got2.cargo_size() != 1 || got2.cargo(0).label() != "solo") return 10;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb = [os.path.join(proto_dir, "shipment_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "parcel_{}.pb.cc".format(HASH))]
    binary = str(tmp_path / "repcomposed")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), *pb, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "repeated-composed program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "repeated-composed round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="nested-embed round-trip needs protoc + protobuf")
def test_nested_embed_roundtrip(generated, sqlite_obj, tmp_path):
    """A singular composed field whose own sub-field is itself composed to a
    table-less message (journey.path -> route, route.start -> waypoint)
    flattens both levels into prefixed columns (path_start_city etc.) and
    round-trips through the plain scalar-column path -- no child table."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")

    prog = tmp_path / "nestedembed.cpp"
    prog.write_text(
        '#include "db/journey_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::journey_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        '    ::journey j; j.set_id_{h}(1); j.set_vessel("kon-tiki");\n'
        "    auto* path = j.mutable_path();\n"
        '    path->set_label("pacific");\n'
        "    auto* start = path->mutable_start();\n"
        '    start->set_city("callao"); start->set_elevation(12);\n'
        "    if (!dao.create(j)) return 3;\n"
        "    ::journey got;\n"
        "    if (!dao.read(1, &got)) return 4;\n"
        '    if (got.path().label() != "pacific") return 5;\n'
        '    if (got.path().start().city() != "callao") return 6;\n'
        "    if (got.path().start().elevation() != 12) return 7;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb = [os.path.join(proto_dir, "journey_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "route_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "waypoint_{}.pb.cc".format(HASH))]
    binary = str(tmp_path / "nestedembed")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), *pb, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "nested-embed program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "nested-embed round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="embedded-FK round-trip needs protoc + protobuf")
def test_embedded_fk_roundtrip(generated, sqlite_obj, tmp_path):
    """A composed field nested inside a table-less embedded message, whose OWN
    target owns a table (outpost.berth -> crew_quarters, crew_quarters.skipper
    -> crew), persists the child via its own DAO through the embed's accessor
    chain and reloads it on read -- the FK-inside-an-embed gap."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")

    prog = tmp_path / "embeddedfk.cpp"
    prog.write_text(
        '#include "db/outpost_{h}_crudl.h"\n'
        '#include <soci/soci.h>\n'
        '#include <soci/sqlite3/soci-sqlite3.h>\n'
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::outpost_dao pdao(db);\n"
        "    harpia::db::crew_dao cdao(db);\n"
        "    if (!pdao.create_table() || !cdao.create_table()) return 2;\n"
        '    ::outpost o; o.set_id_{h}(1); o.set_commander("shepard");\n'
        "    auto* berth = o.mutable_berth();\n"
        '    berth->set_label("bay 3");\n'
        "    auto* skipper = berth->mutable_skipper();\n"
        '    skipper->set_id_{h}(9); skipper->set_name("anderson");\n'
        "    if (!pdao.create(o)) return 3;\n"          # creates child + parent
        "    ::outpost got;\n"
        "    if (!pdao.read(1, &got)) return 4;\n"
        '    if (got.berth().label() != "bay 3") return 5;\n'
        "    if (!got.berth().has_skipper()) return 6;\n"
        "    if (got.berth().skipper().id_{h}() != 9) return 7;\n"
        '    if (got.berth().skipper().name() != "anderson") return 8;\n'
        "    // the child row is independently present in its own table\n"
        '    ::crew c; if (!cdao.read(9, &c) || c.name() != "anderson") return 9;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb = [os.path.join(proto_dir, "outpost_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "crew_quarters_{}.pb.cc".format(HASH)),
          os.path.join(proto_dir, "crew_{}.pb.cc".format(HASH))]
    binary = str(tmp_path / "embeddedfk")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root,
         *_pkgconfig("--cflags"), str(prog), *pb, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "embedded-FK program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "embedded-FK round-trip failed at check #{}".format(
        run.returncode)


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="DB import/export round-trip needs protoc + protobuf")
def test_dbio_roundtrip(generated, sqlite_obj, tmp_path):
    """Export the table to JSON and XML, import into fresh DBs, verify rows."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")

    prog = tmp_path / "dbio.cpp"
    prog.write_text(
        '#include "dbio/users_{h}_dbio.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "#include <vector>\n"
        "int main() {{\n"
        '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::users_dao dao(db);\n"
        "    if (!dao.create_table()) return 1;\n"
        "    ::users a; a.set_id_{h}(1); a.set_name(\"neo\"); a.set_address(\"matrix\");\n"
        "    ::users b; b.set_id_{h}(2); b.set_name(\"trinity\");\n"
        "    if (!dao.create(a) || !dao.create(b)) return 2;\n"
        "    // JSON export -> import into a fresh DB\n"
        "    std::string js; if (!harpia::dbio::export_json(dao, &js)) return 3;\n"
        '    ::soci::session jdb(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::users_dao jdao(jdb); jdao.create_table();\n"
        "    if (!harpia::dbio::import_json(jdao, js)) return 4;\n"
        "    std::vector<::users> jr; jdao.list(&jr); if (jr.size() != 2) return 5;\n"
        "    ::users jg; if (!jdao.read(1, &jg) || jg.name() != \"neo\") return 6;\n"
        "    // XML export -> import into a fresh DB\n"
        "    std::string xs; if (!harpia::dbio::export_xml(dao, &xs)) return 7;\n"
        '    ::soci::session xdb(::soci::sqlite3, ":memory:");\n'
        "    harpia::db::users_dao xdao(xdb); xdao.create_table();\n"
        "    if (!harpia::dbio::import_xml(xdao, xs)) return 8;\n"
        "    std::vector<::users> xr; xdao.list(&xr); if (xr.size() != 2) return 9;\n"
        "    ::users xg; if (!xdao.read(2, &xg) || xg.name() != \"trinity\") return 10;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH))

    pb_cc = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    tinyxml = os.path.join(TINYXML2, "tinyxml2.cpp")
    binary = str(tmp_path / "dbio")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, "-I", TINYXML2,
         *_pkgconfig("--cflags"), str(prog), pb_cc, tinyxml, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "DB import/export program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "DB import/export round-trip failed at check #{}".format(
        run.returncode)
