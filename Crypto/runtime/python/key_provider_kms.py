"""The KMS/HSM extension point (Python port of
``Crypto/runtime/harpia_key_provider_kms.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.crypto.key_provider_kms``.

* :class:`KmsClient` is the small seam an integrator implements for AWS
  KMS, Vault, a PKCS#11 HSM, ...: four operations over opaque bytes and an
  integer key version. Implementations must be thread-safe.
* :class:`KmsKeyProvider` routes every :class:`KeyProvider` operation to
  that seam and adds nothing, so swapping backends needs no interface
  change. Per-DEK crypto-shred is a local set (most KMS can only delete a
  whole key version).
* :class:`MockKms` is the in-memory reference client (placeholder XOR).
"""
import builtins
import threading
from abc import ABC, abstractmethod

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink
from harpia_runtime.crypto.key_provider import (
    KEY_LEN,
    OP_GENERATE,
    OP_ROTATE,
    OP_SHRED,
    OP_UNWRAP,
    OP_WRAP,
    Dek,
    KeyProvider,
    WrappedDek,
    random_bytes,
    secure_zero,
    shred_key,
    xor_with,
)


class KmsClient(ABC):
    """What a KMS/HSM integration implements."""

    @abstractmethod
    def active_version(self) -> int:
        """The KMS's current key version; :meth:`rotate` advances it."""

    @abstractmethod
    def wrap(self, version: int, dek_material: builtins.bytes) -> builtins.bytes:
        """Wrap DEK material under key ``version``; returns an opaque blob."""

    @abstractmethod
    def unwrap(self, version: int, wrapped: builtins.bytes) -> builtins.bytes | None:
        """Unwrap a blob made by :meth:`wrap`; ``None`` when ``version`` is
        gone at the KMS."""

    @abstractmethod
    def rotate(self) -> int:
        """Create a new key version and return it; older ones still unwrap."""


class KmsKeyProvider(KeyProvider):
    """A :class:`KeyProvider` whose KEKs live in a :class:`KmsClient`."""

    def __init__(self, kms: KmsClient, audit_sink: AuditSink | None = None) -> None:
        self._kms = kms
        self._audit = audit_sink or default_audit_sink()
        self._lock = threading.Lock()
        self._shredded: set[builtins.bytes] = set()

    def active_kek_version(self) -> int:
        return self._kms.active_version()

    def generate_dek(self) -> Dek:
        self._audit.record(OP_GENERATE, "dek")
        return Dek(random_bytes(KEY_LEN))  # minted locally, the KMS wraps it

    def wrap_dek(self, dek: Dek) -> WrappedDek:
        version = self._kms.active_version()
        self._audit.record(OP_WRAP, f"kek:{version}")
        wrapped = self._kms.wrap(version, builtins.bytes(dek.material))
        return WrappedDek(version, wrapped)

    def unwrap_dek(self, w: WrappedDek) -> Dek | None:
        subject = f"kek:{w.kek_version}"
        with self._lock:
            shredded = shred_key(w) in self._shredded
        if shredded:
            self._audit.record(OP_UNWRAP, subject, "shredded")
            return None
        raw = self._kms.unwrap(w.kek_version, w.bytes)
        if raw is None:
            self._audit.record(OP_UNWRAP, subject, "unknown_version")
            return None
        self._audit.record(OP_UNWRAP, subject, "ok")
        return Dek(raw)

    def rotate(self) -> int:
        version = self._kms.rotate()
        self._audit.record(OP_ROTATE, f"kek:{version}")
        return version

    def shred_dek(self, w: WrappedDek) -> None:
        with self._lock:
            self._shredded.add(shred_key(w))
        self._audit.record(OP_SHRED, f"kek:{w.kek_version}")


class MockKms(KmsClient):
    """In-memory reference :class:`KmsClient` (placeholder XOR). Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 1
        self._keys: dict[int, bytearray] = {1: random_bytes(KEY_LEN)}

    def active_version(self) -> int:
        with self._lock:
            return self._active

    def wrap(self, version: int, dek_material: builtins.bytes) -> builtins.bytes:
        with self._lock:
            return xor_with(dek_material, self._keys[version])

    def unwrap(self, version: int, wrapped: builtins.bytes) -> builtins.bytes | None:
        with self._lock:
            key = self._keys.get(version)
            return None if key is None else xor_with(wrapped, key)

    def rotate(self) -> int:
        with self._lock:
            self._active += 1
            self._keys[self._active] = random_bytes(KEY_LEN)
            return self._active

    def forget_version(self, version: int) -> None:
        """Stand-in for "the KMS deleted this key version" (zeroed first)."""
        with self._lock:
            key = self._keys.pop(version, None)
            if key is not None:
                secure_zero(key)

    def __del__(self) -> None:
        for key in getattr(self, "_keys", {}).values():
            secure_zero(key)
