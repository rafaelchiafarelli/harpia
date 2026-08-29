# Callback — Stage 13 (events): in-process event/callback channels for `event` messages

**Pipeline role:** Stage 13, transport-adjacent. Runs right after `ZmqAdapter`
(in `main.py` and `UnitTests/run_pipeline.py`). Emits one in-process
publish/subscribe channel accessor per `event` message type, plus the
hand-written `EventChannel<T>` runtime. Introduced by the `events-callbacks`
epic (`Initiatives/medical_devices/epics/events-callbacks/`), task 1
(`event[cached/not-cached]` implementation).

**Entry point:** `CallbackAdapter(messages, dest, compliance=None).Process()`
— same shape as every other adapter; called from `main.py` / `run_pipeline.py`.
Returns `None`.

**Inputs → Outputs:** the full `messages` list → `<dest>/generated/cpp/events/`:
- `<name>_<hash>_events.h` per non-enum message carrying the `event`
  modifier — defines `inline harpia::events::EventChannel<::<name>>&
  <name>_channel()`, a function-local-static singleton constructed with the
  message's `CacheMode`.
- `harpia_event_cache.h` — the generic runtime, copied verbatim (same
  "generate the thin per-type accessor, copy the generic runtime" split
  `XmlAdapter` uses for `harpia_xml.h` and the capability adapters use for
  the Dispatcher). Not golden-snapshotted.

## Files
- `callback_common.py` — tiny shared helpers (mirrors
  `Capability/capability_common.py`): `EVENT_CACHE_RUNTIME` /
  `EVENT_CACHE_RUNTIME_SRC` path constants; `is_event_message(msg)` (True
  when `access_modifiers` carries an `EVENT` token — any of `event` /
  `event[cached]` / `event[not-cached]`, all one token); `event_message_names`;
  `cache_mode_enum(msg)` → `"Cached"` / `"NotCached"` (bare `event` ==
  `Cached`, the standard).
- `CallbackAdapter.py` — the adapter. Filters to event messages, renders
  `templates/events.h.tmpl` per message, copies the runtime. No `events/`
  dir is created when there are no event messages. Stale wrappers from a
  renamed/removed message are reaped by `main.py`'s one global
  `prune_stale_outputs` pass, not here.
- `templates/events.h.tmpl` — the per-message wrapper (`str.format`
  placeholders, C++ braces escaped `{{ }}`).
- `runtime/harpia_event_cache.h` — hand-written, header-only C++.
  `namespace harpia::events`: `enum class CacheMode { Cached, NotCached }`,
  `using SubscriptionId = std::uint64_t`, `template <class T> class
  EventChannel` with `subscribe(cb) -> SubscriptionId` / `unsubscribe(id)` /
  `publish(const T&)` / `cached()` / `has_last()` / `subscriber_count()`.

## Key facts / gotchas
- **Cache mode is fixed at construction.** `Cached` retains the most
  recently published value; a callback that `subscribe`s *after* a publish
  is invoked once, immediately, with that retained value. `NotCached`
  retains nothing. Bare `event` means `Cached`.
- **Delivery is synchronous, on the calling thread, in subscription order.**
  A throwing callback propagates straight out of `publish()` / `subscribe()`.
  Detached-thread dispatch and callback-exception isolation are **task 2**
  of the epic — do not add a dispatch thread or locking to
  `harpia_event_cache.h`; task 2 owns that seam.
- **Caller-synchronised, no internal locking** — same contract as
  `harpia_capability_dispatch.h` / `harpia_delivery.h`.
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
- **AuditSink hook** on the same create/update OnChange point, for `phi`
  fields, is **task 3** of the epic — not here yet.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py`.
- Depends on: `Logger.logger`, `Util.util` (loadTemplate, write_if_different,
  copy_if_different). Consumed by: `Database/CrudlAdapter.py`
  (`is_event_message`), the generated CRUDL DAOs (`#include "events/..."`).
- Tests: `UnitTests/test_events_callbacks.py` (structural via `run_pipeline.py`
  + g++-gated runtime), `UnitTests/test_golden.py::test_event_channel_wrappers`.
