# Transport Multi-Peer Coverage: Proving Fan-Out and Load-Balance Actually Work With More Than One Peer

**Status: scoped, not started.**

## 1. Why this exists

A 2026-09-02/03 planning session surfaced a real gap: harpia's ZMQ transport
supports two peer topologies at the protocol level —

- **PUB/SUB fan-out** (`event`/`stream` messages): one publisher, any number
  of subscribers, every subscriber gets every message.
- **PUSH/PULL load-balance** (`push`/`pull` messages): one sender, any number
  of pullers, ZMQ round-robins each message to exactly one puller.

— but the test suite only ever proves the **1-publisher-to-1-subscriber** and
**1-sender-to-1-receiver** case. `UnitTests/test_stage13_zmq.py`,
`UnitTests/test_critical_delivery_roundtrip.py`, `UnitTests/test_demo.py` are
all 1:1. Nothing asserts that N subscribers all receive a published stream, or
that N pullers actually split a workload. The in-process `event` callback
channel (`UnitTests/test_events_callbacks.py`) is the one exception — it
already drives 3 callbacks on one channel — but that's threads in a single
process, not separate peers/binaries.

Separately: C++ and Java are both real, shipped ZMQ implementations today
(`ZmqAdapter/`, `JavaZmqAdapter/`) generated from the *same* schema with the
*same* wire numbers, and nothing proves they interoperate as peers of each
other, only that each works against itself.

## 2. Scope

**In scope, now:** C++ and Java, both already shipped. One epic,
`zmq-multipeer`:
- N-subscriber PUB/SUB fan-out, same language (C++).
- N-puller PUSH/PULL load-balance, same language (C++).
- Hardening the existing in-process event-channel test for more subscribers
  and load.
- Cross-language (C++ + Java) versions of the fan-out and load-balance cases.
- One small worked-example app pair, runnable as N copies, so this isn't only
  provable by reading test code.

**Out of scope, deferred to later initiatives:**
- **Go and Python peers.** `Initiatives/go-target/`'s `tri-language-interop`
  epic and `Initiatives/python-target/`'s `quad-language-interop` epic extend
  the exact scenarios below to add those languages as they ship — this
  initiative builds the harness and scenarios once, they don't get
  re-invented per language.
- CURVE/ZAP under multi-peer (single-peer CURVE is already covered by
  `test_stage13_zmq.py`; multi-peer CURVE is not asked for here — flag it
  separately if wanted later).
- DDS multi-peer (DDS already has its own pub/sub proof, `test_dds_demo.py`
  1:1; out of scope here, this initiative is ZMQ/in-process only).

## 3. Non-goals

**This is explicitly not a performance initiative.** No throughput/latency
numbers, no backpressure tuning, no large peer counts. "Not the bare minimum"
means proving N>1 actually behaves correctly (every subscriber gets every
message; work is actually distributed, not silently serialized onto one
puller) — 3-4 peers is enough to prove that. A peer count that would only add
runtime, not additional confidence, is out of scope.

## 4. Epics

One epic: **`zmq-multipeer`** (`epics/README.md`).

## 5. Verification approach

Same posture as the rest of the suite: protoc/g++/pkg-config-gated for the
C++-only tasks (mirrors `test_stage13_zmq.py`'s gating), additionally
gradle+JDK-gated for the cross-language tasks (mirrors
`UnitTests/test_java_zmq.py`). Runs inside the existing `harpia-build` Docker
image — no new toolchain needed (C++ and JDK 17 + Gradle 8.5 are both already
present). Reuses existing fixtures where they already fit
(`HarpiaTest/Include/file3.harpia`'s `courier` (push-only), `sensor_feed`
(stream), `bed_state`/`pump_tick` (event) — see each task file for which).
