# Callback — Stage 13 (events): in-process event/callback channels for `event` messages

**Pipeline role:** Stage 13, transport-adjacent. Runs right after `ZmqAdapter`
(in `main.py` and `UnitTests/run_pipeline.py`). Emits one in-process
publish/subscribe channel accessor per `event` message type, plus the
hand-written `EventChannel<T>` runtime. The `events-callbacks` epic
(`Initiatives/medical_devices/epics/events-callbacks/`): task 1
(`event[cached/not-cached]`), task 2 (detached-thread dispatch + callback
exception isolation), task 3 (OnChange `AuditSink` for `phi`).

**Entry point:** `CallbackAdapter(messages, dest, compliance=None).Process()`
— same shape as every other adapter; called from `main.py` / `run_pipeline.py`.
Returns `None`.

**Inputs → Outputs:** the full `messages` list → `<dest>/generated/cpp/events/`:
- `<name>_<hash>_events.h` per non-enum message carrying the `event`
  modifier — defines `inline harpia::events::EventChannel<::<name>>&
  <name>_channel()`, a function-local-static singleton constructed with the
  message's `CacheMode`.
- `harpia_event_cache.h` + `harpia_audit_sink.h` — the generic runtime and
  its Foundation-F3 audit dependency, copied verbatim (same "generate the
  thin per-type accessor, copy the generic runtime" split `XmlAdapter` uses
  for `harpia_xml.h`, and the runtime+audit pair `ZmqAdapter` ships into
  `delivery/`). Neither is golden-snapshotted.

## Files
- `callback_common.py` — tiny shared helpers (mirrors
  `Capability/capability_common.py`): `EVENT_CACHE_RUNTIME` /
  `EVENT_CACHE_RUNTIME_SRC` + `EVENT_RUNTIME_COPIES` (the cache runtime +
  its `harpia_audit_sink.h`); `is_event_message(msg)` (True when
  `access_modifiers` carries an `EVENT` token — any of `event` /
  `event[cached]` / `event[not-cached]`, all one token);
  `event_message_names`; `cache_mode_enum(msg)` → `"Cached"` /
  `"NotCached"`; `phi_field_names(msg)` / `audit_subject(msg)` (the value-free
  OnChange-audit metadata baked into the channel ctor — empty for non-phi).
- `CallbackAdapter.py` — the adapter. Filters to event messages, renders
  `templates/events.h.tmpl` per message, copies `EVENT_RUNTIME_COPIES`. No
  `events/` dir when there are no event messages. Stale wrappers from a
  renamed/removed message are reaped by `main.py`'s one global
  `prune_stale_outputs` pass, not here.
- `templates/events.h.tmpl` — the per-message wrapper (`str.format`
  placeholders, C++ braces escaped `{{ }}`); the channel ctor takes
  `CacheMode`, `audit_subject`, `audit_phi_fields`.
- `runtime/harpia_event_cache.h` — hand-written, header-only C++
  (`#include "harpia_audit_sink.h"` same-dir). `namespace harpia::events`:
  `enum class CacheMode { Cached, NotCached }`, `using SubscriptionId =
  std::uint64_t`, `template <class T> class EventChannel(CacheMode,
  std::string audit_subject = "", std::string audit_phi_fields = "")` with
  `subscribe(cb) -> SubscriptionId` / `unsubscribe(id)` / `publish(const
  T&)` / `set_audit_sink(AuditSink&)` / `cached()` / `has_last()` /
  `subscriber_count()`.

## Key facts / gotchas
- **Cache mode is fixed at construction.** `Cached` retains the most
  recently published value; a callback that `subscribe`s *after* a publish
  is dispatched once with that retained value. `NotCached` retains nothing.
  Bare `event` means `Cached`.
- **Dispatch is detached-thread + exception-isolated (task 2).** `publish()`
  updates the cached value and snapshots the subscriber list under a
  `std::mutex`, then hands the snapshot + a **copy** of the value to one
  `std::thread` it `detach()`es and returns — it does **not** run callbacks
  on the calling thread. `subscribe()`'s cached replay is dispatched the
  same way. Each callback runs inside `try { … } catch (...) {}`, so a
  throwing callback neither propagates to the `publish()`/`subscribe()`
  caller nor `std::terminate`s the process, and its siblings still run —
  the swallowed exception is recorded as `("event_callback_exception",
  audit_subject_ or "<event>", "")` (task 3).
- **Delivery is asynchronous.** A caller that needs to observe an effect
  synchronises itself. Order is preserved **within** one `publish` (a
  single sequential dispatch thread); order **across** two `publish` calls
  is not guaranteed. `std::thread` needs pthread on old toolchains (modern
  glibc folds it in); the tested compile paths already link it.
- **Thread-safe.** `subs_` / `last_` / `has_last_` / `last_id_` are guarded
  by one `std::mutex`; `subscribe` / `unsubscribe` / `publish` / `has_last`
  / `subscriber_count` are safe to call concurrently. (`cached()` is
  lock-free — `mode_` is `const`.)
- **`read` never fires an event.** For an `event` message that also owns a
  table, `Database/CrudlAdapter.py` makes the generated DAO `#include` this
  module's `events/<name>_<hash>_events.h` and call
  `<name>_channel().publish(msg)` at the end of a successful `create()` and
  `update()` — and nowhere in `read()` / `list()` / `remove()`. A
  table-less `event` message gets the accessor but no DAO firing (the
  application publishes into `<name>_channel()` itself).
- **Flag-only in the front end.** The `event[cached]` / `event[not-cached]`
  bracket rides inside the single `EVENT` token's lexeme
  (`LexicalAnalizer/LexicalAnalyzer.py`) and `Message.py` reads it into
  `Message.event_cache_mode`; the emitted `.proto` is byte-identical to the
  same message with bare `event`. Keeping one token type means
  `ZmqAdapter` / `JavaZmqAdapter` / `Util.util` one-to-many detection (which
  keys off the token type) is untouched.
- **AuditSink hook — OnChange audit for `phi` (task 3), in two places:**
  - **`EventChannel<T>`.** The channel holds an `AuditSink*` (default
    `&default_audit_sink()`, a no-op; `set_audit_sink(AuditSink&)` retargets
    it — call once at startup, the sink must outlive in-flight dispatches)
    plus two `const std::string`s baked into the generated singleton by
    `CallbackAdapter`: `audit_subject_` (the message's `tableName` or name)
    and `audit_phi_fields_` (comma-joined `phi` field names). When
    `audit_phi_fields_` is non-empty, `publish()` records one value-free
    `("phi_event_dispatch", subject, phi_fields)` on the **calling** thread
    (before the dispatch thread starts, regardless of subscriber count; the
    cached replay in `subscribe()` does not). Empty ⇒ non-phi type ⇒ never
    audits. `harpia_event_cache.h` `#include`s `harpia_audit_sink.h`
    same-dir; `CallbackAdapter` copies `Compliance/runtime/harpia_audit_sink.h`
    into `generated/cpp/events/` alongside the cache runtime (`EVENT_RUNTIME_COPIES`).
  - **The CRUDL DAO.** A message that is *both* `event` and `phi`-bearing
    gets one extra `audit_.record("phi_event_onchange", "<table>",
    "<phi cols>")` immediately after the `publish(msg)` call in `create()`
    and `update()` (reusing the DAO's existing `AuditSink&`). Distinct op
    name — `phi_event_onchange` = "a persisted phi change reached the event
    bus". A non-phi event DAO and a phi non-event DAO are byte-identical.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py`.
- Depends on: `Logger.logger`, `Util.util` (loadTemplate, write_if_different,
  copy_if_different), `Compliance.audit_common` (the F3 audit-sink runtime
  path, via `callback_common`). Consumed by: `Database/CrudlAdapter.py`
  (`is_event_message`), the generated CRUDL DAOs (`#include "events/..."`).
- Tests: `UnitTests/test_events_callbacks.py` (structural via `run_pipeline.py`
  + g++-gated runtime + protoc-gated round-trip),
  `UnitTests/test_golden.py::test_event_channel_wrappers`.
