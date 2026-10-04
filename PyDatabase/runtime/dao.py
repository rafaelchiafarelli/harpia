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

from harpia_runtime.db.bind import bind_value, extract_value


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
    """

    name: str
    path: tuple[str, ...]
    fk: str | None = None


M = TypeVar("M", bound=Message)


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
                set_column(msg, col, value)
            elif value:
                # a non-zero key: load the child through its own DAO; a zero
                # key means the child was absent (no phantom child)
                sub: Message = getattr(_owner(msg, col.path, True), col.path[-1])
                sub.SetInParent()
                dao_class(col.fk)(self.conn)._read_into(cur, value, sub)

    # -- cursor-level operations (no transaction handling; a parent DAO runs
    # -- its children's on its own cursor so one call is one transaction) ----
    def _create(self, cur: Any, msg: M) -> None:
        for col in self.COLUMNS:
            if col.fk is not None and _has_child(msg, col):
                dao_class(col.fk)(self.conn)._create(cur, _child(msg, col))
        cur.execute(self.INSERT_SQL, [column_value(msg, c) for c in self.COLUMNS])

    def _read_into(self, cur: Any, pk: Any, out: M) -> bool:
        cur.execute(self.SELECT_SQL, [pk])
        row = cur.fetchone()
        if row is None:
            return False
        self._load_row(cur, row, out)
        return True

    def _update(self, cur: Any, msg: M) -> bool:
        for col in self.COLUMNS:
            if col.fk is not None and _has_child(msg, col):
                dao_class(col.fk)(self.conn)._update(cur, _child(msg, col))
        params = [column_value(msg, c) for c in self.COLUMNS if c.name != self.PK]
        params.append(self._pk_value(msg))
        cur.execute(self.UPDATE_SQL, params)
        return bool(cur.rowcount > 0)

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
            return bool(cur.rowcount > 0)

    def list(self, offset: int | None = None,
             limit: int | None = None) -> builtins.list[M]:
        """Every row, or one page of rows when ``offset``/``limit`` are given.

        Pagination passes ``LIMIT``/``OFFSET`` straight to the database, like
        the C++ DAO (on SQLite a negative limit means "no limit").
        """
        out: builtins.list[M] = []
        with self._tx() as cur:
            if offset is None and limit is None:
                cur.execute(self.LIST_SQL)
            else:
                cur.execute(self.LIST_PAGE_SQL,
                            [-1 if limit is None else limit, offset or 0])
            for row in cur.fetchall():
                msg = self._new()
                self._load_row(cur, row, msg)
                out.append(msg)
        return out
