## Session D.3 — `ZmqAdapter` delivery wiring

Landed in `0e7e200`.

- **Depends on:** D.1 (`Message.is_critical`), D.2 (the runtime).
- **Deliverable:** for a `critical` transport-bearing message, `ZmqAdapter`
  emits a sender/publisher whose `send()`/`publish()` returns
  `::std::optional<::harpia::delivery::PushOutcome>` and *enqueues* a
  stamped `Envelope` (origin CRC + per-sender monotonic seq) into a member
  `BoundedQueue` instead of firing the socket; a new `flush()` drains it
  oldest-first (`peek()` → send → `pop()`), stopping at the first send
  failure. Ctor gains `queue_capacity` (default 128) + `AuditSink&` params.
  `templates/sender_critical.tmpl` (new); `header.h.tmpl` gains an
  `{extra_includes}` slot (empty for non-critical → byte-identical). The
  runtime + `harpia_audit_sink.h` are copied into `generated/cpp/delivery/`
  only when a `critical` transport message exists. Receiver half unchanged.
- **Out of scope:** C++ only — `JavaZmqAdapter` does not read
  `is_critical`. The Rule 4b `Mailbox` stays unwired.
- **Golden:** only `zmq/alarm_event_<hash>_zmq.h` changed; root `HASH`
  unchanged.
- **Tests:** `UnitTests/test_zmq_critical_delivery.py` (structural, pure
  Python).
