## `stream` consumer lifecycle (setup / timed read / stop / watchdog / reclamation)

- **Depends on:** tasks 1–2.
- **Contract:** for a `stream` message, a generated `<name>_stream` class
  next to the subscriber factory (port of `ZmqAdapter/templates/stream.tmpl`):
  - `StreamConfig` dataclass, same fields and defaults as C++: `endpoint`,
    `topic=""`, `read_timeout_ms=1000`, `stop_deadline_ms=30000`,
    `reclaim_after_ms=60000`, `max_records=10000`.
  - `stream_config_valid()`.
  - `setup(cfg, curve=None) -> StreamStatus`. A bad config returns
    `INVALID` and opens nothing.
  - `read(timeout_ms=None) -> ReadResult` (`OK`+msg / `TIMEOUT` /
    `STOPPED` / `INVALID`). It is always timed (`RCVTIMEO`) and never
    blocks.
  - `stop() -> STOPPED`, idempotent. Close with `linger=0`, also in
    `__exit__`/`__del__`.
  - Two **synchronous** teardowns, no timer thread, checked inside `read()`
    / `stop()`, latching `INVALID`:
    - reclamation: `reclaim_after_ms` since any inbound frame;
    - watchdog: `stop_deadline_ms` since the last usable message.

    Reclamation is checked first. Deadlines use `time.monotonic()`.
  - Not thread-safe (caller-synchronized), as in C++.
- **Out of scope:** a producer-side stream API (C++ has none beyond the
  publisher).
- **Tests:** mirroring the C++ zmq-lifecycle tests: invalid config, timed
  read, idempotent stop, watchdog trips on an idle stream, reclamation
  trips on a dead peer, garbage frames keep activity fresh but still trip
  the watchdog. Short windows in tests.
