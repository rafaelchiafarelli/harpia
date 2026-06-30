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
                 fk_table=False, embed=None, child_accessor=None) -> None:
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
        self.embed = embed            # parent field accessor when this column is a
                                      # flattened sub-field of a non-table composed
                                      # field (data.val.var -> column "val_var")
        self.child_accessor = child_accessor  # the sub-field's own accessor

    @property
    def accessor(self):
        # protobuf C++ lowercases the field name for accessors
        return self.name.lower()

    def getter(self, src):
        """C++ expression reading this column's value from message ``src``."""
        if self.embed:
            return "{}.{}().{}()".format(src, self.embed, self.child_accessor)
        return "{}.{}()".format(src, self.accessor)

    def set_stmt(self, value):
        """C++ statement writing ``value`` into this column's field on ``msg``."""
        if self.embed:
            return "msg->mutable_{}()->set_{}({})".format(
                self.embed, self.child_accessor, value)
        return "msg->set_{}({})".format(self.accessor, value)

    def sql_def(self):
        if self.pk:
            return "{} PRIMARY KEY".format(self.sql_type)
        parts = [self.sql_type]
        if self.required:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        return " ".join(parts)


# field names the front-end injects into every message; meaningless when a
# message is embedded inside another, so flattening skips them.
_HIDDEN_PREFIXES = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")


def _is_hidden(name):
    return name.startswith(_HIDDEN_PREFIXES)


def type_registry(messages):
    """Map every declared type name to its kind and definition so analyze() can
    tell an enum reference from a message reference (and a message that owns a
    table from one that does not), and reach a non-table message's fields to
    flatten them. Each entry is ``{"kind": ..., "msg": <Message>}``."""
    reg = {}
    for m in (messages or []):
        if getattr(m, "isEnum", False):
            kind = "enum"
        elif getattr(m, "tableName", None):
            kind = "table"
        else:
            kind = "message"
        reg[m.name] = {"kind": kind, "msg": m}
    return reg


def _lookup(types, name):
    """(kind, msg) for a declared type name, or (None, None) if unknown."""
    entry = (types or {}).get(name)
    if entry is None:
        return None, None
    return entry["kind"], entry["msg"]


def _flatten(parent, child_msg, types):
    """Flatten a non-table composed field's child message into columns prefixed
    with the parent field name (data.val.var -> column "val_var"). Only scalar
    and enum sub-fields are flattened; repeated/map and nested composed
    sub-fields are deferred with a note."""
    columns, notes = [], []
    if child_msg is None:
        return columns, notes
    for v in (child_msg.variables or []):
        if _is_hidden(v.name):
            continue
        col_name = "{}_{}".format(parent, v.name)
        mods = {m[0] for m in (v.modifiers or [])}
        if v.typeMap or "REPETEABLE" in mods:
            notes.append("-- {}.{}: repeated/map in embedded {} (deferred)"
                         .format(parent, v.name, child_msg.name))
            continue
        if v.type[0] == "ID":  # nested composed field inside the embedded message
            kind, _ = _lookup(types, v.type[1])
            if kind == "enum":
                columns.append(Column(col_name, "INTEGER", bindable=False,
                                      kind="enum", enum_type=v.type[1],
                                      embed=parent, child_accessor=v.name.lower()))
                continue
            notes.append("-- {}.{}: nested composed -> {} in embedded {} (deferred)"
                         .format(parent, v.name, v.type[1], child_msg.name))
            continue
        scalar = _SCALARS.get(v.type[0])
        if scalar is None:
            notes.append("-- {}.{}: unsupported type {} (skipped)"
                         .format(parent, v.name, v.type[0]))
            continue
        sql_type, kind = scalar
        columns.append(Column(col_name, sql_type, bindable=False, kind=kind,
                              embed=parent, child_accessor=v.name.lower()))
    return columns, notes


def analyze(msg, types=None):
    """Return (columns, notes) for a table-bearing message.

    Scalar fields become bindable columns. A composed field whose target is an
    enum becomes a bindable INTEGER column (the enum value). A composed field
    whose target is a table-bearing message becomes a persistable FK to the
    child's primary key (fk_table). A composed field whose target is a message
    with no table is flattened: its scalar/enum sub-fields become prefixed
    columns bound through the parent (data.val.var -> column "val_var").
    Repeated/map fields are deferred with a note. ``types`` is the
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
            kind, target_msg = _lookup(types, target)
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
            if kind == "message":
                # composed field whose target has no table: flatten its scalar/
                # enum sub-fields into prefixed columns of this table.
                sub_cols, sub_notes = _flatten(v.name, target_msg, types)
                columns.extend(sub_cols)
                notes.extend(sub_notes)
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
