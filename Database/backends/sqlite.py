"""SQLite dialect.

Reproduces harpia's *original* Stage-8 SQL output verbatim, so that switching
the generator onto the ``DbBackend`` seam is a behavioural no-op for existing
SQLite users. Byte-for-byte parity of the emitted SQL against today's hard-wired
strings is the acceptance test for the schema/CRUDL/migration refactor slices.

Two intentional, documented deltas from the pre-seam code (both behaviour-
equivalent, adopted so the migration C++ can be dialect-free):

  * :meth:`list_columns_sql` uses ``pragma_table_info()`` -- the table-valued
    function form (SQLite >= 3.16) -- so it SELECTs a single ``"name"`` column,
    exactly like the Postgres ``information_schema`` query. The old code ran a
    raw ``PRAGMA table_info("t")`` and read result-column index 1; that index
    knowledge no longer leaks into the generated code.
  * child-table DDL uses ``PRIMARY KEY("owner", "key")`` (no space before the
    paren), matching CrudlAdapter's embedded one-liners. SqlAdapter's pretty
    multi-line schema currently prints ``PRIMARY KEY (...)`` with a space --
    adopting this canonical form is a one-space golden diff, not a semantic one.
"""
from Database.backends.base import DbBackend, _esc


# harpia scalar token -> SQLite column type. (The neutral C++ bind "kind" that
# used to sit beside these in ``model._SCALARS`` -- int/int64/double/text --
# stays in model.py; it is not a dialect concern.)
_TYPES = {
    "INT32":  "INTEGER",
    "INT64":  "INTEGER",
    "BOOL":   "INTEGER",
    "FLOAT":  "REAL",
    "STRING": "TEXT",
}


class SqliteBackend(DbBackend):
    name = "sqlite"
    soci_backend = "sqlite3"

    @property
    def soci_backend_symbol(self):
        return "::soci::sqlite3"

    @property
    def soci_backend_header(self):
        return "soci/sqlite3/soci-sqlite3.h"

    # -- types ----------------------------------------------------------------
    def sql_type(self, token):
        return _TYPES[token]

    @property
    def int_type(self):
        return "INTEGER"

    # -- columns & tables -----------------------------------------------------
    def column_def(self, sql_type, *, pk=False, required=False, unique=False):
        # Caller-assigned PK -- a plain rowid alias, NOT AUTOINCREMENT. The id
        # (ID_<hash> field) is set by the caller and bound on INSERT, so no
        # auto-generation is introduced (that would ignore the caller's id).
        if pk:
            return "{} PRIMARY KEY".format(sql_type)
        parts = [sql_type]
        if required:
            parts.append("NOT NULL")
        if unique:
            parts.append("UNIQUE")
        return " ".join(parts)

    @staticmethod
    def _ine(if_not_exists):
        return "IF NOT EXISTS " if if_not_exists else ""

    @staticmethod
    def _ie(if_exists):
        return "IF EXISTS " if if_exists else ""

    def create_table(self, table, columns, if_not_exists=True):
        cols = ", ".join('"{}" {}'.format(name, defn) for name, defn in columns)
        return 'CREATE TABLE {}"{}" ({});'.format(
            self._ine(if_not_exists), table, cols)

    def drop_table(self, table, if_exists=True):
        return 'DROP TABLE {}"{}";'.format(self._ie(if_exists), table)

    def map_child_table(self, child, owner_type, key_type, val_type,
                        if_not_exists=True):
        return ('CREATE TABLE {}"{}" ("owner" {}, "key" {}, "value" {}, '
                'PRIMARY KEY("owner", "key"));').format(
                    self._ine(if_not_exists), child, owner_type, key_type,
                    val_type)

    def rep_child_table(self, child, owner_type, val_type, if_not_exists=True):
        return ('CREATE TABLE {}"{}" ("owner" {}, "ordinal" INTEGER, '
                '"value" {}, PRIMARY KEY("owner", "ordinal"));').format(
                    self._ine(if_not_exists), child, owner_type, val_type)

    def rep_composed_child_table(self, child, owner_type, columns,
                                 if_not_exists=True):
        cols = "".join(', "{}" {}'.format(name, sql_type)
                       for name, sql_type in columns)
        return ('CREATE TABLE {}"{}" ("owner" {}, "ordinal" INTEGER{}, '
                'PRIMARY KEY("owner", "ordinal"));').format(
                    self._ine(if_not_exists), child, owner_type, cols)

    # -- migration ------------------------------------------------------------
    def version_table(self):
        return ('CREATE TABLE IF NOT EXISTS "_harpia_schema_version" '
                '("name" TEXT PRIMARY KEY, "version" TEXT);')

    def list_columns_sql(self, table):
        return "SELECT \"name\" FROM pragma_table_info('{}');".format(table)

    def add_column(self, table, name, column_def):
        return 'ALTER TABLE "{}" ADD COLUMN "{}" {};'.format(
            table, name, column_def)

    def rename_column(self, table, old, new):
        return 'ALTER TABLE "{}" RENAME COLUMN "{}" TO "{}";'.format(
            table, old, new)

    def drop_column_dynamic(self, table, name_expr):
        return '"ALTER TABLE \\"{}\\" DROP COLUMN \\"" + {} + "\\";"'.format(
            table, name_expr)

    def stamp_version(self, table, version):
        return ('INSERT OR REPLACE INTO "_harpia_schema_version" '
                "(\"name\", \"version\") VALUES ('{}', '{}');").format(
                    table, version)

    def list_column_types_sql(self, table):
        return ('SELECT "name", "type" FROM pragma_table_info(\'{}\');'
                .format(table))

    # -- migration: child tables (repeated / map) --------------------------
    def list_tables_sql(self, prefix):
        # every "<prefix>__*" table; substr (not LIKE, whose _ is a wildcard)
        # keeps the match exact, and the shape mirrors list_columns_sql --
        # one selected column, read uniformly by the migration C++.
        n = len(prefix) + 2
        return ("SELECT \"name\" FROM sqlite_master WHERE type = 'table' "
                "AND substr(\"name\", 1, {}) = '{}__';").format(n, prefix)

    def rename_table(self, old, new):
        return 'ALTER TABLE "{}" RENAME TO "{}";'.format(old, new)

    def drop_table_dynamic(self, name_expr):
        return '"DROP TABLE \\"" + {} + "\\";"'.format(name_expr)

    def retype_rep_child_dynamic(self, child, owner_type, val_sql):
        # No ALTER COLUMN ... TYPE in SQLite: rebuild the (owner, ordinal,
        # value) child table with "value" at the current element type,
        # CASTing every row across. Guarded by the child's live "value" type
        # so an already-current table is untouched.
        types_sql = self.list_column_types_sql(child)
        tmp = "{}__retype_tmp".format(child)
        create_sql = ('CREATE TABLE "{}" ("owner" {}, "ordinal" INTEGER, '
                      '"value" {}, PRIMARY KEY("owner", "ordinal"));').format(
                          tmp, owner_type, val_sql)
        insert_sql = ('INSERT INTO "{}" ("owner", "ordinal", "value") SELECT '
                      '"owner", "ordinal", CAST("value" AS {}) FROM "{}";').format(
                          tmp, val_sql, child)
        drop_sql = 'DROP TABLE "{}";'.format(child)
        rename_sql = 'ALTER TABLE "{}" RENAME TO "{}";'.format(tmp, child)
        return (
            '        {{\n'
            '            std::map<std::string, std::string> _rct;\n'
            '            {{\n'
            '                std::string _rn, _rt; ::soci::indicator _rni, _rti;\n'
            '                ::soci::statement _rs = (db.prepare << "{types}",\n'
            '                                         ::soci::into(_rn, _rni), ::soci::into(_rt, _rti));\n'
            '                _rs.execute();\n'
            '                while (_rs.fetch()) {{ if (_rni == ::soci::i_ok && _rti == ::soci::i_ok) _rct[_rn] = _rt; }}\n'
            '            }}\n'
            '            if (_rct.count("value") && _rct["value"] != "{val}") {{\n'
            '                db << "{create}";\n'
            '                db << "{insert}";\n'
            '                db << "{drop}";\n'
            '                db << "{rename}";\n'
            '            }}\n'
            '        }}'
        ).format(types=_esc(types_sql), val=val_sql, create=_esc(create_sql),
                 insert=_esc(insert_sql), drop=_esc(drop_sql),
                 rename=_esc(rename_sql))

    def retype_column_dynamic(self, table, columns):
        # SQLite has no ALTER COLUMN ... TYPE at all, so a real type change
        # needs a whole-table rebuild: create a tmp table with the CURRENT
        # schema, copy every row across with a CAST per column, drop the old
        # table, rename the tmp one into place. Only worth doing when at
        # least one column's live type actually differs -- one bool guards
        # the whole block, checked against every column up front.
        columns = list(columns)
        checks = "\n".join(
            '            if (have_types.count("{n}") && have_types["{n}"] '
            '!= "{t}") _needs_retype = true;'.format(n=name, t=sql_type)
            for name, sql_type, _column_def in columns)
        tmp = "{}__retype_tmp".format(table)
        create_sql = self.create_table(
            tmp, [(name, column_def) for name, _sql_type, column_def in columns],
            if_not_exists=False)
        col_list = ", ".join('"{}"'.format(name) for name, _, _ in columns)
        select_list = ", ".join(
            'CAST("{}" AS {})'.format(name, sql_type)
            for name, sql_type, _ in columns)
        insert_sql = 'INSERT INTO "{}" ({}) SELECT {} FROM "{}";'.format(
            tmp, col_list, select_list, table)
        drop_sql = self.drop_table(table, if_exists=False)
        rename_sql = 'ALTER TABLE "{}" RENAME TO "{}";'.format(tmp, table)
        return (
            '        bool _needs_retype = false;\n'
            '{checks}\n'
            '        if (_needs_retype) {{\n'
            '            db << "{create}";\n'
            '            db << "{insert}";\n'
            '            db << "{drop}";\n'
            '            db << "{rename}";\n'
            '        }}'
        ).format(checks=checks, create=_esc(create_sql), insert=_esc(insert_sql),
                 drop=_esc(drop_sql), rename=_esc(rename_sql))


if __name__ == "__main__":
    # Eyeball aid: `python3 -m Database.backends.sqlite` prints representative
    # DDL so the abstraction's output can be checked against today's strings.
    b = SqliteBackend()
    print("# backend:", b, "soci_backend_symbol:", b.soci_backend_symbol)
    print(b.create_table("devices", [
        ("ID_abc", b.column_def(b.sql_type("INT32"), pk=True)),
        ("devname", b.column_def(b.sql_type("STRING"), required=True)),
        ("serial", b.column_def(b.sql_type("STRING"), unique=True)),
        ("weight", b.column_def(b.sql_type("FLOAT"))),
        ("profile", b.column_def(b.int_type)),          # enum / FK column
    ]))
    print(b.map_child_table("devices__labels", b.int_type, "TEXT", "TEXT"))
    print(b.rep_child_table("devices__tags", b.int_type, "TEXT"))
    print(b.drop_table("devices"))
    print(b.version_table())
    print(b.list_columns_sql("devices"))
    print(b.add_column("devices", "nickname", b.column_def(b.sql_type("STRING"))))
    print(b.rename_column("devices", "nickname", "label"))
    print(b.drop_column_dynamic("devices", "_dc"))
    print(b.stamp_version("devices", "c96f8fd7"))
    print(b.list_column_types_sql("devices"))
    print(b.retype_column_dynamic("devices", [
        ("ID_abc", b.int_type, b.column_def(b.int_type, pk=True)),
        ("weight", b.sql_type("FLOAT"), b.column_def(b.sql_type("FLOAT"))),
    ]))
    print(b.list_tables_sql("devices"))
    print(b.rename_table("devices__oldtags", "devices__tags"))
    print(b.drop_table_dynamic("_dct"))
    print(b.retype_rep_child_dynamic("devices__tags", b.int_type,
                                     b.sql_type("STRING")))
