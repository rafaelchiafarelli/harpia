"""Session J.21 (Initiatives/multi-language-targets/thread-1-java-target/
histories/Generated-tests-packaging/JUnit-test-generation.md) -- JUnit 5
test generation for the Java target.

A Java-source-emitting counterpart for a SCOPED SUBSET of
`TestAdapter.py`'s ~8 C++ body builders: field access (14.1 analogue),
JSON round trip (14.5), XML round trip (14.6), DB CRUDL round trip (14.2)
-- one JUnit 5 test class per table-bearing message, covering exactly the
columns `JavaDatabase`'s CRUDL DAO handles (top-level scalar/enum; see
`Database.model.analyze()` + the same non-embed/non-fk_table filter
`JavaCrudlAdapter` already uses).

Deliberately NOT ported (flagged, not silently dropped -- see
JavaTestAdapter/CLAUDE.md): `_access_rights_body`/`_access_modifiers_body`
(14.3/14.4 -- the Java target has no access-modifier/PRIVATE-visibility
implementation to test against at all), `_rest_body`/`_soap_body`
(14.7-14.10 -- would need a live HttpServer stood up per test, a bigger
lift than this session's scope), and the whole app-level all-good/crash/
slower/non-parseable suite (14.11-14.14, `_app_render` and friends).

Fields are set/read via reflection, not the generated typed builder API --
same reasoning as JdbcBind/HarpiaXml/HarpiaZmq: this generated code must
compile without a JDK/protoc available here to verify a hand-derived
camelCase accessor name against.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import write_if_different, loadTemplate
from Database.model import type_registry, analyze

_TEMPLATE = loadTemplate(__file__, "test.java.tmpl")


def _java_literal(col, variant):
    """A Java literal for column `col`'s value, variant 'a' or 'b' (mirrors
    TestAdapter.py's _value(), Java-typed: FLOAT is Java `float` (an `f`
    suffix), not `double`, despite Database.model's neutral "double" kind
    label for it -- see JavaDatabase/CLAUDE.md's kind-vs-Java-type note."""
    if col.kind == "text":
        return '"{}_{}"'.format(col.name, variant)
    if col.kind == "double":
        return "2.5f" if variant == "a" else "3.5f"
    if col.kind == "int64":
        return "7L" if variant == "a" else "8L"
    return "1"


def _set_and_assert_lines(usable):
    set_lines, assert_lines = [], []
    for c in usable:
        fd_expr = 'd.findFieldByName("{}")'.format(c.name)
        if c.kind == "enum":
            # Both the set value and the assertion target are derived from
            # the FieldDescriptor itself (findValueByNumber(1) -- "value 1
            # is a valid enumerator for the test schema's enums", same
            # assumption TestAdapter.py's C++ _value() makes) rather than
            # needing the enum type's Java class name at all.
            value_expr = "{}.getEnumType().findValueByNumber(1)".format(fd_expr)
        else:
            value_expr = _java_literal(c, "a")
        set_lines.append("        b.setField({}, {});".format(fd_expr, value_expr))
        assert_lines.append("        assertEquals({}, m.getField({}));".format(
            value_expr, fd_expr))
    return "\n".join(set_lines), "\n".join(assert_lines)


class JavaTestAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "java", "src", "test", "java",
                                   "com", "harpia", "generated", "test")
        self.log = logger(outFile=None, moduleName="JavaTestAdapter")

    def Process(self):
        types = type_registry(self.messages)
        os.makedirs(self.outDir, exist_ok=True)
        written = 0

        for msg in self.messages:
            table = getattr(msg, "tableName", None)
            if not table:
                continue

            columns, _notes = analyze(msg, types)
            usable = [c for c in columns if not c.embed and not c.fk_table]
            pk = next((c for c in usable if c.pk), None)
            if pk is None:
                continue

            set_lines, assert_lines = _set_and_assert_lines(usable)
            source = _TEMPLATE.format(
                name=msg.name, pk_field=pk.name,
                set_lines=set_lines, assert_lines=assert_lines,
            )
            fileName = "{}_Test.java".format(msg.name)
            write_if_different(os.path.join(self.outDir, fileName), source)
            written += 1

        if written == 0:
            self.log.print("no table-bearing messages to generate Java JUnit tests for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} Java JUnit test class(es) into {}".format(
            written, self.outDir))
        return None
