## In-process event channel, more consumers under load

- **Depends on:** nothing (existing shipped `Callback/runtime/harpia_event_cache.h`
  behavior; `UnitTests/test_events_callbacks.py` already covers 3 callbacks
  at the correctness level — this task hardens the *scale* dimension, not
  correctness from scratch).
- **Deliverable:** extend `UnitTests/test_events_callbacks.py` (or add a
  sibling module if that file is getting crowded) with:
  - **10+ subscribers** on one `EventChannel<T>`, a burst publish (N ≥ 50),
    assert every subscriber's callback fired exactly N times with the right
    values, in the right per-publish order (builds directly on the existing
    `test_order_within_one_publish_and_unsubscribe_stops_delivery` shape,
    just more subscribers and more messages).
  - One subscriber that's deliberately slow (sleeps) or throws on every call,
    mixed in with the others: assert the well-behaved subscribers are
    unaffected — no starvation, no missed deliveries, no crash. (Builds on
    the existing `test_a_throwing_callback_is_isolated` /
    `test_detached_dispatch_does_not_block_publish` tests, combined and at
    higher subscriber count.)
- **Out of scope:** cross-process behavior (this is in-process by
  construction — `EventChannel<T>` has no socket), performance numbers.
- **Tests:** extends `UnitTests/test_events_callbacks.py`'s existing g++
  harness (no new gating — already ungated beyond a C++ compiler).
