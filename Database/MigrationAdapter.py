"""Stage 8 (database) -- schema migration / version transforms (spec 8 / 7.2).

For each table-bearing message, emit a header (<name>_<hash>_migrate.h) with a
migrate_<name>(sqlite3*) that brings an existing database up to the current
schema version and records it in a "_harpia_schema_version" table. Migration is
additive: it ensures the table (and its child tables) exist and ALTERs in any
column an older generated version is missing. Renames/drops, type changes and
cross-version data transforms are out of scope.

Columns come from the shared Database.model so the migration agrees with the
schema (SqlAdapter) and the DAO (CrudlAdapter). Header-only C++.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate
from Database.model import analyze, type_registry

MIGRATE_EXT = "_migrate.h"

_MIGRATE = loadTemplate(__file__, "migrate.h.tmpl")

_ALTER = ('    if (!have.count("{cname}")) {{\n'
          '        if (!exec("ALTER TABLE \\"{table}\\" ADD COLUMN '
          '\\"{cname}\\" {ctype};")) return false;\n'
          '    }}')


class MigrationAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "migrate")
        self.types = type_registry(messages)
        self.log = logger(outFile=None, moduleName="MigrationAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, MIGRATE_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(self._render(msg))
            written += 1
        self.log.print("generated {} migration(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        columns, _ = analyze(msg, self.types)
        # additive migration only ALTERs in non-PK columns (the PK always exists
        # from the first version; ALTER cannot add a PRIMARY KEY / NOT NULL column)
        alters = "\n".join(
            _ALTER.format(cname=c.name, table=msg.tableName, ctype=c.sql_type)
            for c in columns if not c.pk)
        return _MIGRATE.format(
            guard="HARPIA_MIGRATE_{}_{}".format(msg.name.upper(), msg.md5Hash),
            name=msg.name,
            hash=msg.md5Hash,
            table=msg.tableName,
            alters=alters,
        )
