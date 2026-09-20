## Worked example: run-N-copies fan-out and load-balance apps

- **Depends on:** tasks 1, 2, 4, 5 (this packages their scenarios as
  standalone runnable binaries, it doesn't invent new ones).
- **Deliverable:** `HarpiaTest/app_example/fanout/` (mirrors the existing
  `HarpiaTest/app_example/consumer/` template's role — a maintained,
  test-guarded example a real consumer can read, not throwaway scaffolding):
  - A publisher binary + a subscriber binary (C++), where the subscriber is
    meant to be launched as N separate OS processes pointed at the same
    endpoint — demonstrates PUB/SUB fan-out as an actual multi-process
    example, not just multiple in-process objects like tasks 1/4's test
    harnesses.
  - A pusher binary + a worker binary (C++), same run-N-copies shape, for
    PUSH/PULL load-balance.
  - A short README (same shape as `HarpiaTest/app_example/consumer/README.md`)
    showing the exact commands to launch, e.g. `./subscriber &` × 3,
    `./publisher`.
  - A Java variant of at least the subscriber and worker binaries, so the
    example itself demonstrates the cross-language case from tasks 4/5, not
    only same-language.
- **Deliverable (test):** `UnitTests/test_consumer_fanout_example.py` (mirrors
  `UnitTests/test_consumer_example.py`'s shape) builds this example and runs
  a small mixed set — e.g. 1 C++ publisher + 2 C++ subscribers + 1 Java
  subscriber; 1 C++ pusher + 1 C++ worker + 1 Java worker — asserting it
  behaves as tasks 1/2/4/5 already proved, so the example never silently
  drifts from what's actually tested.
- **Out of scope:** Go/Python variants of the example (added when those
  language initiatives reach their own interop epics), a GUI or CLI wrapper
  beyond plain binaries, performance numbers.
- **Tests:** `UnitTests/test_consumer_fanout_example.py`, gated same as
  `test_consumer_example.py` (cmake+protoc+g++) plus gradle+JDK for the Java
  variant.
