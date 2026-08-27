## Session D.2 — delivery-guarantee runtime (transport-agnostic)

Landed in `3581933`.

- **Depends on:** D.1 (conceptually — no code dependency).
- **Deliverable:** `Compliance/runtime/harpia_delivery.h` (`harpia::delivery`),
  shaped like `harpia_capability_dispatch.h`:
  - `Envelope` — origin CRC-32 (self-contained, no zlib) + monotonic seq;
    `crc_ok()` verifies at a boundary; `check_on_arrival()` →
    `Arrival{Ok, CrcMismatch, SeqGap, SeqRegressed}`.
  - `BoundedQueue` (Rule 4a) — FIFO, fixed capacity, overflow drops the
    OLDEST + `"queue_rotated"` `AuditSink` record + `rotations()` count;
    `peek()` / `pop()`.
  - `Mailbox` (Rule 4b) — single slot, `put()` overwrites +
    `"mailbox_overwritten"` record.
  - Not thread-safe (caller-synchronized). No payload parsing (Rule 2).
  - `Compliance/delivery_common.py` — path constant + `harpia_audit_sink.h`
    co-copy dependency.
- **Out of scope:** wiring it to any transport (D.3); the `Mailbox` stays
  unwired for now.
- **Tests:** `UnitTests/test_delivery_runtime.py` (g++-gated, `-Werror`,
  standalone compile).
