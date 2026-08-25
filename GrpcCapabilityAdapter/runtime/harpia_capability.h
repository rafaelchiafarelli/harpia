// harpia Stage 13 (gRPC capability handshake) runtime, hand-written, not
// generated. See plans/message-versioning.md S5.
//
//     auto types = harpia::capability::negotiate(channel, 2s, [] {
//         // a peer that predates this feature, or one that's unreachable
//         // within the deadline -- a NAMED outcome, not a hang or a guess.
//     });
//     if (types) { ... }  // the peer's real, current message-type set
//
// Dispatcher (route a message type to a handler, or a mandatory fallback
// when the peer's set doesn't cover it) is transport-agnostic and lives in
// capability/harpia_capability_dispatch.h, shared with the HTTP and ZMQ
// capability runtimes -- see that header.
#ifndef HARPIA_CAPABILITY_RUNTIME_H
#define HARPIA_CAPABILITY_RUNTIME_H

#include <chrono>
#include <functional>
#include <memory>
#include <optional>
#include <set>
#include <string>

#include <grpcpp/grpcpp.h>
#include "protofiles/capabilities_service.grpc.pb.h"

namespace harpia {
namespace capability {

// Queries a peer's advertised message-type set via the generated
// capabilities_Service, with a real deadline. Any non-OK outcome (the peer
// never registered the service -- UNIMPLEMENTED -- or never answered within
// `timeout` -- DEADLINE_EXCEEDED, or any other transport failure) is
// resolved uniformly to the same "legacy peer, no capability set" outcome
// the plan calls for: on_legacy_peer fires exactly once and this returns
// std::nullopt, never a silent empty set and never a hang.
inline std::optional<std::set<std::string>> negotiate(
        const std::shared_ptr<::grpc::ChannelInterface>& channel,
        std::chrono::milliseconds timeout,
        const std::function<void()>& on_legacy_peer = [] {}) {
    auto stub = ::frameworkProtos::capabilities_Service::NewStub(channel);
    ::grpc::ClientContext ctx;
    ctx.set_deadline(std::chrono::system_clock::now() + timeout);
    ::frameworkProtos::capabilities_Request req;
    ::frameworkProtos::capabilities_Response resp;
    const ::grpc::Status status = stub->GetCapabilities(&ctx, req, &resp);
    if (!status.ok()) {
        on_legacy_peer();
        return std::nullopt;
    }
    std::set<std::string> types;
    for (const auto& t : resp.message_types()) types.insert(t);
    return types;
}

}  // namespace capability
}  // namespace harpia

#endif  // HARPIA_CAPABILITY_RUNTIME_H
