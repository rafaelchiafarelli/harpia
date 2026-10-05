## ZMQ fan-out + load-balance with C++, Java and Python peers

- **Depends on:** `py-zmq` task 1 (task 2 for the CURVE variant).
- **Contract:** extend the shipped cross-language harness
  (`test_zmq_xlang_pubsub_fanout.py`, `test_zmq_xlang_pushpull_loadbalance.py`,
  `HarpiaTest/app_example/fanout/`) with Python processes as peers:
  - PUB/SUB fan-out: one publisher (rotating C++ / Python), with C++, Java
    and Python subscribers that all decode identical stamped
    `ORIGINATOR_<hash>` values;
  - PUSH/PULL load-balance: mixed-language pushers and pullers; each
    message is delivered exactly once in total;
  - a CURVE variant between C++ and Python with the ZAP allowlist enforced
    by whichever side binds (Java's CURVE has no ZAP server of its own; a
    Java CURVE client against a C++ or Python ZAP server is in scope).

  Same orchestration as today: READY/GO over stdio, event-driven, no blind
  sleeps beyond the existing slow-joiner settle.
- **Out of scope:** changing the C++/Java sides. If they need a change,
  flag it.
- **Tests:** `UnitTests/test_zmq_xlang3_*.py`, gated on
  protoc+g++ **and** gradle+JDK **and** the Python toolchain.
