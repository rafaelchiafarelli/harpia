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
from Database.model import (analyze, type_registry, repeated_fields, map_fields,
                            child_table_names, RepeatedField,
                            RepeatedComposedField)

MIGRATE_EXT = "_migrate.h"

_MIGRATE = loadTemplate(__file__, "migrate.h.tmpl")

_ALTER = ('        if (!have.count("{cname}")) {{\n'
          '            db << "{alter_sql}";\n'
          '        }}')

_RENAME = ('        if (have.count("{old}") && !have.count("{new}")) {{\n'
          '            db << "{rename_sql}";\n'
          '            have.erase("{old}"); have.insert("{new}");\n'
          '        }}')

_CHILD_RENAME = (
    '        if (_child_have.count("{old}") && !_child_have.count("{new}")) {{\n'
    '            db << "{rename_sql}";\n'
    '            _child_have.erase("{old}"); _child_have.insert("{new}");\n'
    '        }}')


def _esc(sql):
    """Escape a SQL string for embedding in a C++ string literal."""
    return sql.replace('"', '\\"')


class MigrationAdapter:
    def __init__(self, messages, dest, backend=None, compliance=None) -> None:
        self.compliance = compliance
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
        # -- child tables (H.1: repeated-scalar, H.2: map, H.3: rep-composed)
        # repeated-scalar child tables are RepeatedField without an fk_target
        # (that excludes the repeated-composed *link table*, which stays a
        # deferred plain-FK case). The three kinds each get rename (whole
        # child table, via renamed_from) + column evolution; the orphan reap
        # below covers every child table.
        reps = repeated_fields(msg, self.types, b)
        rep_scalars = [r for r in reps
                       if isinstance(r, RepeatedField) and not r.fk_target]
        rep_composed = [r for r in reps
                        if isinstance(r, RepeatedComposedField)]
        maps = map_fields(msg, self.types, b)
        # a repeated/map field carrying renamed_from[<old>] moves its whole
        # "<table>__<old>" child table; only direct (non-embed-nested) fields
        # -- an embed-nested field's renamed_from is not plumbed.
        renamable = ([r for r in rep_scalars if r.renamed_from and not r.embed]
                     + [m for m in maps if m.renamed_from and not m.embed]
                     + [r for r in rep_composed
                        if r.renamed_from and not r.embed])
        child_renames = "\n".join(
            _CHILD_RENAME.format(
                old=_esc("{}__{}".format(msg.tableName, ch.renamed_from)),
                new=_esc(ch.child_table),
                rename_sql=_esc(b.rename_table(
                    "{}__{}".format(msg.tableName, ch.renamed_from),
                    ch.child_table)))
            for ch in renamable)
        child_current = ", ".join(
            '"{}"'.format(_esc(t))
            for t in child_table_names(msg, self.types, b))
        child_drop_expr = b.drop_table_dynamic("_dct")
        child_retypes = "\n".join(
            [b.retype_rep_child_dynamic(r.child_table, b.int_type, r.val_sql)
             for r in rep_scalars]
            + [b.retype_map_child_dynamic(m.child_table, b.int_type,
                                          m.key_sql, m.val_sql)
               for m in maps]
            + [b.evolve_rep_composed_child_dynamic(
                r.child_table, b.int_type,
                [(c.name, c.sql_type, c.sql_def()) for c in r.columns])
               for r in rep_composed])
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
            list_child_tables_sql=_esc(b.list_tables_sql(msg.tableName)),
            child_renames=child_renames,
            child_current=child_current,
            child_drop_expr=child_drop_expr,
            child_retypes=child_retypes,
        )
