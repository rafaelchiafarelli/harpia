"""Session J.6 (initiatives/multi-language-targets/thread-1-java-target/
histories/DB-CRUDL-SQLITE/CRUDL-implementation-sqlite.md) -- CRUDL DAO
generation for the Java target.

Reuses Database/model.py's language-agnostic analyze()/type_registry() as-is
(the actual deliverable's own words) to derive each table-bearing message's
columns, then renders a Java DAO (create/read/update/remove/list +
createTable/dropTable) against those columns via JdbcBind (J.5).

Deliberately reduced scope for this first pass, same "flagged, not scoped
here" treatment this track already gives schema migration (see this
session's own history file and DB-CRUDL-SQLITE/sqlite-round-trip-
acceptance-gate.md): only TOP-LEVEL scalar/enum columns (a Column with
neither `.embed` nor `.fk_table` set) are handled. Singular FK-to-a-table
columns, flattened-embed columns, and every map_fields()/repeated_fields()
child table are all deferred -- not silently dropped: every deferred column
is logged and noted in the generated DAO's own header comment. The C++
CrudlAdapter this reuses the IR from took its own long incremental history
to reach that full sophistication (Database/CLAUDE.md); replicating all of
it in one sitting isn't this session's bar.

The generated table's own CREATE TABLE statement is scoped to match: it
declares only the columns this DAO actually populates, NOT the full schema
`Database/SqlAdapter.py` emits for the C++ target (which includes the
deferred columns) -- so the Java target's SQLite database has a smaller
schema than C++'s for a message with deferred columns, self-consistent on
its own terms rather than reusing a schema this DAO can't fully satisfy
(a REQUIRED deferred column would violate NOT NULL on every INSERT this DAO
issues otherwise).
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import write_if_different, loadTemplate
from Database.model import type_registry, analyze

_KIND_TO_JAVA = {"int": "int", "int64": "long", "double": "double", "text": "String"}
# PreparedStatement/ResultSet setter/getter suffix per column kind -- only
# needed for the PK parameter (every other column goes through JdbcBind,
# which dispatches on the field's own protobuf type instead).
_KIND_TO_JDBC_SETTER = {"int": "Int", "int64": "Long", "double": "Double", "text": "String"}

_TEMPLATE = loadTemplate(__file__, "dao.java.tmpl")


def _escape_java(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


class JavaCrudlAdapter:
    def __init__(self, messages, dest, backend, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.backend = backend
        self.dest = dest
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   "com", "harpia", "generated", "db")
        self.log = logger(outFile=None, moduleName="JavaCrudlAdapter")

    def Process(self):
        types = type_registry(self.messages)
        written = 0
        os.makedirs(self.outDir, exist_ok=True)

        for msg in self.messages:
            table = getattr(msg, "tableName", None)
            if not table:
                continue

            columns, _notes = analyze(msg, types, self.backend)
            usable = [c for c in columns if not c.embed and not c.fk_table]
            deferred = [c for c in columns if c.embed or c.fk_table]
            for c in deferred:
                self.log.print(
                    "{}: column '{}' deferred (embed/FK columns not yet "
                    "supported for the Java target's CRUDL DAO)".format(
                        msg.name, c.name))

            pk = next((c for c in usable if c.pk), None)
            if pk is None:
                # every harpia message gets a front-end-injected ID_<hash>
                # PK; a table-bearing message missing one from `usable`
                # would mean the PK itself got deferred, which analyze()
                # never does (PK is always a plain top-level int column) --
                # not reachable, but fail loudly rather than emit a DAO with
                # no primary key operations.
                self.log.print("{}: no primary-key column found, skipping".format(msg.name))
                continue

            source = self._render(msg, table, pk, usable, deferred)
            fileName = "{}_dao.java".format(msg.name)
            write_if_different(os.path.join(self.outDir, fileName), source)
            written += 1

        if written == 0:
            self.log.print("no table-bearing messages to generate a Java CRUDL DAO for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} Java CRUDL DAO(s) into {}".format(written, self.outDir))
        return None

    def _render(self, msg, table, pk, usable, deferred):
        non_pk = [c for c in usable if not c.pk]
        pk_java_type = _KIND_TO_JAVA[pk.kind]
        pk_setter = _KIND_TO_JDBC_SETTER[pk.kind]

        col_names_sql = ", ".join('"{}"'.format(c.name) for c in usable)
        placeholders = ", ".join("?" for _ in usable)
        insert_sql = 'INSERT INTO "{}" ({}) VALUES ({})'.format(table, col_names_sql, placeholders)
        select_all_sql = 'SELECT {} FROM "{}"'.format(col_names_sql, table)
        select_by_pk_sql = '{} WHERE "{}" = ?'.format(select_all_sql, pk.name)
        set_clause = ", ".join('"{}" = ?'.format(c.name) for c in non_pk)
        update_sql = 'UPDATE "{}" SET {} WHERE "{}" = ?'.format(table, set_clause, pk.name)
        delete_sql = 'DELETE FROM "{}" WHERE "{}" = ?'.format(table, pk.name)
        create_table_sql = self.backend.create_table(
            table, [(c.name, c.sql_def()) for c in usable], if_not_exists=True)
        drop_table_sql = self.backend.drop_table(table, if_exists=True)

        bind_lines = "\n".join(
            '        JdbcBind.bind(ps, {}, msg, "{}");'.format(i + 1, c.name)
            for i, c in enumerate(usable))
        extract_lines = "\n".join(
            '        JdbcBind.extract(rs, "{}", builder, "{}");'.format(c.name, c.name)
            for c in usable)
        update_bind_lines = "\n".join(
            '        JdbcBind.bind(ps, {}, msg, "{}");'.format(i + 1, c.name)
            for i, c in enumerate(non_pk))

        deferred_note = ("none" if not deferred else ", ".join(
            "{} (embed/FK)".format(c.name) for c in deferred))

        return _TEMPLATE.format(
            name=msg.name,
            table=table,
            deferred_note=deferred_note,
            pk_field=pk.name,
            pk_java_type=pk_java_type,
            pk_setter=pk_setter,
            insert_sql=_escape_java(insert_sql),
            select_by_pk_sql=_escape_java(select_by_pk_sql),
            select_all_sql=_escape_java(select_all_sql),
            update_sql=_escape_java(update_sql),
            delete_sql=_escape_java(delete_sql),
            create_table_sql=_escape_java(create_table_sql),
            drop_table_sql=_escape_java(drop_table_sql),
            bind_lines=bind_lines,
            extract_lines=extract_lines,
            update_bind_lines=update_bind_lines,
            update_pk_index=len(non_pk) + 1,
        )
