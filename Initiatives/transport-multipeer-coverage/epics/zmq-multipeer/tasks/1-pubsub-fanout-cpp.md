## PUB/SUB fan-out, same language (C++)

- **Depends on:** nothing (existing shipped `ZmqAdapter` behavior).
- **Fixture:** `bed_state` (`event[cached]`) or `pump_tick` (`event[not-cached]`)
  from `HarpiaTest/Include/file3.harpia` — either is fine, pick whichever
  reads cleaner in the harness; no `.harpia` change needed.
- **Deliverable:** a new test driving one `<name>_publisher` and **3**
  `<name>_subscriber` instances (separate objects, real `tcp://` sockets —
  `inproc://` is fine only if all peers share one process/context, which is
  the realistic case here since this is proving the *socket* behavior, not
  cross-process IPC):
  - Publish N messages (N ≥ 10) after all 3 subscribers have joined and the
    slow-joiner settle window has passed (same settle-delay pattern as
    `UnitTests/test_critical_delivery_roundtrip.py`'s `_SETTLE_MS`).
  - Assert **all 3** subscribers received **all N** messages, in order,
    with correct field values (not just a count — decode and check at least
    one field per message, e.g. a monotonic counter you stamp on send).
  - A 4th subscriber that joins **after** the first burst is sent: assert it
    receives nothing from before its join, then receives a second burst sent
    after it joined — makes the slow-joiner behavior an explicit, asserted
    fact rather than an implicit assumption elsewhere.
- **Out of scope:** cross-language peers (task 4), CURVE (already covered
  1:1 by `test_stage13_zmq.py`), performance/throughput numbers.
- **Tests:** new test module (e.g. `UnitTests/test_zmq_pubsub_fanout.py`),
  protoc+g+++pkg-config-gated same as `test_stage13_zmq.py`.
