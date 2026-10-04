"""Field-level encryption of ``phi`` column values (Python port of
``Crypto/runtime/harpia_encrypted_column.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.crypto.encrypted_column``.

:func:`encrypt_field` runs ``generate_dek`` → ``seal`` → ``wrap_dek`` and
stores ``"enc:v1:"`` + lowercase hex of the frame::

    u64 kek_version (big-endian) | u32 len(wrapped DEK) (big-endian)
    | wrapped DEK | ciphertext

-- byte-identical to C++, so a value encrypted by one language decrypts in
the other given a shared key store (for example one ``LocalKeyProvider``
file). The value keeps its column's existing TEXT type. Text is UTF-8.

Rule 5: :func:`decrypt_field` never raises. A value without the marker is
returned as-is (a legacy plaintext row); a malformed frame, an unknown or
shredded key, or bytes that are not valid UTF-8 give ``""`` -- and ``0``
from the numeric variants, which parse like C ``strtoll``/``strtod``
(leading whitespace, longest numeric prefix, no hexadecimal floats).

This module adds no crypto: it frames and routes. The cipher is whatever
the :class:`~harpia_runtime.crypto.key_provider.KeyProvider` does (today
the placeholder XOR).
"""
import re
import struct
import threading

from harpia_runtime.crypto.key_provider import (
    InMemoryKeyProvider,
    KeyProvider,
    WrappedDek,
)

#: prefix of every encrypted column value
ENC_MARKER = "enc:v1:"

_HEADER = struct.Struct(">QI")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2})*")
_INT = re.compile(r"\s*([+-]?\d+)")
_FLOAT = re.compile(r"\s*([+-]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
                    r"|inf(?:inity)?|nan))", re.IGNORECASE)
_LLONG_MIN, _LLONG_MAX = -(1 << 63), (1 << 63) - 1

_default: KeyProvider | None = None
_default_lock = threading.Lock()


def default_key_provider() -> KeyProvider:
    """The process-wide :class:`InMemoryKeyProvider` (the same object on
    every call) that generated DAOs default to."""
    global _default
    with _default_lock:
        if _default is None:
            _default = InMemoryKeyProvider()
        return _default


def encrypt_field(kp: KeyProvider, plaintext: str) -> str:
    """Encrypt ``plaintext`` under a fresh DEK wrapped by ``kp``'s active KEK."""
    with kp.generate_dek() as dek:
        ciphertext = dek.seal(plaintext.encode("utf-8"))
        w = kp.wrap_dek(dek)
    frame = _HEADER.pack(w.kek_version, len(w.bytes)) + w.bytes + ciphertext
    return ENC_MARKER + frame.hex()


def decrypt_field(kp: KeyProvider, stored: str) -> str:
    """Decrypt a value written by :func:`encrypt_field` (either language).

    Returns:
        ``stored`` unchanged when it lacks the marker; ``""`` when it can't
        be recovered. Never raises.
    """
    if not stored.startswith(ENC_MARKER):
        return stored
    body = stored[len(ENC_MARKER):]
    if not _HEX.fullmatch(body):
        return ""
    frame = bytes.fromhex(body)
    if len(frame) < _HEADER.size:
        return ""
    kek_version, wrapped_len = _HEADER.unpack_from(frame)
    end = _HEADER.size + wrapped_len
    if len(frame) < end:
        return ""
    dek = kp.unwrap_dek(WrappedDek(kek_version, frame[_HEADER.size:end]))
    if dek is None:
        return ""
    with dek:
        raw = dek.open(frame[end:])
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def decrypt_field_ll(kp: KeyProvider, stored: str) -> int:
    """A numeric ``phi`` value as a 64-bit integer (``strtoll``: saturates)."""
    m = _INT.match(decrypt_field(kp, stored))
    if m is None:
        return 0
    digits = m.group(1)
    if len(digits.lstrip("+-").lstrip("0")) > 19:  # beyond int64 (and int()'s limit)
        return _LLONG_MIN if digits.startswith("-") else _LLONG_MAX
    return max(_LLONG_MIN, min(_LLONG_MAX, int(digits)))


def decrypt_field_int(kp: KeyProvider, stored: str) -> int:
    """A numeric ``phi`` value as a 32-bit integer (wraps like C++'s cast)."""
    v = decrypt_field_ll(kp, stored) & 0xFFFFFFFF
    return v - (1 << 32) if v >= 1 << 31 else v


def decrypt_field_float(kp: KeyProvider, stored: str) -> float:
    """A numeric ``phi`` value as a float (``strtod`` prefix parse)."""
    m = _FLOAT.match(decrypt_field(kp, stored))
    return 0.0 if m is None else float(m.group(1))
