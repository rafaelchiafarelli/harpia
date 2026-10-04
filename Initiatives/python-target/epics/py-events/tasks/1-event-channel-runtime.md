## `EventChannel` runtime + per-message channel accessors

- **Depends on:** `py-foundation` (all).
- **Contract:**
  - `harpia_runtime/events.py`, a port of `Callback/runtime/harpia_event_cache.h`
    (read `Callback/CLAUDE.md` first):
    - `CacheMode` (`CACHED`, `NOT_CACHED`; bare `event` = `CACHED`).
    - `EventChannel[T](mode, audit_subject="", audit_phi_fields="")` with
      `subscribe(cb) -> SubscriptionId`, `unsubscribe(id)`, `publish(msg)`,
      `set_audit_sink(sink)`, `cached()`, `has_last()`,
      `subscriber_count()`.
    - `publish()` stores the value (when cached), snapshots subscribers
      under a lock, and hands the snapshot + a **copy** of the message
      (`CopyFrom`) to one daemon thread that dispatches sequentially. It
      returns immediately.
    - A late `subscribe()` on a cached channel replays the last value the
      same way.
    - Exception isolation: each callback runs in `try/except Exception`. A
      raising callback doesn't stop its siblings and records
      `event_callback_exception`.
    - When `audit_phi_fields` is non-empty, `publish()` records one
      value-free `phi_event_dispatch` on the **calling** thread before
      dispatch. Cached replay does not audit.
  - Generated `harpia_generated/events/<name>_<hash>_events.py` per `event`
    message: a module-level singleton accessor `<name>_channel()`
    constructed with the message's cache mode and, for phi messages, its
    phi field names + `tableName`/name as subject. Same filter as
    `CallbackAdapter` (it reuses `Callback.callback_common` helpers by
    import).
- **Out of scope:** DAO firing (task 2). A table-less event's channel is
  application-published.
- **Tests:** mirroring `test_events_callbacks.py`:
  - cached replay vs not-cached;
  - unsubscribe;
  - publish doesn't block on a slow callback;
  - order within one publish;
  - isolation + audit;
  - phi audit on the calling thread;
  - thread-safety under concurrent subscribe/publish
    (`test_events_callbacks_scale.py` idea, scaled down).
