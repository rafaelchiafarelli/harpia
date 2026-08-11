"""PostgreSQL dialect.

The Postgres counterpart to the SQLite backend (see sqlite.py). Because the DAO
is emitted against SOCI, the entire client surface (INSERT/SELECT/UPDATE/DELETE +
binding) is identical across backends; only the SQL *dialect* below differs.

Deltas from SQLite, all grounded in Postgres semantics:
  * types: INT64 -> BIGINT, FLOAT -> DOUBLE PRECISION (SQLite folds both into
    INTEGER/REAL). INT32/BOOL stay INTEGER so the neutral C++ int bind kind still
    matches the column; STRING -> TEXT.
  * caller-assigned PK: "<type> PRIMARY KEY" (NOT SERIAL/IDENTITY) -- harpia ids
    are set by the caller and bound on INSERT, exactly like SQLite, so no
    DB-generated-id semantics are introduced.
  * introspection: information_schema.columns (SQLite uses pragma_table_info);
    both are shaped to SELECT a single column-name column, read uniformly by the
    generated migration C++.
  * version stamp: INSERT ... ON CONFLICT ("name") DO UPDATE (SQLite uses
    INSERT OR REPLACE).
Identifiers are double-quoted everywhere, which is what keeps the SQLite and
Postgres output case-compatible (Postgres folds unquoted identifiers to lower).
"""
from Database.backends.base import DbBackend


# harpia scalar token -> PostgreSQL column type. (The neutral C++ bind "kind" --
# int/int64/double/text -- stays in model.py; it is not a dialect concern.)
_TYPES = {
    "INT32":  "INTEGER",
    "INT64":  "BIGINT",
    "BOOL":   "INTEGER",            # bound as int (matches the neutral bind kind)
    "FLOAT":  "DOUBLE PRECISION",
    "STRING": "TEXT",
}


class PostgresBackend(DbBackend):
    name = "postgresql"
    soci_backend = "postgresql"

    @property
    def soci_backend_symbol(self):
        return "::soci::postgresql"

    @property
    def soci_backend_header(self):
        return "soci/postgresql/soci-postgresql.h"

    # -- types ----------------------------------------------------------------
    def sql_type(self, token):
        return _TYPES[token]

    @property
    def int_type(self):
        return "INTEGER"

    # -- columns & tables -----------------------------------------------------
    def column_def(self, sql_type, *, pk=False, required=False, unique=False):
        # caller-assigned PK -- a plain primary key, NOT SERIAL/IDENTITY (the id
        # is set by the caller and bound on INSERT, so nothing is auto-generated).
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
        return ("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '{}';").format(table)

    def add_column(self, table, name, column_def):
        return 'ALTER TABLE "{}" ADD COLUMN "{}" {};'.format(
            table, name, column_def)

    def stamp_version(self, table, version):
        return ('INSERT INTO "_harpia_schema_version" ("name", "version") '
                "VALUES ('{}', '{}') ON CONFLICT (\"name\") DO UPDATE "
                'SET "version" = EXCLUDED."version";').format(table, version)


if __name__ == "__main__":
    b = PostgresBackend()
    print("# backend:", b, "soci_backend_symbol:", b.soci_backend_symbol)
    print(b.create_table("devices", [
        ("ID_abc", b.column_def(b.sql_type("INT32"), pk=True)),
        ("devname", b.column_def(b.sql_type("STRING"), required=True)),
        ("weight", b.column_def(b.sql_type("FLOAT"))),
    ]))
    print(b.map_child_table("devices__labels", b.int_type, "TEXT", "TEXT"))
    print(b.list_columns_sql("devices"))
    print(b.stamp_version("devices", "c96f8fd7"))
