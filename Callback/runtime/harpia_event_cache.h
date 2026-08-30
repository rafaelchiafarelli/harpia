// harpia EventChannel -- in-process publish/subscribe for one `event`
// message type, with the cached / not-cached last-value semantics of the
// `event[cached]` / `event[not-cached]` DSL modifier (events-callbacks
// epic, task 1). Hand-written, not generated -- copied verbatim into a
// generated project the same way harpia_capability_dispatch.h and
// harpia_audit_sink.h are.
//
// One EventChannel<T> instance exists per event message type, reached
// through the generated events/<name>_<hash>_events.h accessor:
//
//   auto id = harpia::events::vitals_channel().subscribe(
//       [](const ::vitals& v) { handle(v); });
//   // ... later ...
//   harpia::events::vitals_channel().publish(some_vitals);
//   harpia::events::vitals_channel().unsubscribe(id);
//
// Cache mode (fixed at construction):
//   - Cached    : the channel retains the most recently published value.
//                 A callback that subscribes AFTER a publish is dispatched
//                 once with that retained value. This is the default --
//                 bare `event` means `event[cached]`.
//   - NotCached : nothing is retained; a late subscriber receives nothing
//                 until the next publish.
//
// Dispatch (events-callbacks epic, task 2 -- detached-thread dispatch +
// exception isolation):
//   - publish() does NOT run callbacks on the calling thread. Under the
//     channel mutex it stores the cached value and snapshots the current
//     subscriber list, then hands that snapshot plus a COPY of the value
//     to one std::thread it detach()es, and returns immediately. The
//     detached thread invokes the snapshot's callbacks in subscription
//     order. subscribe()'s cached replay is dispatched the same way. The
//     dispatch thread captures only copies -- never `this` -- so it is
//     safe for it to outlive the channel.
//   - Every callback invocation on the dispatch thread is wrapped in
//     try { cb(v); } catch (...) {} -- a throwing callback can neither
//     propagate to the publish()/subscribe() caller nor escape the
//     detached thread (an unhandled exception on a std::thread is
//     std::terminate). One callback throwing does not stop the rest of
//     the same dispatch.
//
// AuditSink (events-callbacks epic, task 3 -- OnChange audit for phi):
//   - A channel for a phi-bearing event type carries audit_subject_ (the
//     message's table/name) and audit_phi_fields_ (comma-joined phi field
//     names), baked into the generated singleton by CallbackAdapter. An
//     empty audit_phi_fields_ means the type carries no phi and the
//     channel never audits.
//   - publish() records one value-free ("phi_event_dispatch",
//     audit_subject_, audit_phi_fields_) on the CALLING thread (before the
//     dispatch thread starts), regardless of subscriber count. The cached
//     replay in subscribe() does NOT record this.
//   - a swallowed callback exception records ("event_callback_exception",
//     audit_subject_ or "<event>", "") from the dispatch thread.
//   - the sink is &harpia::compliance::default_audit_sink() (a no-op)
//     until set_audit_sink() points it at a real one -- call that once at
//     startup, before any publish. The sink must outlive every in-flight
//     dispatch. Rule 5: record() structurally cannot carry a field value.
//
// Consequences to know:
//   - Delivery is ASYNCHRONOUS. A caller that needs to observe an effect
//     must synchronise itself.
//   - Order is preserved WITHIN one publish (a single sequential dispatch
//     thread); order ACROSS two publish calls is not guaranteed.
//   - `read` never fires an event: the generated CRUDL DAO calls publish()
//     only on create/update, never on read/list/remove.
//   - std::thread needs pthread on older toolchains (modern glibc folds it
//     into libc); the tested compile paths already link it
//     (test_stage8_db / test_stage14 pass -lpthread, the consumer example
//     links Threads::Threads).
#ifndef HARPIA_EVENTS_EVENT_CACHE_H
#define HARPIA_EVENTS_EVENT_CACHE_H

#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "harpia_audit_sink.h"

namespace harpia {
namespace events {

enum class CacheMode { Cached, NotCached };

// Opaque handle returned by subscribe(), passed back to unsubscribe().
// 0 is never a live id, so it can be used as a "not subscribed" sentinel.
using SubscriptionId = std::uint64_t;

template <class T>
class EventChannel {
public:
    using Callback = std::function<void(const T&)>;

    // audit_subject / audit_phi_fields are baked in by CallbackAdapter for
    // a phi-bearing event type; both empty for a non-phi type (then the
    // channel never audits). Defaulted so a hand-written
    // `EventChannel<X> c(CacheMode::Cached)` still compiles.
    explicit EventChannel(CacheMode mode,
                          std::string audit_subject = "",
                          std::string audit_phi_fields = "")
        : mode_(mode),
          audit_subject_(std::move(audit_subject)),
          audit_phi_fields_(std::move(audit_phi_fields)) {}

    // No copy/move: the generated accessor hands out a reference to a
    // single function-local static, and subscribers hold that reference.
    EventChannel(const EventChannel&) = delete;
    EventChannel& operator=(const EventChannel&) = delete;

    // Point the channel at a real AuditSink. Call once at startup, before
    // any publish; the sink must outlive every in-flight dispatch.
    void set_audit_sink(::harpia::compliance::AuditSink& sink) {
        std::lock_guard<std::mutex> lock(mutex_);
        audit_ = &sink;
    }

    // mode_ is set once in the ctor and never mutated -> no lock needed.
    bool cached() const { return mode_ == CacheMode::Cached; }

    bool has_last() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return has_last_;
    }

    // Register a callback. On a cached channel that already holds a value,
    // the callback is dispatched once (on its own detached thread) with
    // that value; this call still returns without running user code inline.
    SubscriptionId subscribe(Callback cb) {
        SubscriptionId id;
        bool replay = false;
        T value{};
        ::harpia::compliance::AuditSink* audit = nullptr;
        std::string subject;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            id = ++last_id_;
            subs_.emplace_back(id, cb);
            if (cached() && has_last_) {
                replay = true;
                value = last_;
                audit = audit_;
                subject = audit_subject_;
            }
        }
        if (replay) {
            dispatch(snapshot_of(std::move(cb)), std::move(value), audit,
                     std::move(subject));
        }
        return id;
    }

    // Remove a previously registered callback. Unknown / already-removed
    // ids are ignored. A dispatch already in flight for this id still
    // completes (it runs off a snapshot taken at publish time).
    void unsubscribe(SubscriptionId id) {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = subs_.begin(); it != subs_.end(); ++it) {
            if (it->first == id) {
                subs_.erase(it);
                return;
            }
        }
    }

    // Fire the event: on a cached channel retain `value`, snapshot the
    // subscribers, record the phi OnChange audit (if any) on this thread,
    // then dispatch the snapshot (subscription order) on one detached
    // thread with a copy of `value`. Returns immediately.
    void publish(const T& value) {
        std::vector<std::pair<SubscriptionId, Callback>> snapshot;
        ::harpia::compliance::AuditSink* audit = nullptr;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (cached()) {
                last_ = value;
                has_last_ = true;
            }
            snapshot = subs_;
            audit = audit_;
        }
        if (!audit_phi_fields_.empty()) {
            audit->record("phi_event_dispatch", audit_subject_,
                          audit_phi_fields_);
        }
        if (snapshot.empty()) {
            return;
        }
        dispatch(std::move(snapshot), value, audit, audit_subject_);
    }

    // Test / introspection aid: how many callbacks are currently
    // registered.
    std::size_t subscriber_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return subs_.size();
    }

private:
    using Entry = std::pair<SubscriptionId, Callback>;

    static std::vector<Entry> snapshot_of(Callback cb) {
        std::vector<Entry> one;
        one.emplace_back(0, std::move(cb));
        return one;
    }

    // Run `snapshot` on one detached thread, each callback isolated by a
    // catch-all; a swallowed exception is audited. Captures only copies.
    static void dispatch(std::vector<Entry> snapshot, T value,
                         ::harpia::compliance::AuditSink* audit,
                         std::string subject) {
        std::thread([snapshot = std::move(snapshot), value = std::move(value),
                     audit, subject = std::move(subject)]() mutable {
            for (const auto& entry : snapshot) {
                try {
                    entry.second(value);
                } catch (...) {
                    if (audit != nullptr) {
                        audit->record("event_callback_exception",
                                      subject.empty() ? "<event>" : subject, "");
                    }
                }
            }
        }).detach();
    }

    const CacheMode mode_;
    const std::string audit_subject_;
    const std::string audit_phi_fields_;
    mutable std::mutex mutex_;
    ::harpia::compliance::AuditSink* audit_ =
        &::harpia::compliance::default_audit_sink();
    std::vector<Entry> subs_;
    SubscriptionId last_id_ = 0;
    T last_ = T();
    bool has_last_ = false;
};

}  // namespace events
}  // namespace harpia

#endif  // HARPIA_EVENTS_EVENT_CACHE_H
