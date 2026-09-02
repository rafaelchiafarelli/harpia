// harpia ZMQ CURVE ZAP client-key allowlist -- hand-written, not generated.
// Copied verbatim into a generated project's output next to the ZMQ transport
// headers (transport-authn epic, "zmq-zap-allowlist"), the same pattern as
// harpia_grpc_mtls.h / harpia_rbac.h.
//
// The shipped CURVE transport is encryption-only: any client presenting valid
// CURVE crypto is accepted. This adds the identity layer -- an allowlist of
// authorized client public keys, enforced at the ZMTP handshake via a ZAP
// handler (RFC 27) bound to inproc://zeromq.zap.01. A key that is not on the
// allowlist is rejected even when its CURVE crypto is valid, the ZMQ analogue
// of mTLS client-certificate allowlisting.
//
// The allowlist is deployment configuration, not schema: it is read once at
// startup from the file named by the HARPIA_ZMQ_ALLOWLIST env var, one
// `<z85-client-public-key> <identity>` per line (`#` comments, blank lines
// ignored). `identity` is informational -- it correlates a key to the RBAC
// principal for the audit trail; ZAP authorizes on the key. There is no
// compiled-in key list, the same reasoning that keeps the CURVE secret keys
// themselves out of the build.
//
// Fail-safe: with no allowlist file (or an empty one) every client key is
// denied -- never "allow all". Every denial emits exactly one AuditSink record
// ("zap_denied") carrying the presented z85 key and, if known, its identity --
// never secret key material (design-rules Rule 5).
//
// Whether the handler is compiled in / started at all is a generation-time
// decision (transport_hardening_required(compliance)); this header is the
// mechanism, not that policy. `ensure_running(ctx)` is idempotent per context
// -- the generated CURVE-server socket ctors call it before binding.
#ifndef HARPIA_ZAP_H
#define HARPIA_ZAP_H

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <zmq.h>
#include <zmq.hpp>
#include <zmq_addon.hpp>

#include "harpia_audit_sink.h"

namespace harpia {
namespace zap {

// identity (z85 CURVE public key) -> optional principal name, loaded once from
// HARPIA_ZMQ_ALLOWLIST.
class AllowList {
public:
    AllowList() = default;

    static AllowList from_file(const std::string& path) {
        AllowList a;
        std::ifstream in(path);
        std::string line;
        while (std::getline(in, line)) {
            const auto hash = line.find('#');
            if (hash != std::string::npos) line.erase(hash);
            std::istringstream ls(line);
            std::string key, identity;
            if (ls >> key) {
                a.keys_.insert(key);
                if (ls >> identity) a.identity_[key] = identity;
            }
        }
        return a;
    }

    static AllowList from_env() {
        const char* p = std::getenv("HARPIA_ZMQ_ALLOWLIST");
        return (p && *p) ? from_file(p) : AllowList{};
    }

    bool contains(const std::string& z85_key) const {
        return keys_.find(z85_key) != keys_.end();
    }

    std::string identity(const std::string& z85_key) const {
        auto it = identity_.find(z85_key);
        return it == identity_.end() ? std::string() : it->second;
    }

    bool empty() const { return keys_.empty(); }

private:
    std::set<std::string> keys_;
    std::map<std::string, std::string> identity_;
};

// The ZAP handler: a REP socket on inproc://zeromq.zap.01 serviced by a
// background thread. libzmq sends it one request per client handshake on a
// CURVE_SERVER socket; the handler answers 200 (allow) or 400 (deny) based on
// the allowlist. One handler per zmq::context_t (see ensure_running).
class ZapHandler {
public:
    explicit ZapHandler(::zmq::context_t& ctx,
                        ::harpia::compliance::AuditSink& audit =
                            ::harpia::compliance::default_audit_sink())
        : audit_(audit),
          allow_(AllowList::from_env()),
          sock_(ctx, ::zmq::socket_type::rep) {
        sock_.set(::zmq::sockopt::linger, 0);
        // A finite recv timeout makes the loop periodically re-check stop_, so
        // ~ZapHandler can join the thread even when the context outlives this
        // handler (a directly-constructed one destroyed before its ctx). A
        // real ZAP request still returns immediately.
        sock_.set(::zmq::sockopt::rcvtimeo, 250);
        try {
            sock_.bind("inproc://zeromq.zap.01");
        } catch (const ::zmq::error_t&) {
            // Another ZAP handler is already serving this context (a second
            // ensure_running() path, or a caller who installed their own).
            // Become inert -- one handler per context is enough. Close the
            // socket now so it does not block zmq_ctx_term at context teardown
            // (this object may outlive the context, e.g. in ensure_running's
            // process-lifetime registry).
            inert_ = true;
            try { sock_.close(); } catch (...) {}
            return;
        }
        thread_ = std::thread([this] { loop(); });
    }

    ~ZapHandler() {
        // The loop exits and closes sock_ on context termination (ETERM); if
        // the context is still alive at teardown, nudge it here.
        stop_.store(true);
        if (thread_.joinable()) thread_.join();
        if (inert_) { try { sock_.close(); } catch (...) {} }
    }

    // False when another handler already owned inproc://zeromq.zap.01.
    bool active() const { return !inert_; }

    ZapHandler(const ZapHandler&) = delete;
    ZapHandler& operator=(const ZapHandler&) = delete;

private:
    // ZAP 1.0 request frames (RFC 27):
    //   0 version ("1.0")   1 request-id   2 domain   3 address
    //   4 identity          5 mechanism    6.. credentials
    // For CURVE the single credentials frame is the client's 32-byte public key.
    void loop() {
        while (!stop_.load()) {
            std::vector<::zmq::message_t> req;
            try {
                auto n = ::zmq::recv_multipart(
                    sock_, std::back_inserter(req), ::zmq::recv_flags::none);
                if (!n) continue;  // rcvtimeo elapsed -- re-check stop_
            } catch (const ::zmq::error_t&) {
                break;  // ETERM on context shutdown, or the socket was closed
            }
            if (req.size() < 7) continue;

            auto as_str = [](const ::zmq::message_t& m) {
                return std::string(static_cast<const char*>(m.data()), m.size());
            };
            const std::string request_id = as_str(req[1]);
            const std::string mechanism = as_str(req[5]);

            std::string z85;
            bool allowed = false;
            if (mechanism == "CURVE" && req[6].size() == 32) {
                char buf[41] = {0};
                if (::zmq_z85_encode(buf,
                                     static_cast<const uint8_t*>(req[6].data()),
                                     32) != nullptr) {
                    z85.assign(buf, 40);
                    allowed = allow_.contains(z85);
                }
            }

            if (!allowed) {
                std::string detail = "key=";
                detail += z85.empty() ? "<none>" : z85;
                const std::string who = z85.empty() ? std::string()
                                                    : allow_.identity(z85);
                if (!who.empty()) { detail += " identity="; detail += who; }
                detail += " mechanism=";
                detail += mechanism.empty() ? "<none>" : mechanism;
                audit_.record("zap_denied", "inproc://zeromq.zap.01", detail);
            }
            reply(request_id, allowed,
                  allowed ? allow_.identity(z85) : std::string());
        }
        try { sock_.close(); } catch (...) {}
    }

    void reply(const std::string& request_id, bool allowed,
               const std::string& user_id) {
        auto part = [&](const std::string& s, bool more) {
            sock_.send(::zmq::buffer(s),
                       more ? ::zmq::send_flags::sndmore
                            : ::zmq::send_flags::none);
        };
        try {
            part("1.0", true);                       // version
            part(request_id, true);                  // request-id (echo)
            part(allowed ? "200" : "400", true);     // status code
            part(allowed ? "OK" : "denied", true);   // status text
            part(user_id, true);                     // user-id
            part("", false);                         // metadata (empty)
        } catch (const ::zmq::error_t&) {
            // context going down between recv and reply -- loop will exit.
        }
    }

    ::harpia::compliance::AuditSink& audit_;
    AllowList allow_;
    ::zmq::socket_t sock_;
    std::thread thread_;
    std::atomic<bool> stop_{false};
    bool inert_ = false;
};

// Start the ZAP handler for `ctx` if it is not already running. Idempotent and
// thread-safe; the handler lives for the rest of the process (its socket is
// closed from inside on context termination so it does not block ctx teardown).
inline void ensure_running(::zmq::context_t& ctx) {
    static std::mutex m;
    static std::map<void*, std::unique_ptr<ZapHandler>> handlers;
    std::lock_guard<std::mutex> lk(m);
    void* key = static_cast<void*>(&ctx);
    if (handlers.find(key) == handlers.end()) {
        handlers.emplace(key, std::unique_ptr<ZapHandler>(new ZapHandler(ctx)));
    }
}

}  // namespace zap
}  // namespace harpia

#endif  // HARPIA_ZAP_H
