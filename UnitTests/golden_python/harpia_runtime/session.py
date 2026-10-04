"""Bearer session tokens (Python port of
``Compliance/runtime/harpia_session.h``, transport-authn task 5).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.session`` next to :mod:`harpia_runtime.rbac` (only when some
message is RBAC-gated). Layered **on top of** the RBAC gate:

1. A caller that authenticated the mTLS transport (client certificate → CN →
   role via ``HARPIA_RBAC_MAP``) asks for a token: ``POST <rest_base>/session``
   (JSON ``{"token": ..., "token_type": "Bearer"}``), ``POST
   <soap_base>/session`` (``<sessionToken>``), or gRPC ``heartBeat`` with
   ``harpia-issue-session`` metadata (``harpia-session-token`` trailing
   metadata).
2. It presents ``Authorization: Bearer <token>`` (gRPC: ``authorization``
   metadata). The gate verifies signature, expiry and revocation and gates on
   the CN inside. A presented token that does not verify is refused (401 /
   ``UNAUTHENTICATED``) -- never a fall-through to the certificate.
3. ``HARPIA_SESSION_REVOCATIONS`` names a file of revoked ``jti`` values (one
   per line, ``#`` comments), re-read whenever its **content** changes.

The token format is the C++ one, byte for byte, so either language verifies
the other's tokens under the same key::

    v1.<base64url(payload), no padding>.<hex HMAC-SHA256(key,
        "harpiasess.v1." + base64url(payload))>
    payload = cn \\n role \\n issued_at \\n expires_at \\n jti   (jti: 128-bit hex)

Configuration (read once, from the environment, like C++):
``HARPIA_SESSION_KEY`` (raw bytes, or ``@<path>`` to read them from a file,
trailing newlines stripped; unset/empty disables sessions -- :func:`issue`
returns ``""`` and :func:`verify` :attr:`Verdict.no_key`),
``HARPIA_SESSION_TTL`` (seconds, default 900), ``HARPIA_SESSION_REVOCATIONS``.

Every non-ok :func:`verify` records exactly one ``session_denied`` audit event
(subject ``"session"``, detail ``verdict=<v> cn=<cn> jti=<jti>``) -- never
token bytes. Thread-safe: key and TTL are resolved once under a lock, the
revocation list is lock-guarded.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from enum import Enum

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink

#: domain-separation prefix mixed into every MAC
TOKEN_CONTEXT = b"harpiasess.v1."
DEFAULT_TTL_SECONDS = 900

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_B64_VALUE = {c: i for i, c in enumerate(_B64)}
_ATOLL = re.compile(rb"[ \t\n\v\f\r]*([+-]?[0-9]+)")


class Verdict(Enum):
    """Outcome of :func:`verify` (values = the C++ ``verdict_name``)."""

    ok = "ok"
    no_key = "no_key"
    malformed = "malformed"
    bad_signature = "bad_signature"
    expired = "expired"
    revoked = "revoked"


@dataclass(frozen=True)
class Claims:
    """What a token carries."""

    cn: str = ""
    role: str = ""
    jti: str = ""
    issued_at: int = 0
    expires_at: int = 0


@dataclass(frozen=True)
class Bearer:
    """An ``Authorization`` header as a gate sees it. Use :attr:`cn` only when
    :attr:`present` and :attr:`verdict` is ok; present-but-not-ok must be
    refused."""

    present: bool = False
    verdict: Verdict = Verdict.malformed
    cn: str = ""
    role: str = ""


def b64url_encode(data: bytes) -> str:
    """Unpadded base64url (C++ ``detail::b64url_encode``)."""
    out: list[str] = []
    for i in range(0, len(data) - len(data) % 3, 3):
        n = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
        out += (_B64[n >> 18], _B64[(n >> 12) & 63], _B64[(n >> 6) & 63], _B64[n & 63])
    rem = data[len(data) - len(data) % 3:]
    if len(rem) == 1:
        n = rem[0] << 16
        out += (_B64[n >> 18], _B64[(n >> 12) & 63])
    elif len(rem) == 2:
        n = (rem[0] << 16) | (rem[1] << 8)
        out += (_B64[n >> 18], _B64[(n >> 12) & 63], _B64[(n >> 6) & 63])
    return "".join(out)


def b64url_decode(text: str) -> bytes | None:
    """Lenient unpadded base64url, as C++: any non-alphabet character →
    ``None``; leftover bits are dropped."""
    out = bytearray()
    buf = bits = 0
    for c in text:
        v = _B64_VALUE.get(c)
        if v is None:
            return None
        buf = ((buf << 6) | v) & 0xFFFFFF
        bits += 6
        if bits >= 8:
            bits -= 8
            out.append((buf >> bits) & 0xFF)
    return bytes(out)


def hmac_sha256_hex(key: bytes, msg: bytes) -> str:
    """HMAC-SHA256 (RFC 2104), lower-case hex."""
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _atoll(raw: bytes) -> int:
    m = _ATOLL.match(raw)
    if not m:
        return 0
    return max(-(2 ** 63), min(int(m.group(1)), 2 ** 63 - 1))


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


_CONFIG_LOCK = threading.Lock()
_KEY: bytes | None = None
_TTL: int | None = None


def signing_key() -> bytes:
    """``HARPIA_SESSION_KEY`` resolved once (``b""``: sessions disabled)."""
    global _KEY
    if _KEY is None:
        with _CONFIG_LOCK:
            if _KEY is None:
                _KEY = _load_key()
    return _KEY


def _load_key() -> bytes:
    raw = os.environb.get(b"HARPIA_SESSION_KEY", b"")
    if len(raw) > 1 and raw[:1] == b"@":
        try:
            with open(raw[1:], "rb") as fh:
                return fh.read().rstrip(b"\r\n")
        except OSError:
            return b""
    return raw


def default_ttl_seconds() -> int:
    """``HARPIA_SESSION_TTL`` resolved once (``atoll``; non-positive → 900)."""
    global _TTL
    if _TTL is None:
        with _CONFIG_LOCK:
            if _TTL is None:
                n = _atoll(os.environb.get(b"HARPIA_SESSION_TTL", b""))
                _TTL = n if n > 0 else DEFAULT_TTL_SECONDS
    return _TTL


class RevocationList:
    """Revoked ``jti`` set from ``HARPIA_SESSION_REVOCATIONS``, re-read
    whenever the file's content hash changes (a missing file revokes
    nothing). Lock-guarded."""

    def __init__(self, path: str | None = None) -> None:
        self._path = os.environ.get("HARPIA_SESSION_REVOCATIONS", "") if path is None \
            else path
        self._lock = threading.Lock()
        self._stamp = b""
        self._revoked: frozenset[str] = frozenset()

    def contains(self, jti: str) -> bool:
        """True when ``jti`` is revoked right now."""
        if not jti:
            return False
        with self._lock:
            self._reload_if_changed()
            return jti in self._revoked

    def _reload_if_changed(self) -> None:
        if not self._path:
            return
        try:
            with open(self._path, "rb") as fh:
                body = fh.read()
        except OSError:
            self._revoked, self._stamp = frozenset(), b""
            return
        stamp = hashlib.sha256(body).digest()
        if stamp == self._stamp:
            return
        revoked = set()
        for line in body.split(b"\n"):
            words = line.split(b"#", 1)[0].split()
            if words:
                revoked.add(_text(words[0]))
        self._revoked, self._stamp = frozenset(revoked), stamp


_REVOCATIONS: RevocationList | None = None


def revocation_list() -> RevocationList:
    """The process-wide :class:`RevocationList` (path read on first use)."""
    global _REVOCATIONS
    if _REVOCATIONS is None:
        with _CONFIG_LOCK:
            if _REVOCATIONS is None:
                _REVOCATIONS = RevocationList()
    return _REVOCATIONS


def _split(token: str) -> tuple[str, str] | None:
    if not token.startswith("v1."):
        return None
    dot = token.rfind(".")
    if dot <= 2:
        return None
    return token[3:dot], token[dot + 1:]


def decode(token: str) -> Claims | None:
    """The payload **without** checking MAC, expiry or revocation; ``None``
    when structurally bad. Lines are read as C++ ``std::getline`` does:
    the fifth (``jti``) needs at least one byte; extra lines are ignored."""
    parts = _split(token)
    if parts is None:
        return None
    payload = b64url_decode(parts[0])
    if payload is None:
        return None
    lines = payload.split(b"\n")
    if payload.endswith(b"\n"):
        lines.pop()
    if len(lines) < 5:
        return None
    cn, role, iat, exp, jti = lines[:5]
    return Claims(cn=_text(cn), role=_text(role), jti=_text(jti),
                  issued_at=_atoll(iat), expires_at=_atoll(exp))


def issue(cn: str, role: str, ttl_seconds: int = 0, now: int = 0) -> str:
    """Mint a token for a transport-authenticated identity; ``""`` when
    sessions are disabled, ``cn`` is empty, or ``cn``/``role`` contain a
    newline. ``ttl_seconds <= 0`` → :func:`default_ttl_seconds`; ``now <= 0``
    → the current time."""
    key = signing_key()
    if not key or not cn or "\n" in cn or "\n" in role:
        return ""
    if ttl_seconds <= 0:
        ttl_seconds = default_ttl_seconds()
    if now <= 0:
        now = int(time.time())
    jti = secrets.token_hex(16)
    payload = f"{cn}\n{role}\n{now}\n{now + ttl_seconds}\n{jti}"
    b64 = b64url_encode(payload.encode("utf-8", "surrogateescape"))
    return "v1." + b64 + "." + hmac_sha256_hex(key, TOKEN_CONTEXT + b64.encode())


def verify(token: str, now: int = 0,
           sink: AuditSink | None = None) -> tuple[Verdict, Claims | None]:
    """Structure, MAC (constant time), expiry (``now >= expires_at``),
    revocation. Returns the verdict and, when ok, the claims. Records one
    ``session_denied`` event per non-ok verdict (no token bytes)."""

    def deny(verdict: Verdict, c: Claims) -> tuple[Verdict, Claims | None]:
        detail = (f"verdict={verdict.value} cn={c.cn or '<none>'} "
                  f"jti={c.jti or '<none>'}")
        (sink or default_audit_sink()).record("session_denied", "session", detail)
        return verdict, None

    key = signing_key()
    if not key:
        return deny(Verdict.no_key, Claims())
    claims = decode(token)
    parts = _split(token)
    if claims is None or parts is None:
        return deny(Verdict.malformed, Claims())
    expected = hmac_sha256_hex(key, TOKEN_CONTEXT + parts[0].encode())
    if not hmac.compare_digest(parts[1].encode("utf-8", "surrogateescape"),
                               expected.encode()):
        return deny(Verdict.bad_signature, claims)
    if now <= 0:
        now = int(time.time())
    if now >= claims.expires_at:
        return deny(Verdict.expired, claims)
    if revocation_list().contains(claims.jti):
        return deny(Verdict.revoked, claims)
    return Verdict.ok, claims


def from_authorization(header_value: str, now: int = 0,
                       sink: AuditSink | None = None) -> Bearer:
    """Parse ``Bearer <token>`` (scheme case-insensitive; a bare token also
    works) and verify it. An absent/blank header is ``present=False``."""
    tok = header_value
    if len(tok) >= 7 and tok[:7].lower() == "bearer ":
        tok = tok[7:]
    tok = tok.lstrip(" \t").rstrip(" \t\r\n")
    if not tok:
        return Bearer()
    verdict, claims = verify(tok, now, sink)
    if claims is None:
        return Bearer(present=True, verdict=verdict)
    return Bearer(present=True, verdict=verdict, cn=claims.cn, role=claims.role)
