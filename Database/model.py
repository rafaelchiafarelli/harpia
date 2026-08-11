"""Shared column model for the Stage 8 database layer.

Both the schema generator (SqlAdapter) and the CRUDL generator (CrudlAdapter)
derive their columns from analyze(), so the CREATE TABLE and the INSERT/SELECT/
UPDATE always agree.

SQL dialect (column types, PRIMARY KEY syntax, CREATE TABLE) is resolved through
a DbBackend (Database/backends) rather than hard-wired, so the same model drives
SQLite / PostgreSQL / ... The backend argument defaults to SQLite everywhere, so
callers that have not yet been threaded (and today's golden output) are
unchanged. The neutral C++ bind "kind" (int/int64/double/text) lives here; only
the SQL type string is the backend's concern.
"""

from Database.backends import get_backend

# harpia scalar type -> neutral C++ bind/column "kind". The matching SQL type is
# supplied by the backend (backend.sql_type(token)); see _scalar() below.
_KINDS = {
    "INT32":  "int",
    "INT64":  "int64",
    "BOOL":   "int",
    "FLOAT":  "double",
    "STRING": "text",
}


def _scalar(token, backend):
    """(sql_type, kind) for a harpia scalar token, or None if it is not a scalar.
    Mirrors the old ``_SCALARS.get(token)`` shape so call sites are unchanged."""
    kind = _KINDS.get(token)
    if kind is None:
        return None
    return backend.sql_type(token), kind


class Column:
    def __init__(self, name, sql_type, pk=False, required=False, unique=False,
                 bindable=False, kind=None, fk_target=None, enum_type=None,
                 fk_table=False, embed=None, child_accessor=None,
                 backend=None) -> None:
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
        self.embed = list(embed) if embed else None
                                      # chain of parent field accessors when this
                                      # column is a flattened sub-field of a
                                      # (possibly nested) non-table composed field
                                      # (data.val.inner.var -> column
                                      # "val_inner_var", C++ x.val().inner().var())
        self.child_accessor = child_accessor  # the sub-field's own accessor
        self._backend = backend or get_backend()  # dialect for sql_def()

    @property
    def accessor(self):
        # protobuf C++ lowercases the field name for accessors
        return self.name.lower()

    def getter(self, src):
        """C++ expression reading this column's value from message ``src``."""
        if self.embed:
            chain = src
            for step in self.embed:
                chain = "{}.{}()".format(chain, step)
            return "{}.{}()".format(chain, self.child_accessor)
        return "{}.{}()".format(src, self.accessor)

    def set_stmt(self, value):
        """C++ statement writing ``value`` into this column's field on ``msg``."""
        if self.embed:
            chain = "msg"
            for step in self.embed:
                chain = "{}->mutable_{}()".format(chain, step)
            return "{}->set_{}({})".format(chain, self.child_accessor, value)
        return "msg->set_{}({})".format(self.accessor, value)

    def sql_def(self):
        return self._backend.column_def(
            self.sql_type, pk=self.pk, required=self.required, unique=self.unique)


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
    """A repeated field persisted as a child table "<table>__<field>" keyed by the
    parent's PK, with an ordinal column preserving insertion order. For a repeated
    scalar the "value" column holds the value; for a repeated composed field whose
    target owns a table (fk_target set) it holds the child's primary key and the
    children are created/loaded via the child DAO (a 1-to-many relationship)."""
    def __init__(self, child_table, field, val_sql, val_kind,
                 fk_target=None, embed=None) -> None:
        self.child_table = child_table
        self.field = field          # protobuf accessor of the repeated field
        self.val_sql = val_sql
        self.val_kind = val_kind
        self.fk_target = fk_target  # child message name (repeated FK) or None
        self.embed = embed          # parent field accessor if embed-nested

    def entries(self, src):
        """Const repeated-field expression on message ``src`` (for iteration)."""
        if self.embed:
            return "{}.{}().{}()".format(src, self.embed, self.field)
        return "{}.{}()".format(src, self.field)

    def add_stmt(self, value):
        """C++ statement appending ``value`` to this field on ``msg`` (pointer)."""
        if self.embed:
            return "msg->mutable_{}()->add_{}({})".format(
                self.embed, self.field, value)
        return "msg->add_{}({})".format(self.field, value)

    def add_on(self, inst, value):
        """Append ``value`` on a local value ``inst`` (dot access, for tests)."""
        if self.embed:
            return "{}.mutable_{}()->add_{}({})".format(
                inst, self.embed, self.field, value)
        return "{}.add_{}({})".format(inst, self.field, value)

    def at(self, inst, index):
        """Indexed read of element ``index`` on a local value ``inst``."""
        if self.embed:
            return "{}.{}().{}({})".format(inst, self.embed, self.field, index)
        return "{}.{}({})".format(inst, self.field, index)

    def size_of(self, inst):
        """Element-count expression on a local value ``inst``."""
        if self.embed:
            return "{}.{}().{}_size()".format(inst, self.embed, self.field)
        return "{}.{}_size()".format(inst, self.field)


class RepeatedComposedField:
    """A repeated field whose target is a table-less composed message,
    persisted as a child table "<table>__<field>" (owner, ordinal, one column
    per the target's own flattened scalar/enum fields, unprefixed -- unlike
    the singular-embed case, each repetition already gets its own row, so no
    prefix is needed to disambiguate). ``columns`` are produced by
    _flatten(..., prefix=False), so nested table-less composition and enum
    sub-fields are already resolved; map/repeated/table-composed sub-fields
    stay deferred (silently dropped, matching repeated_fields()'s existing
    deferred cases -- there is no note channel here)."""
    def __init__(self, child_table, field, columns, embed=None) -> None:
        self.child_table = child_table
        self.field = field          # protobuf accessor of the repeated field
        self.columns = columns      # list of Column, unprefixed names/accessors
        self.embed = embed          # parent field accessor if embed-nested

    def entries(self, src):
        """Const repeated-field expression on message ``src`` (for iteration)."""
        if self.embed:
            return "{}.{}().{}()".format(src, self.embed, self.field)
        return "{}.{}()".format(src, self.field)

    def add_ptr_stmt(self):
        """C++ statement returning a pointer to a newly appended element on
        ``msg`` (pointer), to be populated field-by-field by the caller."""
        if self.embed:
            return "msg->mutable_{}()->add_{}()".format(self.embed, self.field)
        return "msg->add_{}()".format(self.field)

    def size_of(self, inst):
        """Element-count expression on a local value ``inst``."""
        if self.embed:
            return "{}.{}().{}_size()".format(inst, self.embed, self.field)
        return "{}.{}_size()".format(inst, self.field)


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


def pagination_default(msg):
    """The table's declared default page size, i.e. the paginationSize of the
    first field carrying the PAGINATION modifier, or None if the message has
    none. Drives the paginated list()/streamSrc/GET-list surfaces."""
    for v in (msg.variables or []):
        mods = {m[0] for m in (v.modifiers or [])}
        if "PAGINATION" in mods:
            return v.paginationSize
    return None


def _flatten(name_prefix, child_msg, types, backend, embed_path=None, prefix=True):
    """Flatten a message's scalar/enum fields into columns.

    prefix=True (the default): columns are named with ``name_prefix``
    (compounding through nesting: data.val.inner.var -> column
    "val_inner_var") and bound through ``embed_path``, the chain of C++
    accessors from the table-bearing message down to this level
    (x.val().inner().var()) -- a table-less composed field embedded
    (possibly several levels deep) in a table-bearing message.
    prefix=False: columns keep the child message's own field names,
    unprefixed and unbound (embed_path stays empty) -- one repetition's
    worth of columns for a repeated field whose target is a table-less
    message, where each repetition already gets its own child-table row (see
    RepeatedComposedField / repeated_fields()).

    Only scalar and enum sub-fields are flattened; repeated/map and nested
    composed-to-a-table-bearing-message sub-fields are deferred with a note.
    A nested composed sub-field whose own target is ALSO a table-less
    message is flattened recursively (compounding name_prefix/embed_path)."""
    columns, notes = [], []
    if child_msg is None:
        return columns, notes
    embed_path = list(embed_path or [])
    for v in (child_msg.variables or []):
        if _is_hidden(v.name):
            continue
        col_name = "{}_{}".format(name_prefix, v.name) if prefix else v.name
        mods = {m[0] for m in (v.modifiers or [])}
        if v.typeMap:
            notes.append("-- {}.{}: map in embedded {} -> child table"
                         .format(name_prefix, v.name, child_msg.name))
            continue
        if "REPETEABLE" in mods and v.type[0] in _KINDS:
            notes.append("-- {}.{}: repeated in embedded {} -> child table"
                         .format(name_prefix, v.name, child_msg.name))
            continue
        if "REPETEABLE" in mods:
            notes.append("-- {}.{}: repeated composed in embedded {} (deferred)"
                         .format(name_prefix, v.name, child_msg.name))
            continue
        if v.type[0] == "ID":  # nested composed field inside the embedded message
            kind, nested_msg = _lookup(types, v.type[1])
            if kind == "enum":
                columns.append(Column(col_name, backend.int_type, bindable=False,
                                      kind="enum", enum_type=v.type[1],
                                      embed=(embed_path if prefix else None),
                                      child_accessor=v.name.lower(),
                                      backend=backend))
                continue
            if kind == "message":
                # nested table-less composed field: recurse, reaching further
                # scalar/enum fields (compounding name_prefix/embed_path).
                sub_cols, sub_notes = _flatten(
                    col_name if prefix else v.name, nested_msg, types, backend,
                    embed_path=(embed_path + [v.name.lower()]) if prefix else None,
                    prefix=prefix)
                columns.extend(sub_cols)
                notes.extend(sub_notes)
                continue
            notes.append("-- {}.{}: nested composed -> {} in embedded {} (deferred)"
                         .format(name_prefix, v.name, v.type[1], child_msg.name))
            continue
        scalar = _scalar(v.type[0], backend)
        if scalar is None:
            notes.append("-- {}.{}: unsupported type {} (skipped)"
                         .format(name_prefix, v.name, v.type[0]))
            continue
        sql_type, kind = scalar
        columns.append(Column(col_name, sql_type, bindable=False, kind=kind,
                              embed=(embed_path if prefix else None),
                              child_accessor=v.name.lower(),
                              backend=backend))
    return columns, notes


def analyze(msg, types=None, backend=None):
    """Return (columns, notes) for a table-bearing message.

    Scalar fields become bindable columns. A composed field whose target is an
    enum becomes a bindable INTEGER column (the enum value). A composed field
    whose target is a table-bearing message becomes a persistable FK to the
    child's primary key (fk_table). A composed field whose target is a message
    with no table is flattened: its scalar/enum sub-fields become prefixed
    columns bound through the parent (data.val.var -> column "val_var").
    Repeated/map fields are deferred with a note. ``types`` is the
    type_registry(); without it composed fields fall back to deferred FKs.
    ``backend`` selects the SQL dialect (defaults to SQLite).
    """
    types = types or {}
    backend = backend or get_backend()
    columns = []
    notes = []
    for v in (msg.variables or []):
        mods = {m[0] for m in (v.modifiers or [])}
        if v.typeMap:
            notes.append("-- {}: map -> child table (see map_fields)"
                         .format(v.name))
            continue
        if "REPETEABLE" in mods:
            if v.type[0] in _KINDS:
                notes.append("-- {}: repeated -> child table (see repeated_fields)"
                             .format(v.name))
            elif v.type[0] == "ID":
                kind, _ = _lookup(types, v.type[1])
                if kind == "table":
                    notes.append("-- {}: repeated FK -> {} link table (see "
                                 "repeated_fields)".format(v.name, v.type[1]))
                elif kind == "message":
                    notes.append("-- {}: repeated composed -> {} child table "
                                 "(see repeated_fields)".format(v.name, v.type[1]))
                else:
                    notes.append("-- {}: repeated composed -> {} (deferred)"
                                 .format(v.name, v.type[1]))
            else:
                notes.append("-- {}: repeated composed -> child table (deferred)"
                             .format(v.name))
            continue
        if v.type[0] == "ID":  # composed: message or enum reference
            target = v.type[1]
            kind, target_msg = _lookup(types, target)
            if kind == "enum":
                columns.append(Column(v.name, backend.int_type, bindable=True,
                                      kind="enum", enum_type=target,
                                      backend=backend))
                continue
            if kind == "table":
                # composed field whose target owns a table: a persistable FK to
                # the child's primary key (CrudlAdapter creates/loads the child).
                columns.append(Column(v.name, backend.int_type, bindable=False,
                                      fk_target=target, fk_table=True,
                                      backend=backend))
                continue
            if kind == "message":
                # composed field whose target has no table: flatten its scalar/
                # enum sub-fields (recursively, through further table-less
                # nesting) into prefixed columns of this table.
                sub_cols, sub_notes = _flatten(v.name, target_msg, types, backend,
                                               embed_path=[v.name.lower()])
                columns.extend(sub_cols)
                notes.extend(sub_notes)
                continue
            columns.append(Column(v.name, backend.int_type, bindable=False,
                                  fk_target=target, backend=backend))
            notes.append("-- {}: FK -> {} (deferred)".format(v.name, target))
            continue
        scalar = _scalar(v.type[0], backend)
        if scalar is None:
            notes.append("-- {}: unsupported type {} (skipped)"
                         .format(v.name, v.type[0]))
            continue
        sql_type, kind = scalar
        columns.append(Column(v.name, sql_type, pk=v.name.startswith("ID_"),
                              required="REQUIRED" in mods,
                              unique="UNIQUE" in mods,
                              bindable=True, kind=kind, backend=backend))
    return columns, notes


def _map_field(table, v, backend, embed=None):
    # map key/value types live in v.typeMap (positionally [key, value]); v.type is
    # unreliable for maps (the parser overwrites it with the value type).
    key = _scalar(v.typeMap[0][0], backend) if len(v.typeMap or []) > 0 else None
    val = _scalar(v.typeMap[1][0], backend) if len(v.typeMap or []) > 1 else None
    if not key or not val:
        return None
    path = "{}_{}".format(embed, v.name) if embed else v.name
    return MapField("{}__{}".format(table, path), v.name.lower(),
                    key[0], key[1], val[0], val[1], embed=embed)


def map_fields(msg, types=None, backend=None):
    """Map<K,V> fields of a table-bearing message, each -> a child table keyed by
    the parent's PK. Includes maps reached through a flattened non-table composed
    field (embed-nested), mirroring _flatten()'s column flattening. Repeated
    fields are handled separately."""
    types = types or {}
    backend = backend or get_backend()
    table = getattr(msg, "tableName", None)
    if not table:
        return []
    out = []
    for v in (msg.variables or []):
        if v.typeMap:
            mf = _map_field(table, v, backend)
            if mf is not None:
                out.append(mf)
            continue
        if v.type[0] == "ID":  # composed: may embed a table-less message with maps
            kind, target_msg = _lookup(types, v.type[1])
            if kind == "message" and target_msg is not None:
                for cv in (target_msg.variables or []):
                    if _is_hidden(cv.name) or not cv.typeMap:
                        continue
                    mf = _map_field(table, cv, backend, embed=v.name.lower())
                    if mf is not None:
                        out.append(mf)
    return out


def repeated_fields(msg, types=None, backend=None):
    """Repeated scalar fields of a table-bearing message, each -> a child table
    keyed by the parent's PK with an ordinal. A repeated composed field whose
    target owns a table -> a link table via the child's own DAO (RepeatedField,
    fk_target set); whose target has no table -> a child table holding one
    column per the target's own flattened scalar/enum fields
    (RepeatedComposedField). Repeated enums stay deferred (noted by analyze)."""
    types = types or {}
    backend = backend or get_backend()
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
        child = "{}__{}".format(table, v.name)
        if v.type[0] == "ID":  # repeated composed field
            kind, target_msg = _lookup(types, v.type[1])
            if kind == "table":
                # 1-to-many: the link table's value is the child's primary key
                out.append(RepeatedField(child, v.name.lower(), backend.int_type,
                                         "int64", fk_target=v.type[1]))
            elif kind == "message":
                cols, _notes = _flatten(v.name, target_msg, types, backend,
                                        prefix=False)
                if cols:
                    out.append(RepeatedComposedField(child, v.name.lower(), cols))
            # repeated enum -> deferred
            continue
        scalar = _scalar(v.type[0], backend)
        if scalar is None:
            continue
        out.append(RepeatedField(child, v.name.lower(), scalar[0], scalar[1]))
    # repeated scalar fields reached through a flattened non-table composed field
    # (embed-nested), mirroring map_fields; keyed by the parent's PK.
    for v in (msg.variables or []):
        if v.typeMap or v.type[0] != "ID":
            continue
        kind, target_msg = _lookup(types, v.type[1])
        if kind != "message" or target_msg is None:
            continue
        for cv in (target_msg.variables or []):
            if _is_hidden(cv.name) or cv.typeMap:
                continue
            cmods = {m[0] for m in (cv.modifiers or [])}
            if "REPETEABLE" not in cmods or cv.type[0] == "ID":
                continue
            scalar = _scalar(cv.type[0], backend)
            if scalar is None:
                continue
            out.append(RepeatedField(
                "{}__{}_{}".format(table, v.name.lower(), cv.name),
                cv.name.lower(), scalar[0], scalar[1],
                embed=v.name.lower()))
    return out


def create_table_sql(msg, if_not_exists=True, types=None, backend=None):
    """Compact single-line CREATE TABLE (for embedding in generated C++)."""
    backend = backend or get_backend()
    columns, _ = analyze(msg, types, backend)
    return backend.create_table(
        msg.tableName,
        [(c.name, c.sql_def()) for c in columns],
        if_not_exists=if_not_exists)
