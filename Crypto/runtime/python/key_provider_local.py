"""The default key provider for integrators with no KMS/HSM (Python port of
``Crypto/runtime/harpia_key_provider_local.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.crypto.key_provider_local``.

KEK material persists to ``storage_path`` in the **same file format C++
writes**, so one store serves both languages: one ``<version> <hex>`` line
per KEK, lowercase hex, ascending version, rewritten (truncated) on every
change. A missing or empty store is created with KEK version 1.

Crypto-shred appends ``<kek_version> <hex of the wrapped DEK>`` to
``<storage_path>.shred`` (append-only; the KEK store is never touched), so
a shred survives a restart and is honored by the C++ provider too.

**Fail-safe gate:** when the compliance profile puts PHI at scale, the
constructor raises :class:`LocalKeyProviderRefused` unless the integrator
explicitly acknowledged the local fallback
(:attr:`LocalKeyProviderConfig.acknowledged`, for example from
:func:`local_key_provider_acknowledged`).

Still the placeholder XOR cipher of
:mod:`harpia_runtime.crypto.key_provider`; this module adds persistence and
the gate, not a crypto primitive.
"""
import builtins
import os
import threading
from dataclasses import dataclass

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

#: environment variable read by :func:`local_key_provider_acknowledged`
ACK_ENV = "HARPIA_ACK_LOCAL_KEY_PROVIDER"


class LocalKeyProviderRefused(RuntimeError):
    """PHI at scale and the local key backend was not acknowledged."""

    def __init__(self) -> None:
        super().__init__(
            "LocalKeyProvider refused: the compliance profile implies PHI at "
            "scale and the local key backend was not explicitly acknowledged "
            "(set LocalKeyProviderConfig.acknowledged / "
            "HARPIA_ACK_LOCAL_KEY_PROVIDER after making a KMS-vs-local decision)")


@dataclass(frozen=True)
class LocalKeyProviderConfig:
    """How to construct a :class:`LocalKeyProvider`."""

    #: file the KEKs are read from / written to (created if missing)
    storage_path: str
    #: does the active compliance profile put PHI at scale?
    phi_at_scale: bool = False
    #: explicit opt-in to the local fallback (only consulted at scale)
    acknowledged: bool = False


def local_key_provider_acknowledged() -> bool:
    """``True`` when ``HARPIA_ACK_LOCAL_KEY_PROVIDER`` is ``1``/``true``/
    ``yes`` (any case), as in C++."""
    return os.environ.get(ACK_ENV, "").lower() in ("1", "true", "yes")


def _parse_line(line: str) -> tuple[int, builtins.bytes] | None:
    parts = line.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    return int(parts[0]), builtins.bytes.fromhex(parts[1])


class LocalKeyProvider(KeyProvider):
    """File-persisted KEKs plus the acknowledgment gate. Thread-safe."""

    def __init__(self, cfg: LocalKeyProviderConfig,
                 audit_sink: AuditSink | None = None) -> None:
        if cfg.phi_at_scale and not cfg.acknowledged:
            raise LocalKeyProviderRefused()
        self._audit = audit_sink or default_audit_sink()
        self._lock = threading.Lock()
        self._path = cfg.storage_path
        self._active = 1
        self._keks: dict[int, bytearray] = {}
        self._shredded: set[builtins.bytes] = set()
        if not self._load():
            self._keks = {1: random_bytes(KEY_LEN)}
            self._persist()
            self._audit.record(OP_GENERATE, f"kek:{self._active}")
        self._load_shreds()

    @property
    def shred_path(self) -> str:
        """The append-only shred sidecar, ``<storage_path>.shred``."""
        return self._path + ".shred"

    def _load(self) -> bool:
        try:
            with open(self._path, encoding="ascii") as f:
                lines = f.read().split("\n")
        except FileNotFoundError:
            return False
        loaded: dict[int, bytearray] = {}
        for line in lines:
            parsed = _parse_line(line)
            if parsed is not None:
                loaded[parsed[0]] = bytearray(parsed[1])
        if not loaded:
            return False
        self._keks = loaded
        self._active = max(loaded)
        return True

    def _persist(self) -> None:
        with open(self._path, "w", encoding="ascii") as f:
            for version in sorted(self._keks):
                f.write(f"{version} {self._keks[version].hex()}\n")

    def _load_shreds(self) -> None:
        try:
            with open(self.shred_path, encoding="ascii") as f:
                lines = f.read().split("\n")
        except FileNotFoundError:
            return
        for line in lines:
            parsed = _parse_line(line)
            if parsed is not None:
                self._shredded.add(shred_key(WrappedDek(*parsed)))

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
            self._persist()
            self._audit.record(OP_ROTATE, f"kek:{self._active}")
            return self._active

    def shred_dek(self, w: WrappedDek) -> None:
        with self._lock:
            key = shred_key(w)
            if key not in self._shredded:
                self._shredded.add(key)
                with open(self.shred_path, "a", encoding="ascii") as f:
                    f.write(f"{w.kek_version} {w.bytes.hex()}\n")
            self._audit.record(OP_SHRED, f"kek:{w.kek_version}")

    def close(self) -> None:
        """Zero the in-memory KEKs (best-effort); the store file is kept."""
        with self._lock:
            for kek in self._keks.values():
                secure_zero(kek)
            self._keks.clear()

    def __del__(self) -> None:
        if hasattr(self, "_keks"):
            self.close()
