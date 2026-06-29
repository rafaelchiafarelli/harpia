"""Stage 8 (database) -- SQL schema generation.

Replaces the placeholder database/<name>_<hash>_table.sql stub with a real
CREATE TABLE derived from the message:

  - one column per scalar field, with a SQLite type
  - the hidden id field (ID_<hash>) becomes INTEGER PRIMARY KEY
  - `required` -> NOT NULL, `unique` -> UNIQUE

Deferred (noted as SQL comments in the output, implemented in later steps):
  - composed (message-typed) fields -> foreign keys
  - repeated / map fields -> separate child tables
  - version-transform functions (process.md 7.2.1)

Messages with no table declared, and enums, get a one-line note instead of a
table. The generated schema is validated against the vendored SQLite in tests.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate
from Database.model import analyze, type_registry

SQL_EXT = "_table.sql"

_TABLE = loadTemplate(__file__, "table.sql.tmpl")


class SqlAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "database")
        self.types = type_registry(messages)
        self.log = logger(outFile=None, moduleName="SqlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        tables = 0
        for msg in self.messages:
            content = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, SQL_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(content)
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

        columns, notes = analyze(msg, self.types)
        column_lines = ['    "{}" {}'.format(c.name, c.sql_def()) for c in columns]
        return _TABLE.format(
            name=msg.name,
            table=msg.tableName,
            visibility=msg.visibility,
            columns=",\n".join(column_lines),
            notes=("\n".join(notes) + "\n") if notes else "",
        )
