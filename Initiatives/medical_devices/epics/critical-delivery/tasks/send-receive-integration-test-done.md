## `critical` send/receive integration test

Landed in `287e01b`.

- **Depends on:** task 3.
- **Deliverable:** one of the two sensitive-data headline integration
  tests. `UnitTests/test_critical_delivery_roundtrip.py`
  (protoc+g+++pkg-config+libzmq+cppzmq-gated) drives the *generated*
  `alarm_event` transport over a real `tcp://127.0.0.1:*` socket:
  1. **Held then replayed in order.** Publish 5 while the subscriber is
     absent → `publish()` only enqueues, `pending()` grows to 5, the socket
     is never touched. Subscriber joins, 300 ms settle (`_SETTLE_MS` —
     PUB/SUB slow joiner; `flush()` can't be retried), `flush()` sends all
     5, `pending()==0`, received severity 1..5 in order.
  2. **Overflow rotates + audits.** `queue_capacity=4`, 10-message burst
     through a `CountingSink` → `"queue_rotated"` fires exactly 6×,
     `queue().rotations()==6`, `pending()` stays 4, last detail
     `dropped_seq=6`; `flush()` delivers the newest 4 (severity 7..10) in
     order.
  3. **Non-`critical` sender has no queue.** `courier_sender` has no
     `flush()`/`pending()`/`queue()` (compile-time detection traits);
     `send()` stays synchronous `bool`.
- **Note:** case 1's 300 ms settle is the one timing dependency. If a
  loaded CI box makes it flaky, bump `_SETTLE_MS` or add a
  `critical push message` fixture to `Include/file3.harpia` for a
  deterministic PUSH/PULL path (Include-only edit — pinned `HASH`
  unaffected, only golden content moves).
