# PyEvents — the Python target's in-process event channels

**Pipeline role / purpose:** python-target / py-events. The Python side of
`Callback/CallbackAdapter.py`: one in-process publish/subscribe channel per
`event` message. A stage of `LangBackend/python.py`'s `run_python`, after
`PyDatabaseAdapter`.

**Entry point:** `PyEventsAdapter(messages, dest, compliance).Process()` →
`None`. Nothing is written when no message is an `event`.

**Outputs** (under `<dest>/python/`):
- `harpia_runtime/events.py` (from `runtime/events.py`) + the audit sink.
- `harpia_generated/events/<name>_<hash>_events.py` per `event` message
  (`templates/events.py.tmpl`): a module-level
  `EventChannel[<name>](CacheMode.<CACHED|NOT_CACHED>, subject, phi_fields)`
  and its `<name>_channel()` accessor. Filter, cache mode and audit metadata
  come from `Callback.callback_common` (`is_event_message`,
  `cache_mode_enum`, `phi_field_names`, `audit_subject`), so the module set
  and arguments equal the C++ `events/*_events.h` (asserted by
  `test_one_module_per_cpp_event_header`).

## Runtime (`runtime/events.py` → `harpia_runtime.events`)
`CacheMode` (`CACHED` / `NOT_CACHED`), `SubscriptionId` (`int`),
`EventChannel[T]` with `subscribe` / `unsubscribe` / `publish` /
`set_audit_sink` / `cached` / `has_last` / `subscriber_count`. Same
semantics as `harpia_event_cache.h`: publish stores a copy (cached),
snapshots subscribers under a `threading.Lock`, records
`phi_event_dispatch` on the calling thread when `audit_phi_fields` is set
(even with no subscriber; never on the cached replay), then dispatches the
snapshot sequentially on one daemon thread with a `CopyFrom` copy. A
callback raising `Exception` is isolated and recorded as
`event_callback_exception` (subject or `"<event>"`).

## Key facts / gotchas
- Delivery is asynchronous: tests poll (`_wait`) rather than sleep-assert.
- Daemon threads: an in-flight dispatch doesn't keep the interpreter
  alive at exit (C++ detaches its thread the same way).
- `BaseException` (e.g. `KeyboardInterrupt`) in a callback is not caught —
  only `Exception`, per the task contract.

## Touchpoints
- Depends on: `Callback.callback_common`, `Compliance.audit_common`,
  `PyAdapter.runtime_copy`.
- Tested by: `UnitTests/test_py_events.py`.
