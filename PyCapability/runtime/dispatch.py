"""Capability dispatch (Python port of
``Capability/runtime/harpia_capability_dispatch.h``, message-versioning S5).

Hand-written, copied into a generated project as
``harpia_runtime.capability.dispatch``. Transport-agnostic: whichever
transport's ``negotiate()`` produced the peer's capability set, routing "do
I know how to send this type to this peer" is the same decision::

    d = Dispatcher(lambda t: log.warning("peer can't take %s", t))
    d.on("users", send_users)
    d.dispatch("users", peer_caps)   # send_users("users") iff covered

The fallback is **mandatory** (no default): a type the peer doesn't cover,
or one with no registered handler, always reaches it -- never a silent
no-op. Not thread-safe while handlers are being registered; ``dispatch`` on
a fully set-up dispatcher only reads.
"""
from collections.abc import Callable, Collection

#: called with the message type name
Handler = Callable[[str], None]


class Dispatcher:
    """Routes a message type to its handler iff the peer covers it."""

    def __init__(self, fallback: Handler) -> None:
        self._fallback = fallback
        self._handlers: dict[str, Handler] = {}

    def on(self, message_type: str, handler: Handler) -> None:
        """Register (or replace) the handler for ``message_type``."""
        self._handlers[message_type] = handler

    def dispatch(self, message_type: str, peer_capabilities: Collection[str]) -> None:
        """Call the handler when ``message_type`` is in ``peer_capabilities``
        and has one; otherwise the fallback."""
        handler = self._handlers.get(message_type)
        if message_type in peer_capabilities and handler is not None:
            handler(message_type)
            return
        self._fallback(message_type)
