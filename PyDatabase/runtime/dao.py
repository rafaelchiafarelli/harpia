"""The CRUDL engine every generated Python DAO runs on.

A generated ``harpia_generated/db/<name>_<hash>_dao.py`` subclasses
:class:`Dao` and declares only data: the message class, the table, the
column map and the exact SQL (DDL from the same ``DbBackend`` the C++ and
Java targets use, statements with the dialect's DB-API placeholder). This
module turns that into ``create_table`` / ``drop_table`` / ``create`` /
``read`` / ``update`` / ``remove`` / ``list``.

Conventions, matching the C++ DAO (``Database/CrudlAdapter.py``):

- The primary key is caller-assigned: the message's ``ID_<hash>`` field is
  bound explicitly on insert.
- A SQL ``NULL`` reads back as the field's default.
- ``read`` sets the stored fields on the message it is given (it does not
  clear the rest first).
- Map / repeated fields live in child tables keyed by the parent's primary
  key (``owner``): written after the main row, deleted and re-inserted on
  update, read back in ``ordinal`` order after the main row (by ``read``
  and ``list``), deleted by ``remove``. A repeated field of a table-bearing
  message stores each child's key and persists the children through their
  own DAO.

- A composed field whose target owns a table is an FK column holding the
  child's primary key: on create/update a present child is written through
  its own DAO first; on read a non-zero key loads it, a zero key leaves it
  absent. ``remove`` does not cascade to FK children (same as C++).

Different from C++ on purpose: real database errors propagate as
exceptions; a ``bool`` only answers "did a row exist / was one affected".
Every call is one transaction, children included: committed on success,
rolled back on error.
"""
import builtins
import importlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Protocol, TypeVar, cast

from google.protobuf.message import Message

from harpia_runtime.db.bind import bind_value, extract_value, from_db, to_db


class Cursor(Protocol):
    """The DB-API 2.0 cursor surface the DAOs use."""

    rowcount: int

    def execute(self, sql: str, params: Sequence[Any] = ...) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> builtins.list[Any]: ...


class Connection(Protocol):
    """The DB-API 2.0 connection surface the DAOs use (``sqlite3``,
    ``psycopg``)."""

    def cursor(self) -> Any: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class Column:
    """One table column and where its value lives in the message.

    Attributes:
        name: The SQL column name.
        path: Attribute names from the table's message down to the scalar
            or enum field (one element for a top-level field). Several
            elements for a flattened sub-field of a table-less composed
            field (``("path", "start", "city")``).
        fk: For a composed field whose target owns a table, the child's
            generated DAO as ``"module:Class"``. The column then holds the
            child's primary key; ``path`` ends at the composed field.
        phi: The field is tagged ``phi``: a ``PhiDao``
            (``harpia_runtime.db.phi``) stores it encrypted.
    """

    name: str
    path: tuple[str, ...]
    fk: str | None = None
    phi: bool = False


@dataclass(frozen=True)
class ChildTable:
    """A child table keyed by the parent's primary key (``owner``).

    Attributes:
        kind: ``"map"`` (``owner, key, value``), ``"repeated"`` (``owner,
            ordinal, value``; ``fk`` set for a repeated field of a
            table-bearing message: the value is each child's key) or
            ``"composed"`` (``owner, ordinal`` + one column per flattened
            field of a table-less element type).
        path: Attribute names from the table's message to the map/repeated
            field (two elements for an embed-nested one).
        insert_sql: ``INSERT`` of one entry/element.
        select_sql: ``SELECT`` of an owner's entries (``ORDER BY ordinal``).
        delete_sql: ``DELETE`` of an owner's entries.
        fk: The child DAO (``"module:Class"``) of a repeated FK.
        columns: The per-element columns of a ``"composed"`` table, paths
            relative to the element.
    """

    kind: str
    path: tuple[str, ...]
    insert_sql: str
    select_sql: str
    delete_sql: str
    fk: str | None = None
    columns: tuple[Column, ...] = ()


M = TypeVar("M", bound=Message)

#: the LIMIT bound for an open-ended page (valid on SQLite and PostgreSQL)
_NO_LIMIT = (1 << 63) - 1


def _owner(msg: Message, path: tuple[str, ...], mutable: bool) -> Message:
    for step in path[:-1]:
        msg = getattr(msg, step)
        if mutable:
            msg.SetInParent()
    return msg


_DAO_CLASSES: dict[str, type["Dao[Any]"]] = {}


def dao_class(ref: str) -> type["Dao[Any]"]:
    """Resolve a ``"module:Class"`` DAO reference (imported lazily, so two
    DAOs may refer to each other)."""
    cls = _DAO_CLASSES.get(ref)
    if cls is None:
        module, _, name = ref.partition(":")
        cls = cast("type[Dao[Any]]", getattr(importlib.import_module(module), name))
        _DAO_CLASSES[ref] = cls
    return cls


def _child(msg: Message, col: Column) -> Message:
    child: Message = getattr(_owner(msg, col.path, False), col.path[-1])
    return child


def _has_child(msg: Message, col: Column) -> bool:
    return bool(_owner(msg, col.path, False).HasField(col.path[-1]))


def column_value(msg: Message, col: Column) -> Any:
    """The DB-API parameter for ``col`` read from ``msg`` (an FK column binds
    the child's primary key, ``0`` when the child is absent, like C++)."""
    if col.fk is not None:
        return bind_value(_child(msg, col), dao_class(col.fk).PK)
    return bind_value(_owner(msg, col.path, False), col.path[-1])


def set_column(msg: Message, col: Column, value: Any) -> None:
    """Store a fetched value for ``col`` into ``msg``."""
    extract_value(value, _owner(msg, col.path, True), col.path[-1])


class Dao(Generic[M]):
    """Base class of every generated DAO (see the module docstring)."""

    MESSAGE: ClassVar[type[Message]]
    TABLE: ClassVar[str]
    PK: ClassVar[str]
    #: insert/select order; the primary key is one of them
    COLUMNS: ClassVar[tuple[Column, ...]]
    #: map / repeated child tables, in C++ write/read order
    CHILDREN: ClassVar[tuple[ChildTable, ...]] = ()
    CREATE_TABLE_SQL: ClassVar[tuple[str, ...]]
    DROP_TABLE_SQL: ClassVar[tuple[str, ...]]
    INSERT_SQL: ClassVar[str]
    SELECT_SQL: ClassVar[str]
    UPDATE_SQL: ClassVar[str]
    DELETE_SQL: ClassVar[str]
    LIST_SQL: ClassVar[str]
    LIST_PAGE_SQL: ClassVar[str]

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    # -- hooks (identity / no-op here; ``harpia_runtime.db.phi.PhiDao``
    # -- encrypts, decrypts and audits ``phi`` columns through them) ---------
    def _bind(self, msg: M, col: Column) -> Any:
        """The DB-API parameter for ``col``."""
        return column_value(msg, col)

    def _load(self, msg: M, col: Column, value: Any) -> None:
        """Store the fetched ``value`` of a non-FK column into ``msg``."""
        set_column(msg, col, value)

    def _audit(self, op: str) -> None:
        """Called once per CRUDL operation (``create`` / ``read`` /
        ``update`` / ``remove`` / ``list``), at the point C++ audits it."""

    # -- plumbing -------------------------------------------------------------
    @contextmanager
    def _tx(self) -> Iterator[Any]:
        cur = self.conn.cursor()
        try:
            yield cur
        except BaseException:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    def _new(self) -> M:
        return cast(M, self.MESSAGE())

    def _pk_value(self, msg: M) -> Any:
        return bind_value(msg, self.PK)

    def _load_row(self, cur: Any, row: Sequence[Any], msg: M) -> None:
        for col, value in zip(self.COLUMNS, row, strict=False):
            if col.fk is None:
                self._load(msg, col, value)
            elif value:
                # a non-zero key: load the child through its own DAO; a zero
                # key means the child was absent (no phantom child)
                sub: Message = getattr(_owner(msg, col.path, True), col.path[-1])
                sub.SetInParent()
                dao_class(col.fk)(self.conn)._read_into(cur, value, sub)
        if self.CHILDREN:
            owner = self._pk_value(msg)
            for child in self.CHILDREN:
                self._read_child(cur, child, owner, msg)

    # -- child tables (map / repeated), keyed by the parent's primary key ----
    def _container(self, msg: Message, child: ChildTable, mutable: bool) -> Any:
        return getattr(_owner(msg, child.path, mutable), child.path[-1])

    def _field(self, msg: Message, child: ChildTable) -> Any:
        return _owner(msg, child.path, False).DESCRIPTOR.fields_by_name[child.path[-1]]

    def _write_child(self, cur: Any, child: ChildTable, owner: Any, msg: Message,
                     update: bool) -> None:
        if update:
            cur.execute(child.delete_sql, [owner])
        f = self._field(msg, child)
        items = self._container(msg, child, False)
        if child.kind == "map":
            kf = f.message_type.fields_by_name["key"]
            vf = f.message_type.fields_by_name["value"]
            for key in items:
                cur.execute(child.insert_sql,
                            [owner, to_db(kf, key), to_db(vf, items[key])])
            return
        for ordinal, item in enumerate(items):
            if child.kind == "composed":
                values = [column_value(item, c) for c in child.columns]
            elif child.fk is not None:
                child_dao = dao_class(child.fk)(self.conn)
                if update:
                    child_dao._update(cur, item)
                else:
                    child_dao._create(cur, item)
                values = [child_dao._pk_value(item)]
            else:
                values = [to_db(f, item)]
            cur.execute(child.insert_sql, [owner, ordinal, *values])

    def _read_child(self, cur: Any, child: ChildTable, owner: Any,
                    msg: Message) -> None:
        f = self._field(msg, child)
        cur.execute(child.select_sql, [owner])
        rows = cur.fetchall()
        items = self._container(msg, child, True)
        if child.kind == "map":
            kf = f.message_type.fields_by_name["key"]
            vf = f.message_type.fields_by_name["value"]
            for key, value in rows:
                items[from_db(kf, key)] = from_db(vf, value)
            return
        for row in rows:
            if child.kind == "composed":
                element = items.add()
                for col, value in zip(child.columns, row, strict=False):
                    set_column(element, col, value)
            elif child.fk is not None:
                dao_class(child.fk)(self.conn)._read_into(cur, row[0], items.add())
            else:
                items.append(from_db(f, row[0]))

    # -- cursor-level operations (no transaction handling; a parent DAO runs
    # -- its children's on its own cursor so one call is one transaction) ----
    def _create(self, cur: Any, msg: M) -> None:
        for col in self.COLUMNS:
            if col.fk is not None and _has_child(msg, col):
                dao_class(col.fk)(self.conn)._create(cur, _child(msg, col))
        cur.execute(self.INSERT_SQL, [self._bind(msg, c) for c in self.COLUMNS])
        if self.CHILDREN:
            owner = self._pk_value(msg)
            for child in self.CHILDREN:
                self._write_child(cur, child, owner, msg, update=False)
        self._audit("create")

    def _read_into(self, cur: Any, pk: Any, out: M) -> bool:
        cur.execute(self.SELECT_SQL, [pk])
        row = cur.fetchone()
        if row is None:
            return False
        self._load_row(cur, row, out)
        self._audit("read")
        return True

    def _update(self, cur: Any, msg: M) -> bool:
        for col in self.COLUMNS:
            if col.fk is not None and _has_child(msg, col):
                dao_class(col.fk)(self.conn)._update(cur, _child(msg, col))
        params = [self._bind(msg, c) for c in self.COLUMNS if c.name != self.PK]
        params.append(self._pk_value(msg))
        cur.execute(self.UPDATE_SQL, params)
        found = bool(cur.rowcount > 0)
        if self.CHILDREN:
            owner = self._pk_value(msg)
            for child in self.CHILDREN:
                self._write_child(cur, child, owner, msg, update=True)
        self._audit("update")  # whether or not a row matched, as C++
        return found

    # -- DDL ------------------------------------------------------------------
    def create_table(self) -> None:
        """Create the table (and any child tables) if missing."""
        with self._tx() as cur:
            for sql in self.CREATE_TABLE_SQL:
                cur.execute(sql)

    def drop_table(self) -> None:
        """Drop the table (and any child tables) if present."""
        with self._tx() as cur:
            for sql in self.DROP_TABLE_SQL:
                cur.execute(sql)

    # -- CRUDL ----------------------------------------------------------------
    def create(self, msg: M) -> bool:
        """Insert ``msg`` as a new row (its ``ID_<hash>`` is the key).

        Returns:
            ``True``. A database error (for example a duplicate key) raises.
        """
        with self._tx() as cur:
            self._create(cur, msg)
        return True

    def read(self, pk: int, out: M) -> bool:
        """Load the row with primary key ``pk`` into ``out``.

        Returns:
            ``False`` when no such row exists (``out`` is untouched).
        """
        with self._tx() as cur:
            return self._read_into(cur, pk, out)

    def update(self, msg: M) -> bool:
        """Overwrite the row whose key is ``msg``'s ``ID_<hash>``.

        Returns:
            ``False`` when no row has that key.
        """
        with self._tx() as cur:
            return self._update(cur, msg)

    def remove(self, pk: int) -> bool:
        """Delete the row with primary key ``pk``.

        Returns:
            ``False`` when no such row existed.
        """
        with self._tx() as cur:
            cur.execute(self.DELETE_SQL, [pk])
            found = bool(cur.rowcount > 0)
            for child in self.CHILDREN:
                cur.execute(child.delete_sql, [pk])
            self._audit("remove")  # whether or not a row matched, as C++
            return found

    def list(self, offset: int | None = None,
             limit: int | None = None) -> builtins.list[M]:
        """Every row, or one page of rows when ``offset``/``limit`` are given.

        Pagination passes ``LIMIT``/``OFFSET`` straight to the database, like
        the C++ DAO; ``limit=None`` means "no limit" on every dialect
        (PostgreSQL rejects the negative limit SQLite would accept).
        """
        out: builtins.list[M] = []
        with self._tx() as cur:
            if offset is None and limit is None:
                cur.execute(self.LIST_SQL)
            else:
                cur.execute(self.LIST_PAGE_SQL,
                            [_NO_LIMIT if limit is None else limit, offset or 0])
            for row in cur.fetchall():
                msg = self._new()
                self._load_row(cur, row, msg)
                out.append(msg)
            self._audit("list")
        return out
