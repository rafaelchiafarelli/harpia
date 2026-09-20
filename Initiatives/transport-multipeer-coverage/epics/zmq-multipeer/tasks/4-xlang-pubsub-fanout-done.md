## Cross-language PUB/SUB fan-out (C++ + Java)

- **Depends on:** task 1 (same-language fan-out pattern proven first).
- **Fixture:** same message as task 1, generated once for C++
  (`HARPIA_GEN_LANG` default) and once for Java (`HARPIA_GEN_LANG=java`)
  from the *same* `.harpia` input, so both share wire numbers.
- **Deliverable:** one publisher (either language — C++ publisher is the
  simpler harness, mirrors `test_demo.py`'s existing cross-language-adjacent
  process shape) and subscribers split across languages: at least 2 C++
  subscribers + 1 Java subscriber (`JavaZmqAdapter`'s `HarpiaZmq.Receiver`
  SUB role, per `JavaZmqAdapter/CLAUDE.md`).
  - Assert every subscriber, in both languages, receives every published
    message with correct field values.
  - Confirm the `ORIGINATOR`-prefix reflection lookup each runtime uses
    (`ZmqAdapter`'s C++ side, `HarpiaZmq`'s Java side) agrees on the same
    stamped value regardless of which language's runtime wrote it — this
    should already be transparent by construction (see epics/README.md
    "Watch for"), this task is where that gets an actual assertion instead
    of an assumption.
- **Out of scope:** Go/Python peers (later initiatives extend this exact
  scenario, see `Initiatives/transport-multipeer-coverage/README.md` §2),
  CURVE.
- **Tests:** new test module, protoc+g+++pkg-config **and** gradle+JDK-gated
  (same combined gating as `UnitTests/test_java_zmq.py`).
