# Multi-peer ZMQ fan-out / load-balance — worked example

A **standalone project** that runs Harpia-generated ZMQ transport code as
real, separate OS processes — the run-N-copies packaging of the scenarios
`UnitTests/test_zmq_pubsub_fanout.py`, `test_zmq_pushpull_loadbalance.py`,
`test_zmq_xlang_pubsub_fanout.py` and `test_zmq_xlang_pushpull_loadbalance.py`
already prove structurally (transport-multipeer-coverage, `zmq-multipeer`
epic, task 6). Like [`../consumer/`](../consumer/), it does not depend on
the Harpia repo — only on a project you generate with `run_harpia.sh`.

Two independent pairs, both against `HarpiaTest/Include/file3.harpia`'s
fixtures:

- **PUB/SUB fan-out** (`pump_tick`, `event[not-cached]`) — one `publisher`,
  any number of `subscriber` copies (C++ and/or Java). Every subscriber
  receives every tick published after its own subscription has propagated.
- **PUSH/PULL load-balance** (`courier`, push-only) — one `pusher`, any
  number of `worker` copies (C++ and/or Java). ZMQ round-robins each item to
  exactly one worker; the union of what every worker processes is exactly
  what was sent.

## Build (C++)

```sh
# 1. generate a project (the bundled HarpiaTest, SQLite backend — DB is
#    irrelevant here, this example only touches the zmq/ adapter)
./run_harpia.sh HarpiaTest /tmp/gen --no-build

# 2. build this example against it
cmake -S HarpiaTest/app_example/fanout -B /tmp/fanout_build -DHARPIA_GEN=/tmp/gen
cmake --build /tmp/fanout_build
```

Inside the toolchain image (no host deps needed):

```sh
Docker/run.sh bash -c '
  HARPIA_OUTPUT_DIR=/tmp/gen python3 main.py &&
  cmake -S HarpiaTest/app_example/fanout -B /tmp/fb -DHARPIA_GEN=/tmp/gen &&
  cmake --build /tmp/fb'
```

## Run: PUB/SUB fan-out

```sh
/tmp/fanout_build/publisher &
/tmp/fanout_build/subscriber &
/tmp/fanout_build/subscriber &
/tmp/fanout_build/subscriber &
wait
```

Launch order doesn't matter — ZMQ's `tcp://` transport retries a `connect()`
lazily until the peer exists — but a subscriber started only after some
ticks have already gone out misses those (the classic PUB/SUB "slow
joiner", made an explicit assertion in `test_zmq_pubsub_fanout.py` rather
than papered over here). `publisher` sends 20 ticks by default, ~6s apart
at 300ms each — enough time to start a few subscriber terminals by hand.

## Run: PUSH/PULL load-balance

Unlike PUB/SUB, a PUSH socket only round-robins across peers it has
actually `connect()`ed to, and each bound `worker` needs its own port — so
give every worker copy a distinct endpoint and list all of them on
`pusher`'s command line:

```sh
/tmp/fanout_build/worker tcp://127.0.0.1:5571 &
/tmp/fanout_build/worker tcp://127.0.0.1:5572 &
/tmp/fanout_build/worker tcp://127.0.0.1:5573 &
/tmp/fanout_build/pusher tcp://127.0.0.1:5571 tcp://127.0.0.1:5572 tcp://127.0.0.1:5573 &
wait
```

## Java variant

[`java/`](java/) is the Java-target twin of `subscriber`/`worker` (a
standalone Gradle project, same "consume a generated project as a black
box" shape as [`../android_consumer/`](../android_consumer/)) — proving a
Java copy is just another peer alongside the C++ binaries above, not a
separately-tested code path.

```sh
# generate the Java target instead of (or alongside) the C++ one
HARPIA_GEN_LANG=java HARPIA_OUTPUT_DIR=/tmp/gen_java python3 main.py

# build this Java consumer against it
cd HarpiaTest/app_example/fanout/java
gradle build -PharpiaGenDir=/tmp/gen_java

# run a subscriber or worker copy
CP="$(gradle -q classpath -PharpiaGenDir=/tmp/gen_java | sed -n 's/^FANOUT_CLASSPATH=//p')"
java -cp "build/libs/*:$CP" com.harpia.fanout.Subscriber tcp://127.0.0.1:5561
java -cp "build/libs/*:$CP" com.harpia.fanout.Worker tcp://127.0.0.1:5573
```

Mix and match freely — a Java `Subscriber` alongside C++ `subscriber`
copies against the same `publisher`, or a Java `Worker` taking its share of
`pusher`'s round-robin alongside C++ `worker` copies, both exactly as
`test_zmq_xlang_pubsub_fanout.py` / `test_zmq_xlang_pushpull_loadbalance.py`
already prove.

## Files
- [`src/publisher.cpp`](src/publisher.cpp) / [`src/subscriber.cpp`](src/subscriber.cpp) — PUB/SUB fan-out.
- [`src/pusher.cpp`](src/pusher.cpp) / [`src/worker.cpp`](src/worker.cpp) — PUSH/PULL load-balance.
- [`CMakeLists.txt`](CMakeLists.txt) — how the generated `zmq/` headers + protobuf are wired into a build.
- [`java/`](java/) — the Java-target `Subscriber`/`Worker` twins, a standalone Gradle project.

## Notes
- Generated names are **md5-hash-qualified** (`pump_tick_<hash>_zmq.h`,
  `harpia::zmq_transport::pump_tick_publisher`); this example is pinned to
  HarpiaTest's hash (`3ac5d8b36fc7dcfb70888145147ddfb7`), same as
  [`../consumer/`](../consumer/) — regenerate from your own input and update
  the includes accordingly.
- This example's build is verified on Linux/Docker (`UnitTests/test_consumer_fanout_example.py`).
  The `WIN32` branch in `CMakeLists.txt` mirrors `../consumer/CMakeLists.txt`'s
  verified pattern but has not itself been build-verified on Windows in this
  session — say so plainly rather than implying it, per the same disclosure
  standard `USAGE.md` §16 tries to hold everywhere else.
