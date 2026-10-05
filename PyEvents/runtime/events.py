"""In-process publish/subscribe channels for ``event`` messages (Python port
of ``Callback/runtime/harpia_event_cache.h``).

Hand-written, copied verbatim into a generated project as
``harpia_runtime.events``. A generated
``harpia_generated/events/<name>_<hash>_events.py`` holds the one channel
per ``event`` message type and returns it from ``<name>_channel()``.

Semantics, as in C++:

- **Cache mode** is fixed at construction. :attr:`CacheMode.CACHED`
  (bare ``event``) keeps the last published value and replays it once to
  a callback that subscribes later; :attr:`CacheMode.NOT_CACHED` keeps
  nothing.
- **Asynchronous, sequential dispatch.** :meth:`EventChannel.publish`
  stores the value (cached), snapshots the subscribers under a lock and
  hands the snapshot plus a *copy* of the message to one daemon thread,
  which runs the callbacks in subscription order; ``publish`` returns at
  once. Order is kept within one publish, not across publishes.
- **Exception isolation.** A callback that raises (``Exception``) doesn't
  stop its siblings or reach the publisher; it is recorded as
  ``("event_callback_exception", subject or "<event>", "")``.
- **phi audit.** When ``audit_phi_fields`` is set, ``publish`` records one
  value-free ``("phi_event_dispatch", subject, fields)`` on the calling
  thread, whether or not anyone is subscribed. The cached replay doesn't.
- Thread-safe: subscribe / unsubscribe / publish may run concurrently.
"""
import enum
import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from google.protobuf.message import Message

from harpia_runtime.compliance.audit_sink import AuditSink, default_audit_sink

T = TypeVar("T", bound=Message)

#: identifies one subscription (never 0 for a real one)
SubscriptionId = int


class CacheMode(enum.Enum):
    """Whether a channel keeps and replays its last value."""

    CACHED = "cached"
    NOT_CACHED = "not-cached"


def _copy(msg: T) -> T:
    out = type(msg)()
    out.CopyFrom(msg)
    return out


class EventChannel(Generic[T]):
    """One in-process event channel for message type ``T``."""

    def __init__(self, mode: CacheMode, audit_subject: str = "",
                 audit_phi_fields: str = "") -> None:
        """Args:
            mode: Cached (replay the last value) or not.
            audit_subject: The table or message name used in audit records.
            audit_phi_fields: Comma-joined ``phi`` field names; non-empty
                makes every publish record ``phi_event_dispatch``.
        """
        self._mode = mode
        self._subject = audit_subject
        self._phi_fields = audit_phi_fields
        self._lock = threading.Lock()
        self._audit: AuditSink = default_audit_sink()
        self._subs: list[tuple[SubscriptionId, Callable[[T], None]]] = []
        self._last_id = 0
        self._last: T | None = None

    def set_audit_sink(self, sink: AuditSink) -> None:
        """Send this channel's audit records to ``sink`` (call at startup)."""
        with self._lock:
            self._audit = sink

    def cached(self) -> bool:
        """``True`` for a :attr:`CacheMode.CACHED` channel."""
        return self._mode is CacheMode.CACHED

    def has_last(self) -> bool:
        """``True`` once a cached channel holds a published value."""
        with self._lock:
            return self._last is not None

    def subscriber_count(self) -> int:
        """How many callbacks are registered."""
        with self._lock:
            return len(self._subs)

    def subscribe(self, callback: Callable[[T], None]) -> SubscriptionId:
        """Register ``callback``; on a cached channel holding a value it is
        dispatched once with that value (on its own thread)."""
        with self._lock:
            self._last_id += 1
            sub_id = self._last_id
            self._subs.append((sub_id, callback))
            replay = None
            if self.cached() and self._last is not None:
                replay = _copy(self._last)
            audit = self._audit
        if replay is not None:
            self._dispatch([(0, callback)], replay, audit)
        return sub_id

    def unsubscribe(self, sub_id: SubscriptionId) -> None:
        """Remove a subscription; unknown ids are ignored. A dispatch that is
        already running still completes."""
        with self._lock:
            self._subs = [s for s in self._subs if s[0] != sub_id]

    def publish(self, msg: T) -> None:
        """Fire the event; returns before any callback runs."""
        with self._lock:
            if self.cached():
                self._last = _copy(msg)
            snapshot = list(self._subs)
            audit = self._audit
        if self._phi_fields:
            audit.record("phi_event_dispatch", self._subject, self._phi_fields)
        if snapshot:
            self._dispatch(snapshot, _copy(msg), audit)

    def _dispatch(self, snapshot: list[tuple[SubscriptionId, Callable[[T], None]]],
                  value: T, audit: AuditSink) -> None:
        subject = self._subject or "<event>"

        def run() -> None:
            for _, callback in snapshot:
                try:
                    callback(value)
                except Exception:
                    audit.record("event_callback_exception", subject, "")

        threading.Thread(target=run, daemon=True).start()
