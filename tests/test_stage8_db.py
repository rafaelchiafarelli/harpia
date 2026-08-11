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
HASH = "c96f8fd7f45108efee5a8ecb43eab1da"

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
