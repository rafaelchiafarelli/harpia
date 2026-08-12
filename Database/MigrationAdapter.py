"""Stage 8 (database) -- schema migration / version transforms (spec 8 / 7.2).

For each table-bearing message, emit a header (<name>_<hash>_migrate.h) with a
migrate_<name>(soci::session&) that brings an existing database up to the current
schema version and records it in a "_harpia_schema_version" table:
  - ensures the table (and its child tables) exist,
  - RENAMEs a column carrying the DSL's renamed_from[<old>] modifier (both
    names known at generation time -- run first so the subsequent add/drop
    steps see the corrected column set),
  - ADDs any column the current schema declares that an older generated
    version is missing (additive),
  - DROPs any column a live table has that the current schema no longer
    declares (an inverse diff against the runtime-introspected column set --
    there is no schema history, so this is an unconditional "unrecognized
    column" removal, not a marker-driven one),
  - RETYPEs any column whose live SQL type no longer matches what the
    current schema declares for that same name (a second runtime
    introspection pass, after renames/adds/drops so the live table is
    already stabilized to the current column set). Unlike a rename this
    needs no DSL marker -- the column name is unchanged, so the mismatch is
    unambiguous. Postgres fixes each column independently with a direct
    ALTER COLUMN ... TYPE; SQLite has no such statement, so it rebuilds the
    whole table (create with the current schema, copy every row across with
    a CAST per column, drop the old table, rename the new one into place).
Cross-version data transforms (an arbitrary value-transformation function,
not just a CAST) are still out of scope.

Columns come from the shared Database.model so the migration agrees with the
schema (SqlAdapter) and the DAO (CrudlAdapter). Header-only C++.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different
from Database.backends import get_backend
from Database.model import analyze, type_registry

MIGRATE_EXT = "_migrate.h"

_MIGRATE = loadTemplate(__file__, "migrate.h.tmpl")

_ALTER = ('        if (!have.count("{cname}")) {{\n'
          '            db << "{alter_sql}";\n'
          '        }}')

_RENAME = ('        if (have.count("{old}") && !have.count("{new}")) {{\n'
          '            db << "{rename_sql}";\n'
          '            have.erase("{old}"); have.insert("{new}");\n'
          '        }}')


def _esc(sql):
    """Escape a SQL string for embedding in a C++ string literal."""
    return sql.replace('"', '\\"')


class MigrationAdapter:
    def __init__(self, messages, dest, backend=None) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "migrate")
        self.types = type_registry(messages)
        self.backend = backend or get_backend()
        self.log = logger(outFile=None, moduleName="MigrationAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, MIGRATE_EXT)
            write_if_different(os.path.join(self.outDir, fileName), self._render(msg))
            written += 1
        self.log.print("generated {} migration(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        columns, _ = analyze(msg, self.types, self.backend)
        b = self.backend
        # renames run first, against the OLD name, and correct `have` in place
        # so the additive/drop steps below see the post-rename column set.
        renames = "\n".join(
            _RENAME.format(old=c.renamed_from, new=c.name,
                          rename_sql=_esc(b.rename_column(
                              msg.tableName, c.renamed_from, c.name)))
            for c in columns if getattr(c, "renamed_from", None))
        # additive migration only ALTERs in non-PK columns (the PK always exists
        # from the first version; ALTER cannot add a PRIMARY KEY / NOT NULL column)
        alters = "\n".join(
            _ALTER.format(cname=c.name,
                          alter_sql=_esc(b.add_column(msg.tableName, c.name,
                                                      c.sql_type)))
            for c in columns if not c.pk)
        # non-additive: drop any live column the current schema no longer
        # declares (an inverse diff -- `have` minus the current column names).
        # drop_column_dynamic returns a full C++ expression (quotes and all,
        # concatenating the runtime-known column name), not a SQL string to
        # escape into a literal like the other backend calls above -- it is
        # substituted into the template unescaped, as C++ source.
        current_cols = ", ".join('"{}"'.format(_esc(c.name)) for c in columns)
        drop_expr = b.drop_column_dynamic(msg.tableName, "_dc")
        # retype: runs against the table's post-rename/add/drop column set, so
        # every current column is checked (a freshly-added one is already
        # correctly typed by add_column, so its guard is simply never true).
        retype_block = b.retype_column_dynamic(
            msg.tableName, [(c.name, c.sql_type, c.sql_def()) for c in columns])
        return _MIGRATE.format(
            guard="HARPIA_MIGRATE_{}_{}".format(msg.name.upper(), msg.md5Hash),
            name=msg.name,
            hash=msg.md5Hash,
            table=msg.tableName,
            version_table_sql=_esc(b.version_table()),
            list_columns_sql=_esc(b.list_columns_sql(msg.tableName)),
            list_column_types_sql=_esc(b.list_column_types_sql(msg.tableName)),
            stamp_version_sql=_esc(b.stamp_version(msg.tableName, msg.md5Hash)),
            renames=renames,
            alters=alters,
            current_cols=current_cols,
            drop_expr=drop_expr,
            retype_block=retype_block,
        )
