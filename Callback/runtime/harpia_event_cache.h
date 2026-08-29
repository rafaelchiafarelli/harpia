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
//                 A callback that subscribes AFTER a publish is invoked
//                 once, immediately, with that retained value. This is the
//                 default -- bare `event` means `event[cached]`.
//   - NotCached : nothing is retained; a late subscriber receives nothing
//                 until the next publish.
//
// Delivery is synchronous and on the calling thread, in subscription
// order. Detached-thread dispatch and isolation of a callback's own
// exception are TASK 2 of this epic -- here a throwing callback propagates
// straight out of publish() / subscribe(). Do not add locking or a
// dispatch thread in this file; task 2 owns that seam.
//
// Threading: caller-synchronised, no internal locking -- same contract as
// harpia_capability_dispatch.h / harpia_delivery.h. `read` never fires an
// event: the generated CRUDL DAO calls publish() only on create/update,
// never on read/list/remove.
#ifndef HARPIA_EVENTS_EVENT_CACHE_H
#define HARPIA_EVENTS_EVENT_CACHE_H

#include <cstdint>
#include <functional>
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

    bool cached() const { return mode_ == CacheMode::Cached; }
    bool has_last() const { return has_last_; }

    // Register a callback. On a cached channel that already holds a value,
    // the callback is invoked once, immediately, with that value (before
    // this call returns).
    SubscriptionId subscribe(Callback cb) {
        const SubscriptionId id = ++last_id_;
        subs_.emplace_back(id, std::move(cb));
        if (cached() && has_last_) {
            subs_.back().second(last_);
        }
        return id;
    }

    // Remove a previously registered callback. Unknown / already-removed
    // ids are ignored.
    void unsubscribe(SubscriptionId id) {
        for (auto it = subs_.begin(); it != subs_.end(); ++it) {
            if (it->first == id) {
                subs_.erase(it);
                return;
            }
        }
    }

    // Fire the event: on a cached channel retain `value` as the last
    // value, then invoke every current subscriber once, in subscription
    // order. Iterates over a copy so a callback may unsubscribe itself (or
    // another) without invalidating the walk.
    void publish(const T& value) {
        if (cached()) {
            last_ = value;
            has_last_ = true;
        }
        const std::vector<std::pair<SubscriptionId, Callback>> snapshot = subs_;
        for (const auto& entry : snapshot) {
            entry.second(value);
        }
    }

    // Test / introspection aid: how many callbacks are currently
    // registered.
    std::size_t subscriber_count() const { return subs_.size(); }

private:
    CacheMode mode_;
    std::vector<std::pair<SubscriptionId, Callback>> subs_;
    SubscriptionId last_id_ = 0;
    T last_ = T();
    bool has_last_ = false;
};

}  // namespace events
}  // namespace harpia

#endif  // HARPIA_EVENTS_EVENT_CACHE_H
