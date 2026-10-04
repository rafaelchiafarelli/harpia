"""CURVE client-key allowlist enforced at the ZMQ handshake (Python port of
``ZmqAdapter/runtime/harpia_zap.h``).

Hand-written, copied into a generated project as ``harpia_runtime.zap`` under
a hardened compliance profile, where every bind-side CURVE socket calls
:func:`ensure_running` before it becomes a CURVE server.

- :class:`AllowList` reads ``HARPIA_ZMQ_ALLOWLIST`` in the C++ format: one
  ``<z85 public key> [identity]`` per line, whitespace-separated; blank
  lines skipped. A line is a comment only when its first token starts with
  ``#`` **and** is not a valid 40-character Z85 key -- ``#`` is a Z85 digit,
  so a key may start with it (fixes/000005). An identity token starting with
  ``#`` is ignored.
- :class:`ZapHandler` serves ZAP 1.0 (RFC 27) on ``inproc://zeromq.zap.01``
  from one daemon thread: ``200`` for a listed CURVE client key, ``400``
  otherwise. **Fail-safe:** no file or an empty file denies every key. Each
  denial records one value-free ``zap_denied`` audit (the z85 public key,
  identity and mechanism -- never secret material).
- :func:`ensure_running` starts one handler per context, idempotently. A
  handler that finds the endpoint already bound (another handler serves the
  context) becomes inert instead of raising.

Shut a context with a running handler down with ``ctx.term()`` after
closing your own sockets -- the handler's thread then sees
``ContextTerminated`` and closes its socket itself. Never ``ctx.destroy()``:
it closes the handler's socket from another thread while the handler is
using it, and libzmq aborts.

Written by hand rather than with ``zmq.auth.ThreadAuthenticator``: that
reads certificate directories, not this allowlist file, and has no audit
hook, so it could not match the C++ format, fail-safe default and audit.
"""
import os
import threading
import weakref
from typing import Any

import zmq
from zmq.utils import z85

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink

#: the ZAP endpoint libzmq consults (RFC 27)
ZAP_ENDPOINT = "inproc://zeromq.zap.01"
#: environment variable naming the allowlist file
ALLOWLIST_ENV = "HARPIA_ZMQ_ALLOWLIST"
#: the Z85 alphabet (ZeroMQ RFC 32), which includes ``#``
Z85_ALPHABET = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    ".-:+=^!/*?&<>()[]{}@%$#")


def is_z85_key(token: str) -> bool:
    """``True`` for a 40-character Z85 string (a CURVE public key)."""
    return len(token) == 40 and all(c in Z85_ALPHABET for c in token)


class AllowList:
    """The set of CURVE client public keys allowed to connect."""

    def __init__(self, entries: dict[str, str] | None = None) -> None:
        #: z85 key → identity (``""`` when the line names none)
        self._entries = dict(entries or {})

    @classmethod
    def from_file(cls, path: str) -> "AllowList":
        """Parse ``path``; a missing or unreadable file gives an empty list."""
        entries: dict[str, str] = {}
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return cls()
        for line in lines:
            tokens = line.split()
            if not tokens:
                continue
            key = tokens[0]
            if key.startswith("#") and not is_z85_key(key):
                continue  # comment line
            has_identity = len(tokens) > 1 and not tokens[1].startswith("#")
            identity = tokens[1] if has_identity else ""
            entries[key] = identity
        return cls(entries)

    @classmethod
    def from_env(cls) -> "AllowList":
        """The file named by ``HARPIA_ZMQ_ALLOWLIST`` (unset/empty → empty)."""
        path = os.environ.get(ALLOWLIST_ENV, "")
        return cls.from_file(path) if path else cls()

    def contains(self, z85_key: str) -> bool:
        """Is this z85 public key allowed?"""
        return z85_key in self._entries

    def identity(self, z85_key: str) -> str:
        """The identity listed for the key, or ``""``."""
        return self._entries.get(z85_key, "")

    def empty(self) -> bool:
        """``True`` when no key is allowed (every handshake is denied)."""
        return not self._entries


class ZapHandler:
    """Answers ZAP requests for one context from :class:`AllowList.from_env`."""

    def __init__(self, ctx: zmq.Context[Any],
                 audit_sink: AuditSink | None = None) -> None:
        self._audit = audit_sink or default_audit_sink()
        self._allow = AllowList.from_env()
        self._stop = threading.Event()
        self._socket: zmq.Socket[bytes] = ctx.socket(zmq.REP)
        self._socket.setsockopt(zmq.LINGER, 0)
        # a finite timeout lets the loop notice stop() without a request
        self._socket.setsockopt(zmq.RCVTIMEO, 250)
        try:
            self._socket.bind(ZAP_ENDPOINT)
        except zmq.ZMQError:
            self._inert = True  # another handler already serves this context
            self._socket.close(linger=0)
            self._thread: threading.Thread | None = None
            return
        self._inert = False
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="harpia-zap")
        self._thread.start()

    def active(self) -> bool:
        """``False`` when another handler already owned the endpoint."""
        return not self._inert

    def stop(self) -> None:
        """Stop serving (joins the thread; the context stays usable)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                request = self._socket.recv_multipart()
            except zmq.Again:
                continue
            except zmq.ZMQError:
                break  # context terminated or socket closed
            if len(request) < 7:
                continue
            request_id, mechanism = request[1], request[5].decode("ascii", "replace")
            key = ""
            if mechanism == "CURVE" and len(request[6]) == 32:
                encoded: bytes = z85.encode(request[6])  # type: ignore[no-untyped-call]
                key = encoded.decode("ascii")
            allowed = bool(key) and self._allow.contains(key)
            if not allowed:
                detail = "key=" + (key or "<none>")
                who = self._allow.identity(key) if key else ""
                if who:
                    detail += " identity=" + who
                detail += " mechanism=" + (mechanism or "<none>")
                self._audit.record("zap_denied", ZAP_ENDPOINT, detail)
            user = self._allow.identity(key).encode() if allowed else b""
            try:
                self._socket.send_multipart([
                    b"1.0", request_id, b"200" if allowed else b"400",
                    b"OK" if allowed else b"denied", user, b""])
            except zmq.ZMQError:
                break
        self._socket.close(linger=0)


_handlers: "weakref.WeakKeyDictionary[zmq.Context[Any], ZapHandler]" = (
    weakref.WeakKeyDictionary())
_lock = threading.Lock()


def ensure_running(ctx: zmq.Context[Any],
                   audit_sink: AuditSink | None = None) -> ZapHandler:
    """Start the ZAP handler for ``ctx`` unless one already runs (idempotent).

    ``audit_sink`` only applies when this call starts the handler.
    """
    with _lock:
        handler = _handlers.get(ctx)
        if handler is None:
            handler = ZapHandler(ctx, audit_sink)
            _handlers[ctx] = handler
        return handler
