"""``phi`` column encryption + per-operation audit for generated DAOs (the
Python side of the C++ DAO's db-encryption wiring in
``Database/CrudlAdapter.py``).

A generated DAO whose message has a ``phi`` column subclasses
:class:`PhiDao` instead of :class:`~harpia_runtime.db.dao.Dao`. Copied into
a generated project only when such a column exists, together with the
``harpia_runtime.crypto`` runtimes.

As in C++:

- every ``phi`` column is stored as :func:`encrypt_field` text
  (``enc:v1:...``) in its column's existing type; numeric/enum/bool values
  are stringified first (``std::to_string`` style: ``%f`` for floats);
- it is read back with ``decrypt_field`` / ``_ll`` / ``_int`` / ``_float``
  by field type; an unrecoverable value reads as the field's zero;
- every CRUDL call records exactly one
  ``record("phi_<op>", "<table>", "<phi column names>")`` --
  ``phi_create`` / ``phi_read`` / ``phi_update`` / ``phi_delete`` /
  ``phi_list``. Names only, never a value. A ``read`` that finds no row
  records nothing; ``update`` / ``remove`` record whether or not a row
  matched; a child DAO reached through an FK audits its own operations
  and uses its own (default) key provider and sink.

Only top-level and flattened-embed scalar/enum columns can be ``phi`` (the
C++ scope): child-table values are not encrypted.
"""
from typing import Any, ClassVar, TypeVar

from google.protobuf.descriptor import FieldDescriptor as FD
from google.protobuf.message import Message

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink
from harpia_runtime.crypto.encrypted_column import (
    decrypt_field,
    decrypt_field_float,
    decrypt_field_int,
    decrypt_field_ll,
    default_key_provider,
    encrypt_field,
)
from harpia_runtime.crypto.key_provider import KeyProvider
from harpia_runtime.db.dao import (
    Column,
    Connection,
    Dao,
    _owner,
    column_value,
    set_column,
)

M = TypeVar("M", bound=Message)

#: audit operation per CRUDL call (``remove`` audits as ``phi_delete``, as C++)
AUDIT_OPS = {"create": "phi_create", "read": "phi_read", "update": "phi_update",
             "remove": "phi_delete", "list": "phi_list"}

_FLOATS = (FD.CPPTYPE_FLOAT, FD.CPPTYPE_DOUBLE)
_WIDE = (FD.CPPTYPE_INT64, FD.CPPTYPE_UINT64)


def _descriptor(msg: Message, col: Column, mutable: bool) -> tuple[Message, FD]:
    owner = _owner(msg, col.path, mutable)
    return owner, owner.DESCRIPTOR.fields_by_name[col.path[-1]]


def plaintext(value: Any, field: FD) -> str:
    """The text a ``phi`` value is sealed as (C++ ``std::to_string``)."""
    if field.cpp_type == FD.CPPTYPE_STRING:
        return str(value)
    if field.cpp_type in _FLOATS:
        return f"{value:f}"
    return str(int(value))


class PhiDao(Dao[M]):
    """A :class:`~harpia_runtime.db.dao.Dao` that encrypts its ``phi``
    columns and audits every operation."""

    #: the ``phi`` column names, the audit record's detail
    PHI_FIELDS: ClassVar[tuple[str, ...]]

    def __init__(self, conn: Connection, key_provider: KeyProvider | None = None,
                 audit_sink: AuditSink | None = None) -> None:
        """Args:
            conn: A DB-API connection.
            key_provider: Wraps the per-value DEKs; defaults to the
                process-wide in-memory provider (not for production).
            audit_sink: Receives one record per operation; defaults to
                the no-op sink.
        """
        super().__init__(conn)
        self.key_provider = key_provider or default_key_provider()
        self.audit_sink = audit_sink or default_audit_sink()

    def _bind(self, msg: M, col: Column) -> Any:
        if not col.phi:
            return column_value(msg, col)
        owner, field = _descriptor(msg, col, False)
        return encrypt_field(self.key_provider,
                             plaintext(getattr(owner, field.name), field))

    def _load(self, msg: M, col: Column, value: Any) -> None:
        if not col.phi:
            set_column(msg, col, value)
            return
        owner, field = _descriptor(msg, col, True)
        stored = "" if value is None else str(value)
        kp = self.key_provider
        decoded: Any
        if field.cpp_type == FD.CPPTYPE_STRING:
            decoded = decrypt_field(kp, stored)
        elif field.cpp_type in _FLOATS:
            decoded = decrypt_field_float(kp, stored)
        elif field.cpp_type in _WIDE:
            decoded = decrypt_field_ll(kp, stored)
            if field.cpp_type == FD.CPPTYPE_UINT64:
                decoded &= (1 << 64) - 1
        else:
            decoded = decrypt_field_int(kp, stored)
            if field.cpp_type == FD.CPPTYPE_UINT32:
                decoded &= 0xFFFFFFFF
            elif field.cpp_type == FD.CPPTYPE_BOOL:
                decoded = bool(decoded)
        setattr(owner, field.name, decoded)

    def _audit(self, op: str) -> None:
        self.audit_sink.record(AUDIT_OPS[op], self.TABLE, ",".join(self.PHI_FIELDS))
