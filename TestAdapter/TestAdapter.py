"""Stage 14 (unit tests) -- generate C++ unit tests for the generated code.

For each table-bearing message this emits a self-contained test program
(<name>_<hash>_test.cpp) covering, for Stage 14a:

  14.1 simple access -- every scalar field survives setter -> getter
  14.2 database      -- a CRUDL round-trip (create/read/update/list/remove)
                        against an in-memory SQLite database

It also emits the generated project's ``tests/CMakeLists.txt`` (one CTest test
per message) and vendors SQLite into the build tree so the generated project
stays self-contained. The tests are opt-in in the top-level CMake via
``-DHARPIA_BUILD_TESTS=ON`` so the existing demo build is unaffected.

Later slices add the remaining sub-items (access rights/modifiers, JSON/XML
parsers, REST/SOAP APIs, and the all-good/crash/slower/non-parseable apps).
"""
import os
import shutil

from Logger.logger import logger
from Util.util import loadTemplate
from Database.model import analyze

TEST_EXT = "_test.cpp"

_TEST = loadTemplate(__file__, "test.cpp.tmpl")

# the vendored SQLite the generated DB tests compile against
_SQLITE_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "third_party", "sqlite")


def _value(col, variant):
    """A C++ literal for this column. ``variant`` distinguishes the two rows the
    DB round-trip inserts (and keeps text/64-bit fields unique across rows).

    ``int`` covers both INT32 and BOOL in the shared column model, so it stays at
    1 in both rows -- a truthy value that round-trips whether the field is an int
    or a bool. Row uniqueness is carried by the primary key, set separately."""
    if col.kind == "text":
        return '"{}_{}"'.format(col.accessor, variant)
    if col.kind == "double":
        return "2.5" if variant == "a" else "3.5"
    if col.kind == "int64":
        return "7" if variant == "a" else "8"
    return "1"


class TestAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "tests")
        self.log = logger(outFile=None, moduleName="TestAdapter")

    def _tables(self):
        return [m for m in self.messages
                if not getattr(m, "isEnum", False) and m.tableName]

    def Process(self):
        tables = self._tables()
        os.makedirs(self.outDir, exist_ok=True)

        written = 0
        for msg in tables:
            src = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, TEST_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(src)
            written += 1

        if tables:
            self._vendor_sqlite()
        self._write_cmake(tables)

        self.log.print("generated {} unit-test program(s) into {}".format(
            written, self.outDir))
        return None

    # -- C++ test program ---------------------------------------------------
    def _render(self, msg):
        columns, _ = analyze(msg)
        bindable = [c for c in columns if c.bindable]
        pk = next((c for c in bindable if c.pk), None)
        non_pk = [c for c in bindable if not c.pk]

        return _TEST.format(
            cls=msg.name,
            crudl_header="db/{}_{}_crudl.h".format(msg.name, msg.md5Hash),
            simple_body=self._simple_body(msg, bindable),
            db_body=self._db_body(msg, pk, non_pk),
        )

    def _simple_body(self, msg, bindable):
        lines = ["    ::{} m;".format(msg.name)]
        for c in bindable:
            lines.append("    m.set_{}({});".format(c.accessor, _value(c, "a")))
        for i, c in enumerate(bindable):
            lines.append("    if (m.{}() != {}) return {};".format(
                c.accessor, _value(c, "a"), 10 + i))
        return "\n".join(lines)

    def _db_body(self, msg, pk, non_pk):
        cls = msg.name
        if pk is None:
            return ("    // no primary key column: CRUDL round-trip deferred "
                    "(Stage 14a)\n    return 0;")

        text_field = next((c for c in non_pk if c.kind == "text"), None)
        L = [
            "    ::sqlite3* db = nullptr;",
            '    if (::sqlite3_open(":memory:", &db) != SQLITE_OK) return 20;',
            "    harpia::db::{}_dao dao(db);".format(cls),
            "    if (!dao.create_table()) return 21;",
            "",
            "    // create + read back row 1",
            "    ::{} a;".format(cls),
            "    a.set_{}(1);".format(pk.accessor),
        ]
        L += ["    a.set_{}({});".format(c.accessor, _value(c, "a"))
              for c in non_pk]
        L += [
            "    if (!dao.create(a)) return 22;",
            "    ::{} got;".format(cls),
            "    if (!dao.read(1, &got)) return 23;",
        ]
        L += ["    if (got.{}() != {}) return 24;".format(c.accessor,
              _value(c, "a")) for c in non_pk]

        if text_field is not None:
            L += [
                "",
                "    // update an existing row",
                "    ::{} upd = a;".format(cls),
                '    upd.set_{}("{}_u");'.format(text_field.accessor,
                                                 text_field.accessor),
                "    if (!dao.update(upd)) return 25;",
                "    ::{} got2;".format(cls),
                "    if (!dao.read(1, &got2)) return 26;",
                '    if (got2.{}() != "{}_u") return 27;'.format(
                    text_field.accessor, text_field.accessor),
            ]

        L += [
            "",
            "    // a second row, then list + delete",
            "    ::{} b;".format(cls),
            "    b.set_{}(2);".format(pk.accessor),
        ]
        L += ["    b.set_{}({});".format(c.accessor, _value(c, "b"))
              for c in non_pk]
        L += [
            "    if (!dao.create(b)) return 28;",
            "    std::vector<::{}> all;".format(cls),
            "    if (!dao.list(&all) || all.size() != 2) return 29;",
            "    if (!dao.remove(1)) return 30;",
            "    ::{} gone;".format(cls),
            "    if (dao.read(1, &gone)) return 31;",
            "",
            "    ::sqlite3_close(db);",
            "    return 0;",
        ]
        return "\n".join(L)

    # -- generated project plumbing ----------------------------------------
    def _vendor_sqlite(self):
        dst = os.path.join(self.dest, "third_party", "sqlite")
        os.makedirs(dst, exist_ok=True)
        for name in ("sqlite3.c", "sqlite3.h", "sqlite3ext.h"):
            src = os.path.join(_SQLITE_SRC, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst, name))

    def _write_cmake(self, tables):
        lines = [
            "# Generated by harpia Stage 14 (unit tests). Do not edit.",
            "#",
            "# Built only when the top-level CMake is configured with",
            "# -DHARPIA_BUILD_TESTS=ON; run with `ctest` from the build dir.",
            "enable_language(C)",
            "find_package(Threads)",
            "",
            "# Vendored SQLite, compiled once for the generated DB unit tests.",
            "add_library(harpia_sqlite STATIC",
            "    ${CMAKE_SOURCE_DIR}/third_party/sqlite/sqlite3.c)",
            "target_include_directories(harpia_sqlite PUBLIC",
            "    ${CMAKE_SOURCE_DIR}/third_party/sqlite)",
            "target_link_libraries(harpia_sqlite PUBLIC "
            "Threads::Threads ${CMAKE_DL_LIBS})",
            "",
        ]
        for msg in tables:
            tgt = "{}_test".format(msg.name)
            src = "{}_{}{}".format(msg.name, msg.md5Hash, TEST_EXT)
            lines += [
                "add_executable({} {})".format(tgt, src),
                "target_include_directories({} PRIVATE "
                "${{CMAKE_SOURCE_DIR}}/generated/cpp)".format(tgt),
                "target_link_libraries({} PRIVATE protofiles harpia_sqlite)"
                .format(tgt),
                "add_test(NAME {} COMMAND {})".format(tgt, tgt),
                "",
            ]
        with open(os.path.join(self.outDir, "CMakeLists.txt"), "w") as out:
            out.write("\n".join(lines))
