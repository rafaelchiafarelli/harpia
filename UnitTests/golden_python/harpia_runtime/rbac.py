"""Three-role access control: admin / main / guest (Python port of
``Compliance/runtime/harpia_rbac.h``, transport-authn task 4).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.rbac`` whenever at least one message gets the RBAC gate
(``Database.auth_gate.effective_rbac``). It replaces the flat "message name +
hash" credential on the REST / SOAP / gRPC data operations with a role check
on the identity the transport authenticated -- the verified client
certificate's subject CommonName (:mod:`harpia_runtime.rbac_gates` wires it
into the transports).

The identity → role bindings are deployment configuration, not schema: they
are read from the file named by the ``HARPIA_RBAC_MAP`` environment variable,
one ``CN role`` pair per line, in the **same format as C++** (``#`` starts a
comment, blank and malformed lines are skipped, CRLF is fine, a later line
for the same CN wins, an unknown role name maps to :attr:`Role.none`).

Fail-safe, as in C++: an empty identity is
:attr:`Decision.unauthenticated` (HTTP 401 / ``UNAUTHENTICATED``); a verified
identity that is unmapped, or whose role may not perform the operation, is
:attr:`Decision.forbidden` (HTTP 403 / ``PERMISSION_DENIED``). With no map
file every data operation is forbidden; ``heartBeat`` alone stays open.
Every non-allow decision records exactly one ``rbac_denied`` audit event
carrying the CN, role and operation -- identity metadata only, never a
credential or field value.

**Thread safety:** the process-wide :func:`role_map` is loaded once, under a
lock, on first use, and a :class:`RoleMap` is never mutated after
:meth:`RoleMap.from_file` returns, so concurrent request threads only read
it (the property the C++ db-concurrency 1b audit checks for
``harpia_rbac.h``).
"""
import os
import threading
from enum import Enum

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink


class Role(Enum):
    """The three roles (and ``none`` for an unmapped identity)."""

    none = "none"
    guest = "guest"
    main = "main"
    admin = "admin"


class Operation(Enum):
    """Transport-neutral operation kinds: GET-list → ``list``, GET-item /
    ``pullByID`` / SOAP ``get`` → ``read``, POST / ``push`` / SOAP ``set`` →
    ``create``, PUT / SOAP ``update`` → ``update``, DELETE / SOAP ``delete``
    → ``remove``, ``streamSrc`` → ``stream``, ``heartBeat`` →
    ``heartbeat``."""

    read = "read"
    list = "list"
    create = "create"
    update = "update"
    remove = "remove"
    stream = "stream"
    heartbeat = "heartbeat"


class Decision(Enum):
    """Outcome of :func:`decide`."""

    allow = "allow"
    unauthenticated = "unauthenticated"
    forbidden = "forbidden"


def parse_role(name: str) -> Role:
    """``"admin"`` / ``"main"`` / ``"guest"`` → that role; anything else →
    :attr:`Role.none`."""
    if name in ("admin", "main", "guest"):
        return Role(name)
    return Role.none


def permitted(role: Role, op: Operation) -> bool:
    """The fixed role × operation matrix (one per project, never per
    jurisdiction)::

        admin  every operation
        main   read / list / create / update / stream   (not remove)
        guest  read / list / stream                     (read-only)

    ``heartbeat`` is open to everyone, including an unauthenticated caller.
    """
    return (op is Operation.heartbeat
            or role is Role.admin
            or (role is Role.main and op is not Operation.remove)
            or (role is Role.guest
                and op in (Operation.read, Operation.list, Operation.stream)))


class RoleMap:
    """Identity (client-certificate CN) → :class:`Role`. Read-only once
    built."""

    def __init__(self, by_cn: dict[str, Role] | None = None) -> None:
        self._by_cn: dict[str, Role] = dict(by_cn or {})

    @classmethod
    def from_file(cls, path: str) -> "RoleMap":
        """Parse a ``CN role`` file (C++ ``RoleMap::from_file``). A missing
        or unreadable file is an empty map (every data operation
        forbidden)."""
        by_cn: dict[str, Role] = {}
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    words = line.split("#", 1)[0].split()
                    if len(words) >= 2:
                        by_cn[words[0]] = parse_role(words[1])
        except OSError:
            return cls()
        return cls(by_cn)

    @classmethod
    def from_env(cls) -> "RoleMap":
        """:meth:`from_file` on ``$HARPIA_RBAC_MAP``; empty when unset."""
        path = os.environ.get("HARPIA_RBAC_MAP", "")
        return cls.from_file(path) if path else cls()

    def role_for(self, cn: str) -> Role:
        """The role bound to ``cn`` (:attr:`Role.none` when empty or
        unmapped)."""
        if not cn:
            return Role.none
        return self._by_cn.get(cn, Role.none)

    def empty(self) -> bool:
        """True when no identity is mapped."""
        return not self._by_cn


_ROLE_MAP: RoleMap | None = None
_ROLE_MAP_LOCK = threading.Lock()


def role_map() -> RoleMap:
    """The process-wide map, loaded from ``HARPIA_RBAC_MAP`` once, on first
    use (C++'s function-local static)."""
    global _ROLE_MAP
    if _ROLE_MAP is None:
        with _ROLE_MAP_LOCK:
            if _ROLE_MAP is None:
                _ROLE_MAP = RoleMap.from_env()
    return _ROLE_MAP


def decide(cn: str, op: Operation, subject: str,
           sink: AuditSink | None = None) -> Decision:
    """The gate. ``cn`` is the transport-verified identity (``""`` if none),
    ``subject`` the message name. On a non-allow decision records exactly one
    ``rbac_denied`` event (``cn=<cn|<none>> role=<role> op=<op>
    decision=<unauthenticated|forbidden>``, byte-identical to C++) on
    ``sink`` (default: :func:`default_audit_sink`)."""
    if op is Operation.heartbeat:
        return Decision.allow
    role = role_map().role_for(cn)
    if not cn:
        decision = Decision.unauthenticated
    elif permitted(role, op):
        return Decision.allow
    else:
        decision = Decision.forbidden
    detail = (f"cn={cn or '<none>'} role={role.value} op={op.value} "
              f"decision={decision.value}")
    (sink or default_audit_sink()).record("rbac_denied", subject, detail)
    return decision
