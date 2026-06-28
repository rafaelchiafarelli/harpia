"""Shared column model for the Stage 8 database layer.

Both the schema generator (SqlAdapter) and the CRUDL generator (CrudlAdapter)
derive their columns from analyze(), so the CREATE TABLE and the INSERT/SELECT/
UPDATE always agree.
"""

# harpia scalar type -> (SQLite type, C++ bind/column "kind")
_SCALARS = {
    "INT32":  ("INTEGER", "int"),
    "INT64":  ("INTEGER", "int64"),
    "BOOL":   ("INTEGER", "int"),
    "FLOAT":  ("REAL", "double"),
    "STRING": ("TEXT", "text"),
}


class Column:
    def __init__(self, name, sql_type, pk=False, required=False, unique=False,
                 bindable=False, kind=None, fk_target=None) -> None:
        self.name = name
        self.sql_type = sql_type
        self.pk = pk
        self.required = required
        self.unique = unique
        self.bindable = bindable      # can the DAO bind/extract it from the message
        self.kind = kind              # int | int64 | double | text  (bindable only)
        self.fk_target = fk_target    # message/enum name for composed fields

    @property
    def accessor(self):
        # protobuf C++ lowercases the field name for accessors
        return self.name.lower()

    def sql_def(self):
        if self.pk:
            return "{} PRIMARY KEY".format(self.sql_type)
        parts = [self.sql_type]
        if self.required:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        return " ".join(parts)


def analyze(msg):
    """Return (columns, notes) for a table-bearing message.

    Scalar fields become bindable columns; composed (message/enum) fields become
    a non-bindable INTEGER FK column; repeated/map and unsupported fields are
    skipped with a note. Notes are SQL comment lines, in field order.
    """
    columns = []
    notes = []
    for v in (msg.variables or []):
        mods = {m[0] for m in (v.modifiers or [])}
        if v.typeMap or "REPETEABLE" in mods:
            notes.append("-- {}: repeated/map -> separate table (deferred)"
                         .format(v.name))
            continue
        if v.type[0] == "ID":  # composed: message or enum reference
            columns.append(Column(v.name, "INTEGER", bindable=False,
                                  fk_target=v.type[1]))
            notes.append("-- {}: FK -> {} (deferred)".format(v.name, v.type[1]))
            continue
        scalar = _SCALARS.get(v.type[0])
        if scalar is None:
            notes.append("-- {}: unsupported type {} (skipped)"
                         .format(v.name, v.type[0]))
            continue
        sql_type, kind = scalar
        columns.append(Column(v.name, sql_type, pk=v.name.startswith("ID_"),
                              required="REQUIRED" in mods,
                              unique="UNIQUE" in mods,
                              bindable=True, kind=kind))
    return columns, notes


def create_table_sql(msg, if_not_exists=True):
    """Compact single-line CREATE TABLE (for embedding in generated C++)."""
    columns, _ = analyze(msg)
    cols = ", ".join('"{}" {}'.format(c.name, c.sql_def()) for c in columns)
    ine = "IF NOT EXISTS " if if_not_exists else ""
    return 'CREATE TABLE {}"{}" ({});'.format(ine, msg.tableName, cols)
