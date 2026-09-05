# transport-multipeer-coverage — epics

One epic: **`zmq-multipeer`** (`zmq-multipeer/tasks/`).

## Task order

Numbered — later tasks build on earlier ones (same-language fan-out/load-
balance proven first, cross-language second, worked example last):

```
1-pubsub-fanout-cpp
2-pushpull-loadbalance-cpp
3-event-channel-under-load        (independent of 1/2 — in-process, no sockets)
        │
        ▼ (needs 1, 2 patterns proven same-language first)
4-xlang-pubsub-fanout
5-xlang-pushpull-loadbalance
        │
        ▼ (needs 1, 2, 4, 5)
6-worked-example
```

## Definition of done (every task)

- A real multi-peer run (3+ peers where the task calls for peers), not a
  parametrized re-run of the existing 1:1 test with peer-count=1.
  Every message accounted for: for fan-out, every subscriber must report
  receiving every message (no "probably" — count and compare); for
  load-balance, the union of what every puller received must equal exactly
  what was sent, no duplicates, no drops.
- No behavior change to `ZmqAdapter`/`JavaZmqAdapter` generated code expected
  — this initiative is test/harness work proving existing generated code
  already does the right thing under N peers. If a task discovers the
  generated code does NOT behave correctly under N peers, stop and flag it
  (that's a real bug, not a test-coverage gap) rather than working around it
  in the test.
- Full suite green in Docker before merging up, same as any task
  (`Docker/run.sh pytest UnitTests/`).

## Watch for

- **Slow joiner** (PUB/SUB): a subscriber connecting after the publisher has
  already sent messages can miss them — this is normal ZMQ behavior, not a
  bug. Tasks 1 and 4 make this explicit (assert on it) rather than papering
  over it with a fixed sleep and hoping.
- **`ORIGINATOR` field naming differs by topology** — bare `ORIGINATOR` for a
  many-to-* (shared) sender, `ORIGINATOR_<hash>` for a one-to-* (unique)
  sender (`Message/Variables.py AddHiddenVariables`). Both C++'s and Java's
  runtimes find it by name *prefix* via reflection, not by exact name, so
  this should already be transparent — task 4/5 confirm it stays transparent
  across the language boundary too, they don't need to special-case it.
- **Wire compatibility across languages is a protobuf-contract given, not
  something to re-verify from scratch** — C++ and Java generate off the same
  `.proto` (same field numbers, same `schema_registry/`), so the interesting
  part of tasks 4/5 is the ZMQ-level peer behavior (fan-out, load-balance),
  not "can Java decode what C++ sent" (already proven by things like
  `UnitTests/test_message_versioning_wire.py`'s cross-generation proof, and
  `test_java_zmq.py`'s own round-trip).
