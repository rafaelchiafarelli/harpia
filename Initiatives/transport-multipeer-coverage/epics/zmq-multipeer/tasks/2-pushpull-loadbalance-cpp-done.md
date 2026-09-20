## PUSH/PULL load-balance, same language (C++)

- **Depends on:** nothing (existing shipped `ZmqAdapter` behavior).
- **Fixture:** `courier` (push-only) from `HarpiaTest/Include/file3.harpia` —
  or `users`/`top_users` (push+pull+event) from `HarpiaTest/test.harpia` if a
  pull-capable-both-ways message reads better; either is a valid PUSH sender.
- **Deliverable:** a new test driving one `<name>_sender` and **3**
  `<name>_receiver` instances, all bound to the same PUSH sender's connect
  target (standard ZMQ PUSH/PULL: pullers `bind`, the pusher `connect`s and
  round-robins — confirm against `ZmqAdapter/CLAUDE.md`'s stated roles before
  wiring the harness, since which side binds matters for the topology):
  - Send 30 messages, each stamped with a distinct sequence number.
  - Assert: the union of what the 3 pullers received is exactly the 30 sent
    (no message lost, none duplicated across pullers).
  - Assert real distribution happened: no single puller received all 30 (a
    loose bound like "each puller got at least 1" is enough — this is not a
    fairness/perf test, just proof the work didn't silently serialize onto
    one receiver).
- **Out of scope:** exact round-robin fairness guarantees (ZMQ's own
  contract, not harpia's to re-prove precisely), CURVE, performance numbers.
- **Tests:** new test module (e.g. `UnitTests/test_zmq_pushpull_loadbalance.py`),
  protoc+g+++pkg-config-gated.
