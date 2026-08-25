// harpia Stage 13 (ZMQ capability handshake) runtime, hand-written, not
// generated. See plans/message-versioning.md S5.
//
//     auto types = harpia::capability::negotiate(ctx, "tcp://peer:5560", 2s, [] {
//         // a peer that predates this feature (nothing bound to the
//         // endpoint, or unreachable within the timeout) -- a NAMED
//         // outcome, not a hang or a guess.
//     });
//     if (types) { ... }  // the peer's real, current message-type set
//
// Dispatcher lives in capability/harpia_capability_dispatch.h (transport-
// agnostic, shared with the gRPC and HTTP capability runtimes).
#ifndef HARPIA_ZMQ_CAPABILITY_RUNTIME_H
#define HARPIA_ZMQ_CAPABILITY_RUNTIME_H

#include <chrono>
#include <cstring>
#include <functional>
#include <optional>
#include <set>
#include <string>

#include <zmq.hpp>
#include "protofiles/capabilities_service.pb.h"

namespace harpia {
namespace capability {

// Queries a peer's advertised message-type set over a fresh REQ socket
// connected to `endpoint`, with a real receive timeout (ZMQ_RCVTIMEO).
// ZMQ's async connect means send() on a REQ socket normally succeeds even
// against a peer that never shows up (it just queues) -- the real signal
// here, as with any ZMQ request/reply, is recv() timing out: no responder
// bound at all (a peer that predates this feature), or one that's
// unreachable/too slow within `timeout`. Either way resolves uniformly to
// the plan's "legacy peer, no capability set" outcome: on_legacy_peer()
// fires exactly once and this returns std::nullopt, never a silent empty
// set and never a hang. linger=0 so a socket left with an unanswered
// request doesn't block on destruction (same ZMQ_LINGER gotcha documented
// for CURVE in ZmqAdapter/CLAUDE.md).
inline std::optional<std::set<std::string>> negotiate(
        ::zmq::context_t& ctx, const std::string& endpoint,
        std::chrono::milliseconds timeout,
        const std::function<void()>& on_legacy_peer = [] {}) {
    ::zmq::socket_t req(ctx, ::zmq::socket_type::req);
    req.set(::zmq::sockopt::rcvtimeo, static_cast<int>(timeout.count()));
    req.set(::zmq::sockopt::linger, 0);
    req.connect(endpoint);

    ::frameworkProtos::capabilities_Request request;
    std::string bytes;
    request.SerializeToString(&bytes);
    ::zmq::message_t frame(bytes.size());
    std::memcpy(frame.data(), bytes.data(), bytes.size());
    if (!req.send(frame, ::zmq::send_flags::none).has_value()) {
        on_legacy_peer();
        return std::nullopt;
    }

    ::zmq::message_t reply;
    if (!req.recv(reply, ::zmq::recv_flags::none).has_value()) {
        on_legacy_peer();
        return std::nullopt;
    }
    ::frameworkProtos::capabilities_Response response;
    if (!response.ParseFromArray(reply.data(), static_cast<int>(reply.size()))) {
        on_legacy_peer();
        return std::nullopt;
    }
    std::set<std::string> types;
    for (const auto& t : response.message_types()) types.insert(t);
    return types;
}

}  // namespace capability
}  // namespace harpia

#endif  // HARPIA_ZMQ_CAPABILITY_RUNTIME_H
