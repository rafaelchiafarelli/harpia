## QoS mapping (`critical` ↔ reliable/keep-all, else best-effort/keep-last-1)

- **Depends on:** task 1.
- **Contract:** the generated writer/reader QoS per message, from
  `msg.is_critical`, exactly as `DdsAdapter`:
  - `critical`: `Reliable` + `KeepAll` + `ResourceLimits(max_samples=128,
    …)` (`QUEUE_DEPTH` mirrors ZMQ's queue capacity);
  - otherwise `BestEffort` + `KeepLast(1)`.

  The reader mirrors the writer. `Durability` is left `Volatile` (a
  documented open question in C++; not decided here).
- **Bar:** a Python reader matches a C++ writer of the same message under
  both profiles.
- **Tests:** structural (QoS per message); behavioral mirroring
  `test_dds_demo.py`: critical survives a transient reader gap, and
  non-critical collapses to the newest.
