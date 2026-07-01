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


class MapField:
    """A map<K,V> field persisted as a child table keyed by the parent's PK.

    Direct map:       child table "<table>__<field>".
    Embed-nested map: child table "<table>__<embed>_<field>" -- the map lives on a
                      flattened non-table composed field, reached via msg.<embed>()
                      (mirrors how _flatten() flattens that message's scalars).
    """
    def __init__(self, child_table, field, key_sql, key_kind, val_sql, val_kind,
                 embed=None) -> None:
        self.child_table = child_table
        self.field = field          # protobuf accessor of the map field
        self.key_sql = key_sql
        self.key_kind = key_kind    # int | int64 | double | text
        self.val_sql = val_sql
        self.val_kind = val_kind
        self.embed = embed          # parent field accessor if embed-nested

    def entries(self, src):
        """Const map expression on message ``src`` (for iteration)."""
        if self.embed:
            return "{}.{}().{}()".format(src, self.embed, self.field)
        return "{}.{}()".format(src, self.field)

    def mutable(self):
        """Mutable map pointer expression on ``msg`` (for population)."""
        if self.embed:
            return "msg->mutable_{}()->mutable_{}()".format(self.embed, self.field)
        return "msg->mutable_{}()".format(self.field)

    def mutable_on(self, inst):
        """Mutable map pointer on a local value ``inst`` (dot access)."""
        if self.embed:
            return "{}.mutable_{}()->mutable_{}()".format(inst, self.embed, self.field)
        return "{}.mutable_{}()".format(inst, self.field)


class RepeatedField:
    """A repeated scalar field persisted as a child table "<table>__<field>" keyed
    by the parent's PK, with an ordinal column preserving insertion order."""
    def __init__(self, child_table, field, val_sql, val_kind) -> None:
        self.child_table = child_table
        self.field = field          # protobuf accessor of the repeated field
        self.val_sql = val_sql
        self.val_kind = val_kind

    def entries(self, src):
        """Const repeated-field expression on message ``src`` (for iteration)."""
        return "{}.{}()".format(src, self.field)

    def add_on(self, inst, value):
        """Append ``value`` on a local value ``inst`` (dot access, for tests)."""
        return "{}.add_{}({})".format(inst, self.field, value)


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
        if v.typeMap:
            notes.append("-- {}.{}: map in embedded {} -> child table"
                         .format(parent, v.name, child_msg.name))
            continue
        if "REPETEABLE" in mods:
            notes.append("-- {}.{}: repeated in embedded {} (deferred)"
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
        if v.typeMap:
            notes.append("-- {}: map -> child table (see map_fields)"
                         .format(v.name))
            continue
        if "REPETEABLE" in mods:
            if _SCALARS.get(v.type[0]) is not None:
                notes.append("-- {}: repeated -> child table (see repeated_fields)"
                             .format(v.name))
            else:
                notes.append("-- {}: repeated composed -> child table (deferred)"
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


def _map_field(table, v, embed=None):
    # map key/value types live in v.typeMap (positionally [key, value]); v.type is
    # unreliable for maps (the parser overwrites it with the value type).
    key = _SCALARS.get(v.typeMap[0][0]) if len(v.typeMap or []) > 0 else None
    val = _SCALARS.get(v.typeMap[1][0]) if len(v.typeMap or []) > 1 else None
    if not key or not val:
        return None
    path = "{}_{}".format(embed, v.name) if embed else v.name
    return MapField("{}__{}".format(table, path), v.name.lower(),
                    key[0], key[1], val[0], val[1], embed=embed)


def map_fields(msg, types=None):
    """Map<K,V> fields of a table-bearing message, each -> a child table keyed by
    the parent's PK. Includes maps reached through a flattened non-table composed
    field (embed-nested), mirroring _flatten()'s column flattening. Repeated
    fields are handled separately."""
    types = types or {}
    table = getattr(msg, "tableName", None)
    if not table:
        return []
    out = []
    for v in (msg.variables or []):
        if v.typeMap:
            mf = _map_field(table, v)
            if mf is not None:
                out.append(mf)
            continue
        if v.type[0] == "ID":  # composed: may embed a table-less message with maps
            kind, target_msg = _lookup(types, v.type[1])
            if kind == "message" and target_msg is not None:
                for cv in (target_msg.variables or []):
                    if _is_hidden(cv.name) or not cv.typeMap:
                        continue
                    mf = _map_field(table, cv, embed=v.name.lower())
                    if mf is not None:
                        out.append(mf)
    return out


def repeated_fields(msg, types=None):
    """Repeated scalar fields of a table-bearing message, each -> a child table
    keyed by the parent's PK with an ordinal. Repeated composed fields are
    deferred (noted by analyze)."""
    types = types or {}
    table = getattr(msg, "tableName", None)
    if not table:
        return []
    out = []
    for v in (msg.variables or []):
        if v.typeMap:
            continue
        mods = {m[0] for m in (v.modifiers or [])}
        if "REPETEABLE" not in mods:
            continue
        scalar = _SCALARS.get(v.type[0])
        if scalar is None:
            continue  # repeated composed -> deferred
        out.append(RepeatedField("{}__{}".format(table, v.name), v.name.lower(),
                                 scalar[0], scalar[1]))
    return out


def create_table_sql(msg, if_not_exists=True, types=None):
    """Compact single-line CREATE TABLE (for embedding in generated C++)."""
    columns, _ = analyze(msg, types)
    cols = ", ".join('"{}" {}'.format(c.name, c.sql_def()) for c in columns)
    ine = "IF NOT EXISTS " if if_not_exists else ""
    return 'CREATE TABLE {}"{}" ({});'.format(ine, msg.tableName, cols)
