"""Stage 14 (unit tests) -- generate C++ unit tests for the generated code.

For each table-bearing message this emits a self-contained test program
(<name>_<hash>_test.cpp) covering, for Stage 14a:

  14.1 simple access -- every scalar field survives setter -> getter
  14.2 database      -- a CRUDL round-trip (create/read/update/list/remove)
                        against an in-memory SQLite database

It also emits the generated project's ``tests/CMakeLists.txt`` (one CTest test
per message). The DB layer is emitted against SOCI (soci_core + sqlite3 backend,
which links the system libsqlite3), so the tests link SOCI rather than a vendored
SQLite. The tests are opt-in in the top-level CMake via ``-DHARPIA_BUILD_TESTS=ON``
so the existing demo build is unaffected.

Later slices add the remaining sub-items (access rights/modifiers, JSON/XML
parsers, REST/SOAP APIs, and the all-good/crash/slower/non-parseable apps).
"""
import os
import shutil

from Logger.logger import logger
from Util.util import loadTemplate
from Database.model import (analyze, type_registry, map_fields, repeated_fields,
                            RepeatedComposedField)

TEST_EXT = "_test.cpp"

_TEST = loadTemplate(__file__, "test.cpp.tmpl")
_APP = loadTemplate(__file__, "app.cpp.tmpl")

# vendored third-party the generated tests compile against
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_THIRD_PARTY = os.path.join(_REPO_ROOT, "third_party")
# the harpia test HTTP client (Crow ships no client); emitted alongside the tests
_CLIENT_HDR = os.path.join(_REPO_ROOT, "tests", "harpia_test_client.h")
# (subdir, files) to copy into the generated project's third_party/.
# SQLite is no longer vendored: the DB layer is emitted against SOCI, whose
# sqlite3 backend links the system libsqlite3 (SOCI/libpq come from the system,
# like protobuf/gRPC/ZMQ).
_VENDOR = (
    ("tinyxml2", ("tinyxml2.cpp", "tinyxml2.h")),     # SOAP credential parsing
    ("crow", ("crow.h",)),                            # REST/SOAP HTTP server
)
# vendored header trees copied wholesale (whole directory), not a file list
_VENDOR_TREES = ("asio",)                             # Crow's transport dependency


def _value(col, variant):
    """A C++ literal for this column. ``variant`` distinguishes the two rows the
    DB round-trip inserts (and keeps text/64-bit fields unique across rows).

    ``int`` covers both INT32 and BOOL in the shared column model, so it stays at
    1 in both rows -- a truthy value that round-trips whether the field is an int
    or a bool. Row uniqueness is carried by the primary key, set separately."""
    if col.kind == "text":
        return '"{}_{}"'.format(col.accessor, variant)
    if col.kind == "enum":
        # value 1 is a valid enumerator for the test schema's enums
        return "static_cast<::{}>(1)".format(col.enum_type)
    if col.kind == "double":
        return "2.5" if variant == "a" else "3.5"
    if col.kind == "int64":
        return "7" if variant == "a" else "8"
    return "1"


def _embed_getter(inst, col):
    """C++ read chain for an embed-flattened column: inst.step0().step1()....
    child_accessor(). col.embed is the (possibly multi-level) accessor chain
    from Database.model.Column."""
    chain = inst
    for step in col.embed:
        chain = "{}.{}()".format(chain, step)
    return "{}.{}()".format(chain, col.child_accessor)


def _embed_mutable(inst, col):
    """C++ write chain for an embed-flattened column:
    inst.mutable_step0()->mutable_step1()->...->set_child_accessor(value) is
    built by the caller appending 'set_<child_accessor>(value)'; this returns
    just the inst.mutable_step0()->mutable_step1()->...-> pointer chain."""
    chain = "{}.mutable_{}()".format(inst, col.embed[0])
    for step in col.embed[1:]:
        chain = "{}->mutable_{}()".format(chain, step)
    return chain


def _map_key(kind, i):
    """A distinct C++ key literal for map round-trip entry ``i`` (1-based)."""
    return '"k{}"'.format(i) if kind == "text" else str(i)


def _map_val(kind, i):
    """A distinct C++ value literal for map round-trip entry ``i``."""
    if kind == "text":
        return '"v{}"'.format(i)
    if kind == "double":
        return "{}.5".format(i)
    return str(i * 10)


class TestAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "tests")
        self.types = type_registry(messages)
        self.log = logger(outFile=None, moduleName="TestAdapter")

    def _tables(self):
        return [m for m in self.messages
                if not getattr(m, "isEnum", False) and m.tableName]

    def Process(self):
        tables = self._tables()
        os.makedirs(self.outDir, exist_ok=True)

        units = []  # (cmake target, source filename)
        for msg in tables:
            src = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, TEST_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(src)
            units.append(("{}_test".format(msg.name), fileName))

        if tables:
            self._vendor_deps()
            # one application-level test (14.11-14.14) over a representative
            # message, exercising the whole stack and its failure modes.
            rep = self._pick_rep(tables)
            appFile = "app_{}{}".format(rep.md5Hash, TEST_EXT)
            with open(os.path.join(self.outDir, appFile), "w") as out:
                out.write(self._app_render(rep))
            units.append(("app_test", appFile))

        self._write_cmake(units)

        self.log.print("generated {} test program(s) into {}".format(
            len(units), self.outDir))
        return None

    # -- C++ test program ---------------------------------------------------
    def _render(self, msg):
        columns, _ = analyze(msg, self.types)
        bindable = [c for c in columns if c.bindable]
        # an embed-nested FK column (fk_table) is a submessage, not a scalar
        # value _embed_getter/_embed_mutable can set/compare -- like the
        # repeated-FK case below, it's exercised by a dedicated host test
        # instead (test_embedded_fk_roundtrip).
        embed_cols = [c for c in columns if c.embed and not c.fk_table]
        pk = next((c for c in bindable if c.pk), None)
        non_pk = [c for c in bindable if not c.pk]

        return _TEST.format(
            cls=msg.name,
            crudl_header="{}_{}_crudl.h".format(msg.name, msg.md5Hash),
            soap_header="{}_{}_soap.h".format(msg.name, msg.md5Hash),
            json_header="{}_{}_json.h".format(msg.name, msg.md5Hash),
            xml_header="{}_{}_xml.h".format(msg.name, msg.md5Hash),
            rest_header="{}_{}_rest.h".format(msg.name, msg.md5Hash),
            simple_body=self._simple_body(msg, bindable),
            db_body=self._db_body(msg, pk, non_pk, embed_cols,
                                  map_fields(msg, self.types),
                                  repeated_fields(msg, self.types)),
            ar_body=self._access_rights_body(msg),
            am_body=self._access_modifiers_body(msg, pk, non_pk),
            json_body=self._json_body(msg, bindable),
            xml_body=self._xml_body(msg, bindable),
            rest_body=self._rest_body(msg, pk, non_pk),
            soap_body=self._soap_body(msg, pk, non_pk),
        )

    def _simple_body(self, msg, bindable):
        lines = ["    ::{} m;".format(msg.name)]
        for c in bindable:
            lines.append("    m.set_{}({});".format(c.accessor, _value(c, "a")))
        for i, c in enumerate(bindable):
            lines.append("    if (m.{}() != {}) return {};".format(
                c.accessor, _value(c, "a"), 10 + i))
        return "\n".join(lines)

    def _db_body(self, msg, pk, non_pk, embed_cols=(), maps=(), reps=()):
        cls = msg.name
        if pk is None:
            return ("    // no primary key column: CRUDL round-trip deferred "
                    "(Stage 14a)\n    return 0;")

        # repeated scalars round-trip here with literal values; repeated FK
        # (1-to-many) and repeated composed-to-table-less (RepeatedComposedField)
        # are exercised by host tests instead (test_repeated_fk_roundtrip /
        # test_repeated_composed_roundtrip), since both need dedicated fixtures.
        reps = [rf for rf in reps if not getattr(rf, "fk_target", None)
               and not isinstance(rf, RepeatedComposedField)]
        text_field = next((c for c in non_pk if c.kind == "text"), None)
        L = [
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::{}_dao dao(db);".format(cls),
            "    if (!dao.create_table()) return 21;",
            "",
            "    // create + read back row 1",
            "    ::{} a;".format(cls),
            "    a.set_{}(1);".format(pk.accessor),
        ]
        L += ["    a.set_{}({});".format(c.accessor, _value(c, "a"))
              for c in non_pk]
        # flattened sub-fields of a non-table composed field round-trip too
        L += ["    {}->set_{}({});".format(
              _embed_mutable("a", c), c.child_accessor, _value(c, "a"))
              for c in embed_cols]
        # map<K,V> fields round-trip through their child tables (two entries each)
        for mf in maps:
            for i in (1, 2):
                L.append("    (*{m})[{k}] = {v};".format(
                    m=mf.mutable_on("a"), k=_map_key(mf.key_kind, i),
                    v=_map_val(mf.val_kind, i)))
        # repeated scalar fields round-trip through their child tables (ordered)
        for rf in reps:
            for i in (1, 2):
                L.append("    {};".format(rf.add_on("a", _map_val(rf.val_kind, i))))
        L += [
            "    if (!dao.create(a)) return 22;",
            "    ::{} got;".format(cls),
            "    if (!dao.read(1, &got)) return 23;",
        ]
        L += ["    if (got.{}() != {}) return 24;".format(c.accessor,
              _value(c, "a")) for c in non_pk]
        L += ["    if ({} != {}) return 32;".format(
              _embed_getter("got", c), _value(c, "a")) for c in embed_cols]
        for mf in maps:
            for i in (1, 2):
                entries = mf.entries("got")
                L.append("    if ({e}.count({k}) != 1 || {e}.at({k}) != {v}) "
                         "return 33;".format(e=entries, k=_map_key(mf.key_kind, i),
                                             v=_map_val(mf.val_kind, i)))
        for rf in reps:
            L.append("    if ({} != 2) return 34;".format(rf.size_of("got")))
            for i in (1, 2):
                L.append("    if ({at} != {v}) return 34;".format(
                    at=rf.at("got", i - 1), v=_map_val(rf.val_kind, i)))

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
            "    return 0;",
        ]
        return "\n".join(L)

    def _access_rights_body(self, msg):
        # 14.3: the SOAP endpoint requires the generated credential
        # (user=<name>, pswd=<hash>). authorized_<name>() is the gate the handler
        # uses; unit-test it directly without standing up a server.
        cls = msg.name
        cred = ('<credentials><user>{cls}</user><pswd>{{}}</pswd></credentials>'
                .format(cls=cls))
        env = ('<soap:Envelope><soap:Header>' + cred +
               '</soap:Header><soap:Body/></soap:Envelope>')
        good = env.format(msg.md5Hash)
        wrong = env.format("wrong-password")
        none = "<soap:Envelope><soap:Body/></soap:Envelope>"
        return "\n".join([
            '    const std::string good = "{}";'.format(good),
            '    const std::string wrong = "{}";'.format(wrong),
            '    const std::string none = "{}";'.format(none),
            "    if (!harpia::soap::authorized_{}(good)) return 50;".format(cls),
            "    if (harpia::soap::authorized_{}(wrong)) return 51;".format(cls),
            "    if (harpia::soap::authorized_{}(none)) return 52;".format(cls),
            "    return 0;",
        ])

    def _access_modifiers_body(self, msg, pk, non_pk):
        # 14.4: modifiers that reach the schema are enforced at runtime. The ID_
        # column is a PRIMARY KEY, so a second row with the same key is rejected.
        cls = msg.name
        if pk is None:
            return ("    // no primary key column: constraint check deferred "
                    "(Stage 14b)\n    return 0;")
        L = [
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::{}_dao dao(db);".format(cls),
            "    if (!dao.create_table()) return 41;",
            "    ::{} a;".format(cls),
            "    a.set_{}(1);".format(pk.accessor),
        ]
        L += ["    a.set_{}({});".format(c.accessor, _value(c, "a"))
              for c in non_pk]
        L += [
            "    if (!dao.create(a)) return 42;",
            "    // PRIMARY KEY is unique: a duplicate key must be rejected",
            "    ::{} dup;".format(cls),
            "    dup.set_{}(1);".format(pk.accessor),
        ]
        L += ["    dup.set_{}({});".format(c.accessor, _value(c, "b"))
              for c in non_pk]
        L += [
            "    if (dao.create(dup)) return 43;",
            "    return 0;",
        ]
        return "\n".join(L)

    def _set_all(self, msg, bindable):
        lines = ["    ::{} a;".format(msg.name)]
        for c in bindable:
            lines.append("    a.set_{}({});".format(c.accessor, _value(c, "a")))
        return lines

    def _survives(self, bindable, base_code):
        # assert each scalar field set on `a` survived the round-trip into `b`.
        # (Scalars only; composed/repeated round-trip is deferred -- the XML
        # runtime emits unset nested messages, so SerializeAsString equality is
        # not reliable for FK-bearing messages yet.)
        return ["    if (b.{}() != {}) return {};".format(
                c.accessor, _value(c, "a"), base_code) for c in bindable]

    def _json_body(self, msg, bindable):
        # 14.5: message -> JSON -> message preserves the fields, and the checker
        # accepts good JSON but rejects garbage.
        L = self._set_all(msg, bindable)
        L += [
            "    std::string js;",
            "    if (!harpia::json::to_json(a, &js)) return 60;",
            "    ::{} b;".format(msg.name),
            "    if (!harpia::json::from_json(js, &b)) return 61;",
        ]
        L += self._survives(bindable, 62)
        L += [
            "    if (!harpia::json::is_valid_json(js)) return 63;",
            '    if (harpia::json::is_valid_json("this is not json")) return 64;',
            "    return 0;",
        ]
        return "\n".join(L)

    def _xml_body(self, msg, bindable):
        # 14.6: message -> XML -> message preserves the fields, and from_xml
        # rejects non-XML input.
        L = self._set_all(msg, bindable)
        L += [
            "    const std::string xs = ::harpia::xml::to_xml(a);",
            "    if (xs.empty()) return 70;",
            "    ::{} b;".format(msg.name),
            "    if (!::harpia::xml::from_xml(xs, &b)) return 71;",
        ]
        L += self._survives(bindable, 72)
        L += [
            "    ::{} c;".format(msg.name),
            '    if (::harpia::xml::from_xml("not xml at all", &c)) return 73;',
            "    return 0;",
        ]
        return "\n".join(L)

    def _serve(self, registers, fail_code):
        # Stand a Crow app up on an OS-assigned ephemeral port (so parallel ctest
        # runs don't collide) and open a client on it. `registers` are the
        # register_* statements; `fail_code` is returned if the bind fails.
        # crow's app.port() returns the real bound port after wait_for_server_start
        # (the acceptor binds in the server ctor, before the start is signalled),
        # so no separate port probe is needed.
        L = [
            "    crow::SimpleApp app;",
            "    app.loglevel(crow::LogLevel::Warning);",
        ]
        L += ["    " + r for r in registers]
        L += [
            '    auto fut = app.bindaddr("127.0.0.1").port(0).multithreaded().run_async();',
            "    app.wait_for_server_start();",
            "    const int port = app.port();",
            "    if (port <= 0) {{ app.stop(); fut.get(); return {}; }}".format(
                fail_code),
            '    harpia_test::Client cli("127.0.0.1", port);',
        ]
        return L

    def _rest_body(self, msg, pk, non_pk):
        # 14.7/14.10: the REST bindings serve real HTTP JSON CRUD over a live
        # server on an ephemeral port (so parallel ctest runs don't collide).
        cls = msg.name
        if pk is None:
            return ("    // no primary key: REST id routing deferred (Stage 14d)"
                    "\n    return 0;")
        probe = next((c for c in non_pk if c.kind == "text"), None)
        cred = ('const harpia_test::Headers cred = {{"X-User", "' + cls +
                '"}, {"X-Pswd", "' + msg.md5Hash + '"}};')
        credx = ('const harpia_test::Headers credx = {{"X-User", "' + cls +
                 '"}, {"X-Pswd", "' + msg.md5Hash +
                 '"}, {"Accept", "application/xml"}};')
        wrong = ('harpia_test::Headers{{"X-User", "' + cls +
                 '"}, {"X-Pswd", "nope"}}')
        L = [
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::" + cls + "_dao dao(db);",
            "    if (!dao.create_table()) return 81;",
        ]
        L += self._serve(
            ['harpia::rest::register_' + cls + '(app, db, "/api/v1");'], 82)
        L += [
            "    " + cred,
            "    " + credx,
            "    int code = 0;",
            "    do {",
            "        // every route requires the generated credential (X-User/X-Pswd)",
            '        auto noc = cli.Get("/api/v1/' + cls + '");',
            "        if (!noc || noc.status != 401) { code = 93; break; }",
            '        auto bad = cli.Get("/api/v1/' + cls + '", ' + wrong + ");",
            "        if (!bad || bad.status != 401) { code = 94; break; }",
            "        ::" + cls + " a;",
            "        a.set_" + pk.accessor + "(1);",
        ]
        L += ["        a.set_" + c.accessor + "(" + _value(c, "a") + ");"
              for c in non_pk]
        L += [
            "        std::string body;",
            "        if (!::harpia::json::to_json(a, &body)) { code = 83; break; }",
            '        auto post = cli.Post("/api/v1/' + cls + '", body, "application/json", cred);',
            "        if (!post || post.status != 201) { code = 84; break; }",
            '        auto got = cli.Get("/api/v1/' + cls + '/1", cred);',
            "        if (!got || got.status != 200) { code = 85; break; }",
        ]
        if probe is not None:
            v = probe.accessor + "_a"
            L.append('        if (got.body.find("' + v + '") == std::string::npos)'
                     " { code = 86; break; }")
        L += [
            '        auto lst = cli.Get("/api/v1/' + cls + '", cred);',
            "        if (!lst || lst.status != 200) { code = 87; break; }",
            "        // content negotiation: XML response, and an XML request body",
            '        auto gx = cli.Get("/api/v1/' + cls + '/1", credx);',
            '        if (!gx || gx.status != 200 || gx.body.find("<") == '
            "std::string::npos) { code = 95; break; }",
        ]
        if probe is not None:
            L.append('        if (gx.body.find("' + probe.accessor + '_a") == '
                     "std::string::npos) { code = 96; break; }")
        L += [
            "        ::" + cls + " ax = a;",
            "        ax.set_" + pk.accessor + "(2);",
            "        const std::string axml = ::harpia::xml::to_xml(ax);",
            '        auto xpost = cli.Post("/api/v1/' + cls + '", axml, "application/xml", cred);',
            "        if (!xpost || xpost.status != 201) { code = 97; break; }",
            '        auto gx2 = cli.Get("/api/v1/' + cls + '/2", credx);',
            "        if (!gx2 || gx2.status != 200) { code = 98; break; }",
        ]
        if probe is not None:
            L.append('        if (gx2.body.find("' + probe.accessor + '_a") == '
                     "std::string::npos) { code = 99; break; }")
        if probe is not None:
            L += [
                "        ::" + cls + " b = a;",
                '        b.set_' + probe.accessor + '("' + probe.accessor + '_u");',
                "        std::string bb;",
                "        if (!::harpia::json::to_json(b, &bb)) { code = 88; break; }",
                '        auto put = cli.Put("/api/v1/' + cls + '/1", bb, "application/json", cred);',
                "        if (!put || put.status != 204) { code = 89; break; }",
                '        auto g2 = cli.Get("/api/v1/' + cls + '/1", cred);',
                '        if (!g2 || g2.body.find("' + probe.accessor + '_u") == '
                "std::string::npos) { code = 90; break; }",
            ]
        L += [
            '        auto del = cli.Delete("/api/v1/' + cls + '/1", cred);',
            "        if (!del || del.status != 204) { code = 91; break; }",
            '        auto gone = cli.Get("/api/v1/' + cls + '/1", cred);',
            "        if (!gone || gone.status != 404) { code = 92; break; }",
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
        ]
        return "\n".join(L)

    def _soap_body(self, msg, pk, non_pk):
        # 14.8/14.9: the SOAP endpoint serves real SOAP-over-HTTP (XML), gated by
        # the credential: a correct one round-trips set/get, a wrong one -> 401.
        cls = msg.name
        if pk is None:
            return ("    // no primary key: SOAP id routing deferred (Stage 14d)"
                    "\n    return 0;")
        probe = next((c for c in non_pk if c.kind == "text"), None)
        good = ('<soap:Header><credentials><user>' + cls + '</user><pswd>' +
                msg.md5Hash + '</pswd></credentials></soap:Header>')
        bad = ('<soap:Header><credentials><user>' + cls +
               '</user><pswd>nope</pswd></credentials></soap:Header>')
        L = [
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::" + cls + "_dao dao(db);",
            "    if (!dao.create_table()) return 101;",
        ]
        L += self._serve(
            ['harpia::soap::register_' + cls + '_soap(app, db, "/soap");'], 102)
        L += [
            '    const std::string hdr = "' + good + '";',
            '    const std::string badhdr = "' + bad + '";',
            "    int code = 0;",
            "    do {",
            "        ::" + cls + " a;",
            "        a.set_" + pk.accessor + "(1);",
        ]
        L += ["        a.set_" + c.accessor + "(" + _value(c, "a") + ");"
              for c in non_pk]
        L += [
            "        const std::string mx = ::harpia::xml::to_xml(a);",
            '        const std::string setEnv = "<soap:Envelope>" + hdr + "<soap:Body><set>" + mx + "</set></soap:Body></soap:Envelope>";',
            '        auto s = cli.Post("/soap/' + cls + '", setEnv, "text/xml");',
            '        if (!s || s.status != 200 || s.body.find("<ok>true</ok>") == std::string::npos) { code = 103; break; }',
            '        const std::string badEnv = "<soap:Envelope>" + badhdr + "<soap:Body><get><id>1</id></get></soap:Body></soap:Envelope>";',
            '        auto na = cli.Post("/soap/' + cls + '", badEnv, "text/xml");',
            "        if (!na || na.status != 401) { code = 104; break; }",
            '        const std::string getEnv = "<soap:Envelope>" + hdr + "<soap:Body><get><id>1</id></get></soap:Body></soap:Envelope>";',
            '        auto g = cli.Post("/soap/' + cls + '", getEnv, "text/xml");',
            '        if (!g || g.status != 200 || g.body.find("getResponse") == std::string::npos) { code = 105; break; }',
        ]
        if probe is not None:
            v = probe.accessor + "_a"
            L.append('        if (g.body.find("' + v + '") == std::string::npos)'
                     " { code = 106; break; }")
        # update round-trips: change a field, <update>, then <get> sees the change
        if probe is not None:
            L += [
                "        ::" + cls + " b = a;",
                '        b.set_' + probe.accessor + '("' + probe.accessor + '_u");',
                "        const std::string ux = ::harpia::xml::to_xml(b);",
                '        const std::string updEnv = "<soap:Envelope>" + hdr + "<soap:Body><update>" + ux + "</update></soap:Body></soap:Envelope>";',
                '        auto u = cli.Post("/soap/' + cls + '", updEnv, "text/xml");',
                '        if (!u || u.status != 200 || u.body.find("<ok>true</ok>") == std::string::npos) { code = 107; break; }',
                '        auto g2 = cli.Post("/soap/' + cls + '", getEnv, "text/xml");',
                '        if (!g2 || g2.body.find("' + probe.accessor + '_u") == std::string::npos) { code = 108; break; }',
            ]
        # delete round-trips: <delete>, then <get> reports not found
        L += [
            '        const std::string delEnv = "<soap:Envelope>" + hdr + "<soap:Body><delete><id>1</id></delete></soap:Body></soap:Envelope>";',
            '        auto d = cli.Post("/soap/' + cls + '", delEnv, "text/xml");',
            '        if (!d || d.status != 200 || d.body.find("<ok>true</ok>") == std::string::npos) { code = 109; break; }',
            '        auto g3 = cli.Post("/soap/' + cls + '", getEnv, "text/xml");',
            '        if (!g3 || g3.body.find("not found") == std::string::npos) { code = 111; break; }',
        ]
        L += [
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
        ]
        return "\n".join(L)

    # -- application-level test (14.11-14.14) ------------------------------
    def _pick_rep(self, tables):
        # a representative message for the whole-stack app test: prefer one with
        # a primary key and a text field and no composed field (FK or flattened
        # embed), so the cross-layer round-trip stays flat and deterministic.
        def cols(m):
            return analyze(m, self.types)[0]

        def has_pk(m):
            return any(c.bindable and c.pk for c in cols(m))

        def has_text(m):
            return any(c.bindable and c.kind == "text" and not c.pk for c in cols(m))

        def has_composed(m):
            return any(c.fk_target or c.embed for c in cols(m))

        for m in tables:
            if has_pk(m) and has_text(m) and not has_composed(m):
                return m
        for m in tables:
            if has_pk(m) and has_text(m):
                return m
        return tables[0]

    def _app_render(self, msg):
        columns, _ = analyze(msg, self.types)
        bindable = [c for c in columns if c.bindable]
        pk = next((c for c in bindable if c.pk), None)
        non_pk = [c for c in bindable if not c.pk]
        probe = next((c for c in non_pk if c.kind == "text"), None)
        h = msg.md5Hash
        return _APP.format(
            cls=msg.name,
            crudl_header="{}_{}_crudl.h".format(msg.name, h),
            soap_header="{}_{}_soap.h".format(msg.name, h),
            json_header="{}_{}_json.h".format(msg.name, h),
            xml_header="{}_{}_xml.h".format(msg.name, h),
            rest_header="{}_{}_rest.h".format(msg.name, h),
            all_good=self._app_all_good(msg, pk, non_pk, probe),
            crash=self._app_crash(msg, pk, probe),
            slower=self._app_slower(),
            non_parseable=self._app_non_parseable(msg),
        )

    def _credential(self, msg):
        return ('<soap:Header><credentials><user>' + msg.name + '</user><pswd>' +
                msg.md5Hash + '</pswd></credentials></soap:Header>')

    def _rest_headers_decl(self, msg):
        # C++ declaration of the REST access credential (X-User/X-Pswd) as `rc`.
        return ('const harpia_test::Headers rc = {{"X-User", "' + msg.name +
                '"}, {"X-Pswd", "' + msg.md5Hash + '"}};')

    def _app_all_good(self, msg, pk, non_pk, probe):
        cls = msg.name
        L = [
            "int all_good() {",
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::" + cls + "_dao dao(db);",
            "    if (!dao.create_table()) return 111;",
        ]
        L += self._serve([
            'harpia::rest::register_' + cls + '(app, db, "/api/v1");',
            'harpia::soap::register_' + cls + '_soap(app, db, "/soap");',
        ], 112)
        L += [
            '    const std::string hdr = "' + self._credential(msg) + '";',
            "    " + self._rest_headers_decl(msg),
            "    int code = 0;",
            "    do {",
            "        ::" + cls + " a;",
            "        a.set_" + pk.accessor + "(1);",
        ]
        L += ["        a.set_" + c.accessor + "(" + _value(c, "a") + ");"
              for c in non_pk]
        L += [
            "        std::string body;",
            "        if (!::harpia::json::to_json(a, &body)) { code = 113; break; }",
            '        auto post = cli.Post("/api/v1/' + cls + '", body, "application/json", rc);',
            "        if (!post || post.status != 201) { code = 114; break; }",
            '        const std::string getEnv = "<soap:Envelope>" + hdr + "<soap:Body><get><id>1</id></get></soap:Body></soap:Envelope>";',
            '        auto g = cli.Post("/soap/' + cls + '", getEnv, "text/xml");',
            '        if (!g || g.status != 200 || g.body.find("getResponse") == std::string::npos) { code = 115; break; }',
        ]
        if probe is not None:
            L.append('        if (g.body.find("' + probe.accessor + '_a") == '
                     "std::string::npos) { code = 116; break; }")
        L += [
            "        ::" + cls + " chk;",
            "        if (!dao.read(1, &chk)) { code = 117; break; }",
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
            "}",
        ]
        return "\n".join(L)

    def _app_crash(self, msg, pk, probe):
        cls = msg.name
        L = [
            "int crash() {",
            "    // no create_table(): backend ops must fail cleanly, not crash",
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::" + cls + "_dao dao(db);",
            "    ::" + cls + " a;",
            "    a.set_" + pk.accessor + "(1);",
        ]
        if probe is not None:
            L.append('    a.set_' + probe.accessor + '("' + probe.accessor + '_a");')
        L += [
            "    if (dao.create(a)) return 121;",
            "    ::" + cls + " got;",
            "    if (dao.read(1, &got)) return 122;",
        ]
        L += self._serve(
            ['harpia::rest::register_' + cls + '(app, db, "/api/v1");'], 123)
        L += [
            "    " + self._rest_headers_decl(msg),
            "    int code = 0;",
            "    do {",
            "        std::string body;",
            "        if (!::harpia::json::to_json(a, &body)) { code = 124; break; }",
            '        auto post = cli.Post("/api/v1/' + cls + '", body, "application/json", rc);',
            "        if (!post) { code = 125; break; }",
            "        if (post.status != 500) { code = 126; break; }",
            '        auto lst = cli.Get("/api/v1/' + cls + '", rc);',
            "        if (!lst || lst.status != 500) { code = 127; break; }",
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
            "}",
        ]
        return "\n".join(L)

    def _app_slower(self):
        return "\n".join([
            "int slower() {",
            "    crow::SimpleApp app;",
            "    app.loglevel(crow::LogLevel::Warning);",
            "    // a deliberately slow handler models a slow application",
            '    app.route_dynamic("/slow").methods(crow::HTTPMethod::GET)(',
            "        [](const crow::request&, crow::response& res) {",
            "            std::this_thread::sleep_for(std::chrono::milliseconds(150));",
            "            res.code = 200;",
            '            res.set_header("Content-Type", "text/plain");',
            '            res.body = "ok";',
            "            res.end();",
            "        });",
            '    auto fut = app.bindaddr("127.0.0.1").port(0).multithreaded().run_async();',
            "    app.wait_for_server_start();",
            "    const int port = app.port();",
            "    if (port <= 0) { app.stop(); fut.get(); return 130; }",
            "    int code = 0;",
            "    do {",
            "        // a generous read timeout tolerates the slow response",
            '        harpia_test::Client ok("127.0.0.1", port);',
            "        ok.set_read_timeout_ms(5000);",
            '        auto good = ok.Get("/slow");',
            "        if (!good || good.status != 200) { code = 131; break; }",
            "        // a dead endpoint returns cleanly within a bounded timeout",
            '        harpia_test::Client dead("127.0.0.1", 1);',
            "        dead.set_connection_timeout_ms(1000);",
            '        auto r = dead.Get("/nope");',
            "        if (r) { code = 132; break; }",
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
            "}",
        ])

    def _app_non_parseable(self, msg):
        cls = msg.name
        return "\n".join([
            "int non_parseable() {",
            "    ::" + cls + " m;",
            '    if (::harpia::json::from_json("{ not valid json", &m)) return 140;',
            '    if (::harpia::json::is_valid_json("definitely not json")) return 141;',
            '    if (::harpia::xml::from_xml("<unclosed", &m)) return 142;',
            '    ::soci::session db(::soci::sqlite3, ":memory:");',
            "    harpia::db::" + cls + "_dao dao(db);",
            "    if (!dao.create_table()) return 144;",
        ] + self._serve([
            'harpia::rest::register_' + cls + '(app, db, "/api/v1");',
            'harpia::soap::register_' + cls + '_soap(app, db, "/soap");',
        ], 145) + [
            "    " + self._rest_headers_decl(msg),
            "    int code = 0;",
            "    do {",
            '        auto bj = cli.Post("/api/v1/' + cls + '", "{ not json", "application/json", rc);',
            "        if (!bj || bj.status != 400) { code = 146; break; }",
            '        auto bx = cli.Post("/soap/' + cls + '", "<not soap", "text/xml");',
            "        if (!bx || bx.status != 400) { code = 147; break; }",
            "    } while (false);",
            "    app.stop(); fut.get();",
            "    return code;",
            "}",
        ])

    # -- generated project plumbing ----------------------------------------
    def _vendor_deps(self):
        for sub, files in _VENDOR:
            dst = os.path.join(self.dest, "third_party", sub)
            os.makedirs(dst, exist_ok=True)
            for name in files:
                src = os.path.join(_THIRD_PARTY, sub, name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(dst, name))
        # header trees (e.g. standalone asio) copied whole so the generated
        # project stays self-contained on any target board (no system package)
        for sub in _VENDOR_TREES:
            src = os.path.join(_THIRD_PARTY, sub)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(self.dest, "third_party", sub),
                                dirs_exist_ok=True)
        # the test HTTP client lives next to the generated tests (Crow has none)
        if os.path.exists(_CLIENT_HDR):
            shutil.copy2(_CLIENT_HDR,
                         os.path.join(self.outDir, "harpia_test_client.h"))

    def _write_cmake(self, units):
        lines = [
            "# Generated by harpia Stage 14 (unit tests). Do not edit.",
            "#",
            "# Built only when the top-level CMake is configured with",
            "# -DHARPIA_BUILD_TESTS=ON; run with `ctest` from the build dir.",
            "find_package(Threads)",
            "",
            "# The DB layer is emitted against SOCI (soci_core + the sqlite3",
            "# backend); SOCI's sqlite3 backend links the system libsqlite3.",
            "set(HARPIA_SOCI_LIBS soci_core soci_sqlite3)",
            "",
            "# Vendored tinyxml2 for the SOAP credential (access-rights) tests.",
            "add_library(harpia_tinyxml2 STATIC",
            "    ${CMAKE_SOURCE_DIR}/third_party/tinyxml2/tinyxml2.cpp)",
            "target_include_directories(harpia_tinyxml2 PUBLIC",
            "    ${CMAKE_SOURCE_DIR}/third_party/tinyxml2)",
            "",
        ]
        for tgt, src in units:
            lines += [
                "add_executable({} {})".format(tgt, src),
                "target_include_directories({} PRIVATE".format(tgt),
                "    ${CMAKE_SOURCE_DIR}/generated/cpp",
                "    ${CMAKE_CURRENT_SOURCE_DIR}",
                "    ${CMAKE_SOURCE_DIR}/third_party/crow",
                "    ${CMAKE_SOURCE_DIR}/third_party/asio)",
                "target_link_libraries({} PRIVATE protofiles harpia_tinyxml2 "
                "${{HARPIA_SOCI_LIBS}} Threads::Threads ${{CMAKE_DL_LIBS}})".format(
                    tgt),
                "add_test(NAME {} COMMAND {})".format(tgt, tgt),
                "",
            ]
        with open(os.path.join(self.outDir, "CMakeLists.txt"), "w") as out:
            out.write("\n".join(lines))
