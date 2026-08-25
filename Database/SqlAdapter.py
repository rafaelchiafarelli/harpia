"""Stage 8 (database) -- SQL schema generation.

Replaces the placeholder database/<name>_<hash>_table.sql stub with a real
CREATE TABLE derived from the message:

  - one column per scalar field, with a SQLite type
  - the hidden id field (ID_<hash>) becomes INTEGER PRIMARY KEY
  - `required` -> NOT NULL, `unique` -> UNIQUE

Composed (message-typed) fields: an enum becomes an INTEGER column, a singular
FK to a table-bearing message becomes an INTEGER child-PK column, and a non-table
message is flattened (its scalar/enum sub-fields become prefixed columns).

A map<K,V> field (direct or reached through a flattened embed) becomes a child
table "<table>__<path>" keyed by the parent's PK (owner, key, value). A repeated
scalar field becomes a child table (owner, ordinal, value).

Deferred (noted as SQL comments in the output, implemented in later steps):
  - repeated composed (message-typed) fields -> child tables
  - version-transform functions (process.md 7.2.1)

Messages with no table declared, and enums, get a one-line note instead of a
table. The generated schema is validated against the vendored SQLite in tests.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import loadTemplate, write_if_different
from Database.backends import get_backend
from Database.model import (analyze, type_registry, map_fields, repeated_fields,
                            RepeatedComposedField)

SQL_EXT = "_table.sql"

_TABLE = loadTemplate(__file__, "table.sql.tmpl")


class SqlAdapter:
    def __init__(self, messages, dest, backend=None, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "database")
        self.types = type_registry(messages)
        self.backend = backend or get_backend()
        self.log = logger(outFile=None, moduleName="SqlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        tables = 0
        for msg in self.messages:
            content = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, SQL_EXT)
            write_if_different(os.path.join(self.outDir, fileName), content)
            if not getattr(msg, "isEnum", False) and msg.tableName:
                tables += 1
        self.log.print("generated SQL schema for {} table(s) into {}".format(
            tables, self.outDir))
        return None

    def _render(self, msg):
        if getattr(msg, "isEnum", False):
            return "-- {}: enum, no table\n".format(msg.name)
        if not msg.tableName:
            return "-- {}: no table declared\n".format(msg.name)

        columns, notes = analyze(msg, self.types, self.backend)
        column_lines = ['    "{}" {}'.format(c.name, c.sql_def()) for c in columns]
        main = _TABLE.format(
            name=msg.name,
            table=msg.tableName,
            visibility=msg.visibility,
            columns=",\n".join(column_lines),
            notes=("\n".join(notes) + "\n") if notes else "",
        )
        return main + self._child_tables(msg, columns)

    def _child_tables(self, msg, columns):
        """A child table per map<K,V> field (owner, key, value) and per repeated
        scalar field (owner, ordinal, value), keyed by the parent's PK."""
        maps = map_fields(msg, self.types, self.backend)
        reps = repeated_fields(msg, self.types, self.backend)
        if not maps and not reps:
            return ""
        pk = next((c for c in columns if c.pk), None)
        owner_sql = pk.sql_type if pk else self.backend.int_type
        blocks = [""]
        for mf in maps:
            blocks.append(
                '-- map {field} -> child table "{child}" (owner -> "{table}")\n'
                'CREATE TABLE IF NOT EXISTS "{child}" (\n'
                '    "owner" {owner},\n'
                '    "key" {key},\n'
                '    "value" {val},\n'
                '    PRIMARY KEY ("owner", "key")\n'
                ');'.format(field=mf.field, child=mf.child_table,
                            table=msg.tableName, owner=owner_sql,
                            key=mf.key_sql, val=mf.val_sql))
        for rf in reps:
            if isinstance(rf, RepeatedComposedField):
                cols_sql = ",\n".join(
                    '    "{}" {}'.format(c.name, c.sql_def()) for c in rf.columns)
                blocks.append(
                    '-- repeated {field} -> child table "{child}" (owner -> "{table}")\n'
                    'CREATE TABLE IF NOT EXISTS "{child}" (\n'
                    '    "owner" {owner},\n'
                    '    "ordinal" INTEGER,\n'
                    '{cols},\n'
                    '    PRIMARY KEY ("owner", "ordinal")\n'
                    ');'.format(field=rf.field, child=rf.child_table,
                                table=msg.tableName, owner=owner_sql,
                                cols=cols_sql))
                continue
            blocks.append(
                '-- repeated {field} -> child table "{child}" (owner -> "{table}")\n'
                'CREATE TABLE IF NOT EXISTS "{child}" (\n'
                '    "owner" {owner},\n'
                '    "ordinal" INTEGER,\n'
                '    "value" {val},\n'
                '    PRIMARY KEY ("owner", "ordinal")\n'
                ');'.format(field=rf.field, child=rf.child_table,
                            table=msg.tableName, owner=owner_sql, val=rf.val_sql))
        return "\n".join(blocks) + "\n"
