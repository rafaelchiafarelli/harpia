"""Envelope-encryption key management for ``phi`` data (Python port of
``Crypto/runtime/harpia_key_provider.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.crypto.key_provider`` when a runtime needs it.

Envelope encryption, as in C++:

* every ``phi`` value/record gets its own data-encryption key (:class:`Dek`);
* only the DEK ever touches the value (:meth:`Dek.seal` / :meth:`Dek.open`);
* the key-encryption key (KEK) only ever wraps DEKs;
* a :class:`WrappedDek` carries the KEK version that wrapped it, so
  :meth:`KeyProvider.rotate` is O(number of keys): it mints a new KEK
  version and leaves every existing ``WrappedDek`` and ciphertext alone.

**The cipher is a placeholder XOR, not encryption** -- the same transform
as C++, byte for byte, so material sealed or wrapped by one language opens
in the other. The real AEAD is the F5 ``CryptoBackend`` seam binding,
which neither target has yet.

Rule 5: a fallible operation has a distinct, observable outcome.
:meth:`KeyProvider.unwrap_dek` returns ``None`` for an unknown (forgotten)
or crypto-shredded key; it never raises and never returns a zeroed key.

Every key operation is recorded through an
:class:`~harpia_runtime.compliance.audit_sink.AuditSink` as ``key_<op>``
with subject ``kek:<version>`` or ``dek`` -- never key bytes.

**Zeroization is best-effort, not a guarantee.** Key bytes live in
``bytearray`` objects that :func:`secure_zero` overwrites in place when a
:class:`Dek` is closed or collected and when a KEK is evicted. CPython can
still leave copies behind (immutable ``bytes`` temporaries made while
sealing or wrapping, allocator reuse), so this does not match C++'s
``secure_zero`` guarantee.
"""
import builtins
import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink

#: audit operation names (the C++ ``kOp*`` values)
OP_GENERATE = "key_generate"
OP_WRAP = "key_wrap"
OP_UNWRAP = "key_unwrap"
OP_ROTATE = "key_rotate"
OP_SHRED = "key_shred"

#: key length in bytes, for KEKs and DEKs alike (as C++)
KEY_LEN = 32


def secure_zero(buf: bytearray) -> None:
    """Overwrite ``buf`` with zeros in place, then empty it (best-effort)."""
    for i in range(len(buf)):
        buf[i] = 0
    buf.clear()


def random_bytes(n: int) -> bytearray:
    """``n`` random bytes of key material for the placeholder providers."""
    return bytearray(secrets.token_bytes(n))


def xor_with(data: builtins.bytes, key: builtins.bytes | bytearray) -> builtins.bytes:
    """The placeholder transform: ``data`` XOR the repeated ``key``.

    An empty key leaves ``data`` unchanged, as in C++.
    """
    if not key:
        return builtins.bytes(data)
    n = len(key)
    return builtins.bytes(b ^ key[i % n] for i, b in enumerate(data))


class Dek:
    """A data-encryption key: one per ``phi`` value/record.

    Usable as a context manager; leaving the block (or :meth:`close`, or
    garbage collection) zeroes the key bytes.

    :attr:`material` is owned by the ``Dek`` and wiped in place when the
    ``Dek`` goes away, so hold the ``Dek`` itself while you use its key.
    ``p.unwrap_dek(w).material`` is already zeroed once the temporary
    ``Dek`` is collected; copy with ``bytes(dek.material)`` if the bytes
    must outlive it.
    """

    def __init__(self, material: builtins.bytes | bytearray = b"") -> None:
        #: the raw key bytes
        self.material = bytearray(material)

    def seal(self, plaintext: builtins.bytes) -> builtins.bytes:
        """Seal ``plaintext`` with this key (placeholder XOR)."""
        return xor_with(plaintext, self.material)

    def open(self, ciphertext: builtins.bytes) -> builtins.bytes:
        """Open ``ciphertext`` sealed with this key (XOR is its own inverse)."""
        return xor_with(ciphertext, self.material)

    def close(self) -> None:
        """Zero the key bytes (best-effort; see the module docstring)."""
        secure_zero(self.material)

    def __enter__(self) -> "Dek":
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


@dataclass(frozen=True)
class WrappedDek:
    """A DEK wrapped by a KEK, plus the KEK version needed to unwrap it.

    Stored next to the ciphertext; rotation only ever rewrites these.
    """

    kek_version: int
    bytes: builtins.bytes


def shred_key(w: WrappedDek) -> builtins.bytes:
    """Stable identity of one wrapped DEK for the crypto-shred registry:
    ``b"<kek_version>:" + w.bytes``, exact, as C++ ``shred_key``."""
    return str(w.kek_version).encode() + b":" + w.bytes


class KeyProvider(ABC):
    """Where KEKs live and how DEKs are minted, wrapped and shredded."""

    @abstractmethod
    def active_kek_version(self) -> int:
        """The active KEK version; :meth:`rotate` bumps it."""

    @abstractmethod
    def generate_dek(self) -> Dek:
        """Mint a fresh DEK for a new ``phi`` value."""

    @abstractmethod
    def wrap_dek(self, dek: Dek) -> WrappedDek:
        """Wrap ``dek`` with the active KEK, recording that KEK's version."""

    @abstractmethod
    def unwrap_dek(self, w: WrappedDek) -> Dek | None:
        """Unwrap with the KEK version recorded in ``w``.

        Returns:
            ``None`` when that version is unknown or the DEK was shredded.
            Never raises (Rule 5).
        """

    @abstractmethod
    def rotate(self) -> int:
        """Mint a new active KEK version and return it.

        Older KEKs are kept, so every existing :class:`WrappedDek` still
        unwraps; no ciphertext or ``WrappedDek`` is touched.
        """

    @abstractmethod
    def shred_dek(self, w: WrappedDek) -> None:
        """Crypto-shred: permanently discard the DEK ``w`` refers to.

        Afterwards :meth:`unwrap_dek` returns ``None`` for ``w`` although
        the KEK is intact, so exactly that record becomes unrecoverable.
        Per-DEK, idempotent, irreversible.
        """


class InMemoryKeyProvider(KeyProvider):
    """In-memory, non-persistent provider for tests and the default column
    helper. Not for production: keys live only in process memory and the
    transforms are the placeholder XOR. Thread-safe.
    """

    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._audit = audit_sink or default_audit_sink()
        self._lock = threading.Lock()
        self._active = 1
        self._keks: dict[int, bytearray] = {self._active: random_bytes(KEY_LEN)}
        self._shredded: set[builtins.bytes] = set()
        self._audit.record(OP_GENERATE, f"kek:{self._active}")

    def active_kek_version(self) -> int:
        with self._lock:
            return self._active

    def generate_dek(self) -> Dek:
        self._audit.record(OP_GENERATE, "dek")
        return Dek(random_bytes(KEY_LEN))

    def wrap_dek(self, dek: Dek) -> WrappedDek:
        with self._lock:
            self._audit.record(OP_WRAP, f"kek:{self._active}")
            return WrappedDek(self._active,
                              xor_with(builtins.bytes(dek.material),
                                       self._keks[self._active]))

    def unwrap_dek(self, w: WrappedDek) -> Dek | None:
        with self._lock:
            subject = f"kek:{w.kek_version}"
            if shred_key(w) in self._shredded:
                self._audit.record(OP_UNWRAP, subject, "shredded")
                return None
            kek = self._keks.get(w.kek_version)
            if kek is None:
                self._audit.record(OP_UNWRAP, subject, "unknown_version")
                return None
            self._audit.record(OP_UNWRAP, subject, "ok")
            return Dek(xor_with(w.bytes, kek))

    def rotate(self) -> int:
        with self._lock:
            self._active += 1
            self._keks[self._active] = random_bytes(KEY_LEN)
            self._audit.record(OP_ROTATE, f"kek:{self._active}")
            return self._active

    def shred_dek(self, w: WrappedDek) -> None:
        with self._lock:
            self._shredded.add(shred_key(w))
            self._audit.record(OP_SHRED, f"kek:{w.kek_version}")

    def forget_kek_version(self, version: int) -> None:
        """Drop a whole KEK version (zeroed first). Distinct from
        :meth:`shred_dek`: this retires every DEK that KEK wrapped."""
        with self._lock:
            kek = self._keks.pop(version, None)
            if kek is not None:
                secure_zero(kek)

    def close(self) -> None:
        """Zero every KEK (best-effort); the provider is unusable afterwards."""
        with self._lock:
            for kek in self._keks.values():
                secure_zero(kek)
            self._keks.clear()

    def __del__(self) -> None:
        self.close()
