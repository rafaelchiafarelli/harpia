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
//     order. subscribe()'s cached replay is dispatched the same way.
//   - Every callback invocation on the dispatch thread is wrapped in
//     try { cb(v); } catch (...) {} -- a throwing callback can neither
//     propagate to the publish()/subscribe() caller nor escape the
//     detached thread (an unhandled exception on a std::thread is
//     std::terminate). One callback throwing does not stop the rest of
//     the same dispatch. Recording the swallowed failure via AuditSink is
//     task 3, not here.
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
#include <thread>
#include <utility>
#include <vector>

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

    explicit EventChannel(CacheMode mode) : mode_(mode) {}

    // No copy/move: the generated accessor hands out a reference to a
    // single function-local static, and subscribers hold that reference.
    EventChannel(const EventChannel&) = delete;
    EventChannel& operator=(const EventChannel&) = delete;

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
        {
            std::lock_guard<std::mutex> lock(mutex_);
            id = ++last_id_;
            subs_.emplace_back(id, cb);
            if (cached() && has_last_) {
                replay = true;
                value = last_;
            }
        }
        if (replay) {
            dispatch_one(std::move(cb), std::move(value));
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

    // Fire the event: on a cached channel retain `value` as the last
    // value, snapshot the current subscribers, then dispatch them (in
    // subscription order) on one detached thread with a copy of `value`.
    // Returns immediately.
    void publish(const T& value) {
        std::vector<std::pair<SubscriptionId, Callback>> snapshot;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (cached()) {
                last_ = value;
                has_last_ = true;
            }
            snapshot = subs_;
        }
        if (snapshot.empty()) {
            return;
        }
        T copy = value;
        std::thread([snapshot = std::move(snapshot),
                     copy = std::move(copy)]() mutable {
            for (const auto& entry : snapshot) {
                try {
                    entry.second(copy);
                } catch (...) {
                    // isolation: a callback's own exception never escapes
                    // this thread (which would std::terminate) or reaches
                    // the publisher. Auditing it is task 3.
                }
            }
        }).detach();
    }

    // Test / introspection aid: how many callbacks are currently
    // registered.
    std::size_t subscriber_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return subs_.size();
    }

private:
    static void dispatch_one(Callback cb, T value) {
        std::thread([cb = std::move(cb), value = std::move(value)]() mutable {
            try {
                cb(value);
            } catch (...) {
            }
        }).detach();
    }

    const CacheMode mode_;
    mutable std::mutex mutex_;
    std::vector<std::pair<SubscriptionId, Callback>> subs_;
    SubscriptionId last_id_ = 0;
    T last_ = T();
    bool has_last_ = false;
};

}  // namespace events
}  // namespace harpia

#endif  // HARPIA_EVENTS_EVENT_CACHE_H
