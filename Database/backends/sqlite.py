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
from Database.backends.base import DbBackend


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

    def stamp_version(self, table, version):
        return ('INSERT OR REPLACE INTO "_harpia_schema_version" '
                "(\"name\", \"version\") VALUES ('{}', '{}');").format(
                    table, version)


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
    print(b.stamp_version("devices", "c96f8fd7"))
