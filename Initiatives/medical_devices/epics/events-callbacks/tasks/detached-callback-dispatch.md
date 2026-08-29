
## Detached-thread callback dispatch + exception isolation

- **Depends on:** task 1 merged (done — `event-cache-implementation`).

### Contract

**Scope:** `Callback/runtime/harpia_event_cache.h` only. **No generated
output changes** — the per-message `events/<name>_<hash>_events.h`
accessor, `CallbackAdapter`, the CRUDL `publish(msg)` call sites, and every
golden snapshot are untouched. Only the hand-written `EventChannel<T>`
runtime's internals change.

**Delivers:**

1. **Detached-thread dispatch.** `publish(const T& value)` no longer runs
   callbacks on the calling thread. Under a `std::mutex` it updates the
   cached last value and snapshots the current subscriber list, then hands
   that snapshot + a **copy** of `value` to a single `std::thread` that it
   `detach()`es; `publish()` returns immediately. The detached thread
   invokes the snapshot's callbacks in subscription order. The cached
   replay in `subscribe()` (a `Cached` channel with a last value) is
   likewise dispatched on its own detached thread with a copy of the last
   value, so `subscribe()` also returns without running user code inline.

2. **Exception isolation.** Each callback invocation on the dispatch
   thread is wrapped in `try { cb(v); } catch (...) {}` — a throwing
   callback can neither propagate to the `publish()` / `subscribe()`
   caller nor escape the detached thread (an unhandled exception on a
   `std::thread` is `std::terminate`, so the catch-all is what keeps a bad
   callback from crashing the process). One callback throwing does not
   stop the remaining callbacks in the same dispatch from running.
   (Recording the swallowed failure via `AuditSink` is **task 3**, not
   here — task 2 only isolates.)

3. **Thread safety.** `subs_`, `last_`, `has_last_`, `last_id_` are all
   guarded by one `std::mutex`; `subscribe` / `unsubscribe` / `publish` /
   `cached` / `has_last` / `subscriber_count` are safe to call
   concurrently from any thread. The task-1 "caller-synchronised, no
   internal locking" note is replaced.

**Behaviour changes to call out (documented in the header + tests
updated):**
- Delivery is now **asynchronous**. Callers that need to observe an effect
  synchronise themselves (the tests use an atomic counter + a bounded
  wait).
- Ordering is preserved **within a single `publish`** (one dispatch
  thread, sequential). Ordering **across** two `publish` calls is not
  guaranteed — each spawns its own detached thread.
- `std::thread` — tested compile paths already link threads
  (`test_stage8_db.py` / `test_stage14.py` pass `-lpthread`; the consumer
  example links `Threads::Threads`); modern glibc folds pthread into libc.
  The header carries a one-line note for older toolchains.

### Pre-work

None. Task 1 is merged; the runtime file exists.

### Tests — extend `UnitTests/test_events_callbacks.py`

The three existing g++ runtime tests assumed synchronous delivery — they
gain a small `wait_for(pred, timeout)` helper (poll an atomic with a hard
deadline) instead of asserting immediately after `publish` / `subscribe`.
New coverage:
- **exception isolation:** a subscriber whose callback always `throw`s,
  followed by a normal subscriber — publish; the process does not crash,
  `publish()` itself never throws, and the normal subscriber still runs
  (assert its counter advances within the deadline).
- **detached / async:** `publish()` returns before a deliberately slow
  (sleep) callback has finished — the callback's "done" flag is still
  false immediately after `publish()` returns, true after a wait.
- **concurrency:** N threads each calling `publish` while another thread
  churns `subscribe`/`unsubscribe` — no crash / sanitiser complaint, and
  the surviving subscriber's delivered count is `>0` and `<= N`.

Structural tests (CRUDL wiring, `events/` wrappers, golden) are unchanged
and must stay green.

### Acceptance

New functionality on the event path, nothing pre-existing to preserve.
Green: the extended `test_events_callbacks.py` and the full Docker suite
with no new regressions.
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
