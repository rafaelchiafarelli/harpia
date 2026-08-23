// harpia Stage 11/12 (HTTP capability handshake) runtime, hand-written, not
// generated. See plans/message-versioning.md S5.
//
//     auto types = harpia::capability::negotiate(
//         "peer.example.com", 8080, "/api/v1", 2000, [] {
//             // a peer that predates this feature (no /capabilities route,
//             // or unreachable within the timeout) -- a NAMED outcome, not
//             // a hang or a guess.
//         });
//     if (types) { ... }  // the peer's real, current message-type set
//
// Dispatcher lives in capability/harpia_capability_dispatch.h (transport-
// agnostic, shared with the gRPC and ZMQ capability runtimes).
//
// Crow (the server side of REST/SOAP) ships no HTTP client of its own --
// same reason tests/harpia_test_client.h exists. detail::http_get below is
// a trimmed, GET-only, single-purpose sibling of that test client (real
// connect + read timeouts via a raw blocking socket; no default headers, no
// POST/PUT/DELETE -- this runtime only ever needs one GET), so generated
// projects don't have to vendor a full HTTP client library just to ask a
// peer "what do you support."
#ifndef HARPIA_HTTP_CAPABILITY_RUNTIME_H
#define HARPIA_HTTP_CAPABILITY_RUNTIME_H

#include <cstdlib>
#include <cstring>
#include <functional>
#include <optional>
#include <set>
#include <string>

#include <google/protobuf/util/json_util.h>
#include "protofiles/capabilities_service.pb.h"

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using harpia_cap_sockfd_t = SOCKET;
static constexpr harpia_cap_sockfd_t kHarpiaCapInvalidSocket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
using harpia_cap_sockfd_t = int;
static constexpr harpia_cap_sockfd_t kHarpiaCapInvalidSocket = -1;
#endif

namespace harpia {
namespace capability {
namespace detail {

#ifdef _WIN32
inline void ensure_winsock() {
    struct Init {
        Init() { WSADATA wsa; WSAStartup(MAKEWORD(2, 2), &wsa); }
        ~Init() { WSACleanup(); }
    };
    static Init init;
}
inline void close_socket(harpia_cap_sockfd_t fd) { ::closesocket(fd); }
#else
inline void ensure_winsock() {}
inline void close_socket(harpia_cap_sockfd_t fd) { ::close(fd); }
#endif

struct HttpGetResult {
    bool ok = false;
    int status = 0;
    std::string body;
};

// Blocking HTTP/1.1 GET over a fresh connection ("Connection: close"), with
// a single timeout applied to both connect and read (good enough for a
// one-shot capability query; not a general-purpose client).
inline HttpGetResult http_get(const std::string& host, int port,
                              const std::string& path, int timeout_ms) {
    HttpGetResult r;
    ensure_winsock();

    harpia_cap_sockfd_t fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd == kHarpiaCapInvalidSocket) return r;

    ::sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
        close_socket(fd);
        return r;
    }

#ifdef _WIN32
    DWORD tv = static_cast<DWORD>(timeout_ms);
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO,
                 reinterpret_cast<const char*>(&tv), sizeof tv);
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO,
                 reinterpret_cast<const char*>(&tv), sizeof tv);
#else
    ::timeval tv{timeout_ms / 1000, (timeout_ms % 1000) * 1000};
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
#endif

    if (::connect(fd, reinterpret_cast<::sockaddr*>(&addr), sizeof addr) != 0) {
        close_socket(fd);
        return r;
    }

    std::string req = "GET " + path + " HTTP/1.1\r\n";
    req += "Host: " + host + ":" + std::to_string(port) + "\r\n";
    req += "Connection: close\r\n\r\n";
    size_t sent = 0;
    while (sent < req.size()) {
        long n = ::send(fd, req.data() + sent,
                        static_cast<int>(req.size() - sent), 0);
        if (n <= 0) { close_socket(fd); return r; }
        sent += static_cast<size_t>(n);
    }

    std::string raw;
    char buf[4096];
    for (;;) {
        long n = ::recv(fd, buf, sizeof buf, 0);
        if (n > 0) { raw.append(buf, static_cast<size_t>(n)); continue; }
        if (n == 0) break;  // peer closed (Connection: close)
        close_socket(fd);  // timeout (EAGAIN/EWOULDBLOCK/WSAETIMEDOUT) or error
        return r;
    }
    close_socket(fd);

    const size_t sp = raw.find(' ');
    if (sp == std::string::npos) return r;
    r.status = std::atoi(raw.c_str() + sp + 1);
    const size_t hdr_end = raw.find("\r\n\r\n");
    if (hdr_end != std::string::npos) r.body = raw.substr(hdr_end + 4);
    r.ok = r.status != 0;
    return r;
}

}  // namespace detail

// Queries a peer's advertised message-type set via GET <base>/capabilities,
// with a real connect+read timeout. Any failure (connection refused, a
// timeout, a non-200 status -- e.g. a peer that predates this feature and
// has no /capabilities route at all -- or a body that doesn't parse as
// capabilities_Response) resolves uniformly to the plan's "legacy peer, no
// capability set" outcome: on_legacy_peer() fires exactly once and this
// returns std::nullopt, never a silent empty set and never a hang.
inline std::optional<std::set<std::string>> negotiate(
        const std::string& host, int port, const std::string& base,
        int timeout_ms,
        const std::function<void()>& on_legacy_peer = [] {}) {
    const auto resp = detail::http_get(host, port, base + "/capabilities",
                                       timeout_ms);
    if (!resp.ok || resp.status != 200) {
        on_legacy_peer();
        return std::nullopt;
    }
    ::frameworkProtos::capabilities_Response response;
    if (!::google::protobuf::util::JsonStringToMessage(resp.body, &response).ok()) {
        on_legacy_peer();
        return std::nullopt;
    }
    std::set<std::string> types;
    for (const auto& t : response.message_types()) types.insert(t);
    return types;
}

}  // namespace capability
}  // namespace harpia

#endif  // HARPIA_HTTP_CAPABILITY_RUNTIME_H
