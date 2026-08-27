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
from Database.backends.base import DbBackend, _esc


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

    def rename_column(self, table, old, new):
        return 'ALTER TABLE "{}" RENAME COLUMN "{}" TO "{}";'.format(
            table, old, new)

    def drop_column_dynamic(self, table, name_expr):
        return '"ALTER TABLE \\"{}\\" DROP COLUMN \\"" + {} + "\\";"'.format(
            table, name_expr)

    def stamp_version(self, table, version):
        return ('INSERT INTO "_harpia_schema_version" ("name", "version") '
                "VALUES ('{}', '{}') ON CONFLICT (\"name\") DO UPDATE "
                'SET "version" = EXCLUDED."version";').format(table, version)

    def list_column_types_sql(self, table):
        return ("SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = '{}';").format(table)

    # -- migration: child tables (repeated / map) --------------------------
    def list_tables_sql(self, prefix):
        # every "<prefix>__*" table; substr (not LIKE, whose _ is a wildcard)
        # keeps the match exact, and the shape mirrors list_columns_sql.
        n = len(prefix) + 2
        return ("SELECT table_name FROM information_schema.tables "
                "WHERE substr(table_name, 1, {}) = '{}__';").format(n, prefix)

    def rename_table(self, old, new):
        return 'ALTER TABLE "{}" RENAME TO "{}";'.format(old, new)

    def drop_table_dynamic(self, name_expr):
        return '"DROP TABLE \\"" + {} + "\\";"'.format(name_expr)

    def retype_rep_child_dynamic(self, child, owner_type, val_sql):
        # Postgres has a direct ALTER COLUMN ... TYPE, so the (owner, ordinal,
        # value) child table's "value" column is fixed in place, guarded by
        # its live type. information_schema.columns.data_type reports the
        # canonical lower-case name, exactly as in retype_column_dynamic.
        types_sql = self.list_column_types_sql(child)
        alter_sql = ('ALTER TABLE "{}" ALTER COLUMN "value" TYPE {} '
                     'USING "value"::{};').format(child, val_sql, val_sql)
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
            '            if (_rct.count("value") && _rct["value"] != "{val_lc}") {{\n'
            '                db << "{alter}";\n'
            '            }}\n'
            '        }}'
        ).format(types=_esc(types_sql), val_lc=val_sql.lower(),
                 alter=_esc(alter_sql))

    def retype_map_child_dynamic(self, child, owner_type, key_sql, val_sql):
        # As retype_rep_child_dynamic, for a (owner, key, value) map child
        # table: guard the key and the value column independently. Altering
        # the type of "key" (part of PRIMARY KEY(owner, key)) is fine in
        # Postgres -- it transparently rebuilds the backing index.
        types_sql = self.list_column_types_sql(child)
        key_alter = ('ALTER TABLE "{}" ALTER COLUMN "key" TYPE {} '
                     'USING "key"::{};').format(child, key_sql, key_sql)
        val_alter = ('ALTER TABLE "{}" ALTER COLUMN "value" TYPE {} '
                     'USING "value"::{};').format(child, val_sql, val_sql)
        return (
            '        {{\n'
            '            std::map<std::string, std::string> _mct;\n'
            '            {{\n'
            '                std::string _mn, _mt; ::soci::indicator _mni, _mti;\n'
            '                ::soci::statement _ms = (db.prepare << "{types}",\n'
            '                                         ::soci::into(_mn, _mni), ::soci::into(_mt, _mti));\n'
            '                _ms.execute();\n'
            '                while (_ms.fetch()) {{ if (_mni == ::soci::i_ok && _mti == ::soci::i_ok) _mct[_mn] = _mt; }}\n'
            '            }}\n'
            '            if (_mct.count("key") && _mct["key"] != "{key_lc}") {{\n'
            '                db << "{key_alter}";\n'
            '            }}\n'
            '            if (_mct.count("value") && _mct["value"] != "{val_lc}") {{\n'
            '                db << "{val_alter}";\n'
            '            }}\n'
            '        }}'
        ).format(types=_esc(types_sql), key_lc=key_sql.lower(),
                 val_lc=val_sql.lower(), key_alter=_esc(key_alter),
                 val_alter=_esc(val_alter))

    def retype_column_dynamic(self, table, columns):
        # Postgres has a direct ALTER COLUMN ... TYPE, so (unlike SQLite) each
        # column is fixed independently, guarded by its own live-type check.
        # information_schema.columns.data_type reports Postgres's canonical
        # lower-case type name ("integer", "double precision", ...), which is
        # exactly our declared sql_type lowercased -- that's what the guard
        # compares have_types[name] against.
        lines = []
        for name, sql_type, _column_def in columns:
            alter_sql = (
                'ALTER TABLE "{t}" ALTER COLUMN "{n}" TYPE {st} '
                'USING "{n}"::{st};'
            ).format(t=table, n=name, st=sql_type)
            lines.append(
                '        if (have_types.count("{n}") && have_types["{n}"] '
                '!= "{et}") {{\n'
                '            db << "{alter}";\n'
                '        }}'.format(n=name, et=sql_type.lower(),
                                    alter=_esc(alter_sql)))
        return "\n".join(lines)


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
    print(b.retype_map_child_dynamic("devices__labels", b.int_type,
                                     b.sql_type("STRING"), b.sql_type("INT32")))
