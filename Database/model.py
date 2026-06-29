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
                 bindable=False, kind=None, fk_target=None, enum_type=None,
                 fk_table=False) -> None:
        self.name = name
        self.sql_type = sql_type
        self.pk = pk
        self.required = required
        self.unique = unique
        self.bindable = bindable      # can the DAO bind/extract it from the message
        self.kind = kind              # int | int64 | double | text | enum (bindable)
        self.fk_target = fk_target    # message/enum name for composed fields
        self.enum_type = enum_type    # C++ enum type name (kind == "enum")
        self.fk_table = fk_table      # composed field whose target is a table (a
                                      # persistable FK to the child's primary key)

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


def type_registry(messages):
    """Map every declared type name to its kind so analyze() can tell an enum
    reference from a message reference (and a message that owns a table from one
    that does not)."""
    reg = {}
    for m in (messages or []):
        if getattr(m, "isEnum", False):
            reg[m.name] = "enum"
        elif getattr(m, "tableName", None):
            reg[m.name] = "table"
        else:
            reg[m.name] = "message"
    return reg


def analyze(msg, types=None):
    """Return (columns, notes) for a table-bearing message.

    Scalar fields become bindable columns. A composed field whose target is an
    enum becomes a bindable INTEGER column (the enum value). A composed field
    whose target is a table-bearing message becomes a persistable FK to the
    child's primary key (fk_table). Other composed fields (message without a
    table) and repeated/map fields are deferred with a note. ``types`` is the
    type_registry(); without it composed fields fall back to deferred FKs.
    """
    types = types or {}
    columns = []
    notes = []
    for v in (msg.variables or []):
        mods = {m[0] for m in (v.modifiers or [])}
        if v.typeMap or "REPETEABLE" in mods:
            notes.append("-- {}: repeated/map -> separate table (deferred)"
                         .format(v.name))
            continue
        if v.type[0] == "ID":  # composed: message or enum reference
            target = v.type[1]
            kind = types.get(target)
            if kind == "enum":
                columns.append(Column(v.name, "INTEGER", bindable=True,
                                      kind="enum", enum_type=target))
                continue
            if kind == "table":
                # composed field whose target owns a table: a persistable FK to
                # the child's primary key (CrudlAdapter creates/loads the child).
                columns.append(Column(v.name, "INTEGER", bindable=False,
                                      fk_target=target, fk_table=True))
                continue
            columns.append(Column(v.name, "INTEGER", bindable=False,
                                  fk_target=target))
            notes.append("-- {}: FK -> {} (deferred)".format(v.name, target))
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


def create_table_sql(msg, if_not_exists=True, types=None):
    """Compact single-line CREATE TABLE (for embedding in generated C++)."""
    columns, _ = analyze(msg, types)
    cols = ", ".join('"{}" {}'.format(c.name, c.sql_def()) for c in columns)
    ine = "IF NOT EXISTS " if if_not_exists else ""
    return 'CREATE TABLE {}"{}" ({});'.format(ine, msg.tableName, cols)
