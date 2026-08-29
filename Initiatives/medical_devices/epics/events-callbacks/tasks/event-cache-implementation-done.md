## `event[cached/not-cached]` implementation

**Done 2026-08-29** — implemented exactly as scoped below. Lexer `EVENT`
rule carries the optional `[cached|not-cached]` bracket in its lexeme;
`Message.event_cache_mode`; new `Callback/` module (`harpia_event_cache.h`
`EventChannel<T>` runtime + `callback_common.py` + `CallbackAdapter`
emitting `events/<name>_<hash>_events.h` channel singletons); CRUDL DAO
fires `<name>_channel().publish(msg)` on create/update for table-bearing
event messages; `bed_state` (`event[cached]`) + `pump_tick`
(`event[not-cached]`) fixtures in `file3.harpia`;
`UnitTests/test_events_callbacks.py` + `test_golden.py::test_event_channel_wrappers`.
Task 2 (detached dispatch + exception isolation) and task 3 (AuditSink on
OnChange + integration) remain.

- **Depends on:** F1 (Foundation) — present on `dev`. No other epic.

### Contract

**In (DSL surface).** The `event` message-type modifier gains an optional
cache-mode bracket, mirroring `renamed_from[<old>]`'s single-token shape:

| written | cache mode |
|---|---|
| `event message M { … }` | `cached` (the standard when unspecified) |
| `event[cached] message M { … }` | `cached` |
| `event[not-cached] message M { … }` | `not-cached` |

Order-independent with the other message-type modifiers (`critical`,
`stream`, `pull`, `push`) exactly as bare `event` is today. Flag-only in
the front end: the emitted `.proto` for an `event[...]` message is
byte-identical to the same message with bare `event` (same rule as `phi`
/ `critical`). The lexer keeps emitting a single `EVENT` token for all
three forms — the bracket text rides in the token lexeme — so
`ZmqAdapter` / `JavaZmqAdapter` / `Util.util` one-to-many detection is
untouched.

**Delivers.**

1. `Message.event_cache_mode` ∈ `{None, "cached", "not-cached"}` on every
   parsed message (`None` ⇔ no `event` modifier). Set in `Message.py`
   next to `is_critical`; shown in `Message.__str__`.

2. **`Callback/` module** (new, sibling of `Capability/`):
   - `Callback/runtime/harpia_event_cache.h` — hand-written, header-only
     C++, copied verbatim into a generated project the same way
     `harpia_capability_dispatch.h` is. `namespace harpia::events`:
     - `enum class CacheMode { Cached, NotCached };`
     - `template <class T> class EventChannel` — an in-process
       (single-process) publish/subscribe channel for one event message
       type `T`:
       - `SubscriptionId subscribe(std::function<void(const T&)>)` —
         registers the callback. On a **cached** channel that already has
         a last value, the new callback is invoked once, immediately,
         with that value (synchronously, on the subscribing thread —
         detached dispatch is task 2).
       - `void unsubscribe(SubscriptionId)`.
       - `void publish(const T&)` — on a **cached** channel stores the
         value as the last value; then invokes every current subscriber
         once, synchronously, in subscription order.
       - `bool cached() const`, `bool has_last() const`.
     - Caller-synchronised, no internal locking (same contract as
       `harpia_capability_dispatch.h` / `harpia_delivery.h`).
     - A throwing callback propagates to the `publish` / `subscribe`
       caller — **exception isolation is task 2's deliverable**, called
       out in a header comment so task 2 has an obvious seam.
   - `Callback/callback_common.py` — `EVENT_CACHE_RUNTIME` /
     `EVENT_CACHE_RUNTIME_SRC` path constants + `event_message_names()`
     helper (mirrors `Capability/capability_common.py`).
   - `Callback/CallbackAdapter.py` — `CallbackAdapter(messages, dest,
     compliance=None).Process()`. For every non-enum message whose
     `access_modifiers` carry `EVENT`, emits
     `generated/cpp/events/<name>_<hash>_events.h`: includes the runtime +
     the message's `protofiles/<name>_<hash>.pb.h`, and defines
     `inline harpia::events::EventChannel<::<name>>& <name>_channel()` —
     a function-local-static singleton constructed with the message's
     `CacheMode`. Copies `harpia_event_cache.h` into
     `generated/cpp/events/` when it emitted at least one wrapper.
     Driving it with only non-event messages creates no `events/` dir.
   - Wired into `main.py` and `UnitTests/run_pipeline.py` right after
     `ZmqAdapter` (events are transport-adjacent). `run_pipeline.py` also
     snapshots `generated/cpp/events/<name>_<hash>_events.h` into
     `golden/events/` (the static `harpia_event_cache.h` copy is **not**
     snapshotted — same convention as `harpia_xml.h` / the capability
     runtime).

3. **Firing on create / change / update (`read` never fires).** For an
   `event` message that also owns a table, the generated CRUDL DAO
   (`Database/CrudlAdapter.py` + `crudl.h.tmpl`) `#include`s
   `events/<name>_<hash>_events.h` and calls
   `::harpia::events::<name>_channel().publish(msg);` at the end of a
   successful `create()` and `update()` — and nowhere in `read()`,
   `list()`, or `remove()`. Realised with the same empty-placeholder
   technique as the `phi` audit hook, so a non-event DAO is byte-identical.
   A table-less `event` message gets the channel wrapper but no DAO
   firing (the application publishes into `<name>_channel()` directly).

**Out of scope (later tasks in this epic).**
- Detached-thread dispatch + callback-exception isolation → task 2.
- `AuditSink` hook on the same OnChange point for `phi` fields, and the
  subscribe→mutate→assert integration test → task 3.
- Cross-transport (ZMQ) delivery of the cached last-value on subscribe —
  the ZMQ PUB/SUB path is unchanged here; this task is the in-process
  channel only.

### Pre-work

None needing code. The one new fixture need — an `event[not-cached]`
message and an explicit `event[cached]` message — is small, table-less,
and added to `HarpiaTest/Include/file3.harpia` (the standing "extend the
shared Include fixture, don't fork" convention); it moves golden
*content* for the two new messages only and leaves every pinned `HASH`
alone (root `test.harpia` text unchanged).

### Tests — `UnitTests/test_events_callbacks.py` (new)

- **Structural (pure Python, always run)** via `run_pipeline.py`:
  - `pump_tick` parses with `event_cache_mode: not-cached`; `bed_state`
    with `cached`; bare-`event` `alarm_event` with `cached`.
  - the emitted `.proto` for `pump_tick` / `bed_state` carries no
    `cached` / `not-cached` / bracket trace (flag-only).
  - `generated/cpp/events/harpia_event_cache.h` is copied;
    `pump_tick_<hash>_events.h` names `CacheMode::NotCached`,
    `bed_state_<hash>_events.h` / `alarm_event_<hash>_events.h` name
    `CacheMode::Cached`.
  - `alarm_event_<hash>_crudl.h` includes `events/alarm_event_<hash>_events.h`
    and calls `alarm_event_channel().publish(` inside `create` and
    `update` only — not `read` / `list` / `remove`. A non-event table
    message (`beacon_log`) has neither.
  - `CallbackAdapter` driven with a lone non-event message writes no
    `events/` directory.
- **Runtime (g++-gated, `-Werror`, standalone — same harness shape as
  `test_audit_sink.py` / `test_delivery_runtime.py`):**
  - cached channel: `publish(v1)` then a late `subscribe` fires the
    callback immediately with `v1`; a subsequent `publish(v2)` fires it
    with `v2`.
  - not-cached channel: `publish(v1)` then a late `subscribe` does **not**
    fire; the next `publish(v2)` does.
  - multiple subscribers fire in subscription order; `unsubscribe` stops
    delivery to that one.

### Acceptance

New functionality, nothing pre-existing to preserve on the event path.
Green: the new unit tests, the regenerated golden snapshots reviewed, and
the full Docker suite with no new regressions. (Note: `test_proto_files` /
`test_messages` are already red on a fresh `dev` checkout — unrelated
`schema_registry` field-number drift, see the handoff note.)
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
