## `critical` delivery runtime + queued sender/publisher

- **Depends on:** task 1; `py-foundation` task 4.
- **Contract:**
  - `harpia_runtime/delivery.py`, a port of
    `Compliance/runtime/harpia_delivery.h`:
    - `Envelope.stamp(seq, payload)` with CRC-32 IEEE (`zlib.crc32`, the
      same polynomial `0xEDB88320` as the C++ self-contained CRC) and
      `crc_ok()`;
    - `check_on_arrival() -> Arrival` (`Ok` / `CrcMismatch` / `SeqGap` /
      `SeqRegressed`);
    - `BoundedQueue(capacity)`: `push -> PushOutcome` (`Accepted` /
      `RotatedOldest`, with a `queue_rotated` audit), `pop`, `peek`,
      `rotations`, `last_rotated_seq`;
    - `Mailbox` (`put -> PutOutcome`, `mailbox_overwritten` audit);
    - not thread-safe (caller-synchronized), as in C++.
  - A `critical` message's generated sender/publisher factory returns a
    queued variant:
    - `send()`/`publish()` returns `PushOutcome | None` and enqueues a
      stamped envelope (seq starts at 1);
    - `flush()` drains oldest-first and stops at the first socket failure;
    - extra args `queue_capacity=128` and `audit_sink`;
    - `pending()` and `queue()` accessors.

    **Only the payload goes on the wire**: the envelope stays local, as in
    C++ `sender_critical.tmpl`.
- **Out of scope:** arrival-side checking wired into receivers (C++ Phase
  3c, not done there either). The `Mailbox` stays unwired, matching C++.
- **Tests:**
  - Unit tests mirroring `test_delivery_runtime.py` (CRC vectors equal to
    C++'s, rotation audited, peek non-destructive).
  - Generated-project: a transient receiver gap loses nothing within
    capacity, and overflow rotates with an audit
    (`test_critical_delivery_roundtrip.py` shape).
