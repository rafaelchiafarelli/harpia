## `stream` lifecycle: setup / read / stop + timeout

Scoped 2026-08-29. **Task 1** of the zmq-lifecycle epic.

### What exists today

`stream` is a lexer keyword (`LexicalAnalyzer.py`: `('STREAM', r'stream ')`)
and a message-type modifier parsed into `msg.access_modifiers`, same tier as
`push`/`pull`/`event`. `ZmqAdapter` currently treats it as an **alias for
`event`** — `pub_sub = mods & {"EVENT", "STREAM"}` — so a `stream` message
just gets a PUB/SUB publisher/subscriber pair. There is **no
`setup()/read()/stop()` lifecycle API**. This task builds that.

### Decisions (settled during scoping — do not re-litigate)

- **Stream config is a runtime struct passed to `setup()`**, not `.harpia`
  DSL. No `stream[N]` bracket grammar is added (the spec says "pass the
  configurations" to `setup`, and no fixture uses brackets).
- **One `StreamStatus` enum** models every outcome (matches how
  `harpia_delivery.h` models `PushOutcome`/`PutOutcome`).
- **Additive** — the existing STREAM→PUB/SUB generation stays; the stream
  class is a new, correct consumer-side surface layered on it.
- Builds on the **already-shipped CURVE transport** — verify it meets this
  epic's guarantees, do not rebuild it.

### Contract

**Spec source:** `README.md` (~L235–245) = `harpia.process.md` §13.2
("streamming functions"): `setup(config)` may return IN-VALID; `read()` is
always timed and returns null/configurable on no-data; `stop()` kills the
connection, and if not called within a configurable window the connection is
killed and `read()` returns IN-VALID; all resources released on destruction.

**Delivered:**

```c++
enum class StreamStatus { OK, INVALID, TIMEOUT, STOPPED };
//   INVALID == the spec's "IN-VALID".

struct StreamConfig {                 // generated into the zmq runtime header
    std::string endpoint;             // tcp:// | ipc:// | inproc://
    std::string topic;                // SUB filter ("" = all)
    int    read_timeout_ms  = 1000;   // default; read(ms) overrides per call
    int    stop_deadline_ms = 30000;  // watchdog: no stop() within this of the
                                      //   last activity -> force-kill, read() -> INVALID
    int    reclaim_after_ms = 60000;  // task 2's window (declared here, enforced there)
    size_t max_records      = 10000;  // per-read cap (spec's "known maximum
                                      //   number of registers" protection)
};

struct ReadResult { StreamStatus status; std::optional<Payload> msg; };

class <name>_stream {                 // added to the message's existing <name>_<hash>_zmq.h
    StreamStatus setup(const StreamConfig&);   // INVALID on a bad config
    ReadResult   read();                       // uses config.read_timeout_ms
    ReadResult   read(int timeout_ms);
    StreamStatus stop();                       // idempotent; ZMQ_LINGER=0 then close
    ~<name>_stream();                          // RAII: release all resources, ZMQ_LINGER=0
};
```

- `read()` outcomes: `OK` + `msg` on data; `TIMEOUT` (no `msg`) on no data
  within the timeout; `STOPPED` after `stop()`; `INVALID` after the
  `stop_deadline_ms` watchdog kill.
- **Invalid-config set** (→ `setup()` returns `INVALID`): empty `endpoint`;
  `endpoint` with no `tcp://`/`ipc://`/`inproc://` scheme;
  `read_timeout_ms <= 0`; `stop_deadline_ms <= 0`; `max_records == 0`.

**Dependencies:** F1 merged (shipped). Shipped CURVE transport (verify, don't
rebuild).

**Pre-work (inside this task):**
- Add a `stream`-tagged message to `HarpiaTest/Include/file3.harpia` if the
  existing `data` / `top_users` (`stream pull push event`) don't give a
  clean single-transport stream fixture — an Include edit moves golden
  *content* for that message, not the pinned `HASH`.
- No new grammar, no Docker change.

**Tests:**
- Unit: each invalid-config case → `setup()` returns `INVALID`; a valid
  config → `OK`; `read()` after `stop()` → `STOPPED`; destroying an
  un-`stop()`'d stream does not hang (`ZMQ_LINGER=0`).
- Integration: extend `UnitTests/test_demo.py::test_demo_message_crosses_with_curve`
  with a timeout scenario — subscribe, no publisher, `read(200)` → `TIMEOUT`.
  Do **not** duplicate the existing CURVE round-trip coverage.

**Watch for (epic gotchas):**
- Z85 CURVE keys corrupt silently through `target_compile_definitions` — the
  shipped CURVE transport already uses a generated header; keep it that way.
- `ZMQ_LINGER` defaults to `-1`: a socket with an undelivered message from a
  failed handshake hangs on destruction forever. Set `ZMQ_LINGER=0` before
  every close (`stop()`, the watchdog kill, the destructor).

---
## Epic context — zmq-lifecycle

**Contract.** Full `stream` lifecycle (setup/read/stop, timeout, dead-connection
reclamation) on top of the already-shipped CURVE transport, plus a ZAP
authentication layer if this compliance context requires authenticated ZMQ.
Needs only `ComplianceContext` from Foundation. No downstream consumer named.

**Already shipped, verify only:** CURVE-secured sockets + ephemeral keypair
provisioning (`-DUSE_ZMQ_CURVE=ON`, `Assets/cmake/curve_keygen_probe.cpp`). See
`USAGE.md` §10 and `ZmqAdapter/CLAUDE.md`. Do not rebuild.

**Files.** `ZmqAdapter/`. Tests to extend: `UnitTests/test_stage13_zmq.py`
(`test_zmq_curve_roundtrip`), `UnitTests/test_demo.py`
(`test_demo_message_crosses_with_curve`).

**Watch for.** (a) Z85 CURVE keys corrupt silently through
`target_compile_definitions` — use a generated header, never compile-definitions
for key material. (b) `ZMQ_LINGER` defaults to `-1`: a socket with an undelivered
message from a failed handshake hangs on destruction forever — applies to
dead-connection reclamation and the ZAP handler both.
