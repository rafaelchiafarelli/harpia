// harpia message-versioning capability dispatch (plans/message-versioning.md
// S5), hand-written, not generated. Transport-agnostic -- shared verbatim by
// GrpcCapabilityAdapter, HttpCapabilityAdapter, and ZmqCapabilityAdapter's
// generated output, since routing "do I know how to send this type to this
// peer" is the same decision regardless of which transport's negotiate()
// (see each adapter's own runtime/) produced the peer's capability set.
#ifndef HARPIA_CAPABILITY_DISPATCH_H
#define HARPIA_CAPABILITY_DISPATCH_H

#include <functional>
#include <map>
#include <set>
#include <string>
#include <utility>

namespace harpia {
namespace capability {

// Routes a message type name to its registered handler iff the peer's
// capability set includes it; otherwise calls the mandatory fallback --
// structurally never a silent no-op (the constructor requires one, there is
// no default). Harpia generates this dispatch scaffolding; the schema
// author supplies the actual handlers and fallback logic, same "harpia
// wires the capability, caller supplies the logic" precedent as
// Database/MigrationAdapter's data_transform hook.
class Dispatcher {
public:
    using Handler = std::function<void(const std::string&)>;

    explicit Dispatcher(Handler fallback) : fallback_(std::move(fallback)) {}

    void on(const std::string& message_type, Handler handler) {
        handlers_[message_type] = std::move(handler);
    }

    void dispatch(const std::string& message_type,
                  const std::set<std::string>& peer_capabilities) const {
        if (peer_capabilities.count(message_type)) {
            auto it = handlers_.find(message_type);
            if (it != handlers_.end()) {
                it->second(message_type);
                return;
            }
        }
        fallback_(message_type);
    }

private:
    std::map<std::string, Handler> handlers_;
    Handler fallback_;
};

}  // namespace capability
}  // namespace harpia

#endif  // HARPIA_CAPABILITY_DISPATCH_H
