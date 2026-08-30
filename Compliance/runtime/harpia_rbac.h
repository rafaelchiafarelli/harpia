// harpia RBAC gate -- hand-written, not generated. Copied verbatim into a
// generated project's output next to the transport headers (transport-authn
// epic, task 4), the same pattern as harpia_audit_sink.h.
//
// Replaces the flat "message name + hash" credential check on the REST / SOAP /
// gRPC data operations with a three-role model -- admin / main / guest -- keyed
// on the identity the transport authenticated:
//   - REST / SOAP: the verified client-certificate subject CommonName
//     (`crow::request::client_cert_cn`, a harpia patch to vendored Crow -- see
//     third_party/crow/VENDORED.md).
//   - gRPC: the x509 CN from `ServerContext::auth_context()`.
//
// The identity -> role bindings are deployment configuration, not schema: they
// are read at startup from a file (path in the HARPIA_RBAC_MAP env var), one
// `CN role` per line. There is no compiled-in identity list -- the same
// reasoning that keeps the mTLS certificates themselves out of the build.
//
// Fail-safe: an empty identity is `unauthenticated` (HTTP 401 /
// UNAUTHENTICATED); a verified-but-unmapped identity, or one whose role may not
// perform the operation, is `forbidden` (HTTP 403 / PERMISSION_DENIED). With no
// map file present every data operation is forbidden -- heartBeat alone stays
// open, matching its pre-RBAC behaviour. Every non-allow decision emits exactly
// one AuditSink record ("rbac_denied") carrying the CN, role and operation --
// identity metadata only, never a credential value (design-rules Rule 5).
//
// Whether RBAC is compiled into the gate at all is a generation-time decision
// (`transport_hardening_required(compliance)`); this header is the mechanism,
// not that policy.
#ifndef HARPIA_RBAC_H
#define HARPIA_RBAC_H

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>

#include "harpia_audit_sink.h"

namespace harpia {
namespace rbac {

enum class Role { none, guest, main, admin };

// Transport-neutral operation kinds. REST verbs and gRPC RPCs both map onto
// these: GET-list -> list, GET-item / pullByID -> read, POST / push -> create,
// PUT -> update, DELETE -> remove, streamSrc -> stream, heartBeat -> heartbeat.
enum class Operation { read, list, create, update, remove, stream, heartbeat };

enum class Decision { allow, unauthenticated, forbidden };

inline const char* role_name(Role r) {
    switch (r) {
        case Role::admin: return "admin";
        case Role::main:  return "main";
        case Role::guest: return "guest";
        default:          return "none";
    }
}

inline Role parse_role(const std::string& s) {
    if (s == "admin") return Role::admin;
    if (s == "main")  return Role::main;
    if (s == "guest") return Role::guest;
    return Role::none;
}

inline const char* op_name(Operation op) {
    switch (op) {
        case Operation::read:      return "read";
        case Operation::list:      return "list";
        case Operation::create:    return "create";
        case Operation::update:    return "update";
        case Operation::remove:    return "remove";
        case Operation::stream:    return "stream";
        case Operation::heartbeat: return "heartbeat";
    }
    return "?";
}

// The fixed role x operation matrix -- one per project, never per-jurisdiction
// (master plan section 0a). heartBeat is open to everyone (including an
// unauthenticated caller), unchanged from before RBAC.
//   admin  every operation
//   main   read / list / create / update / stream   (not remove)
//   guest  read / list / stream                     (read-only)
inline constexpr bool permitted(Role role, Operation op) {
    return op == Operation::heartbeat
        || role == Role::admin
        || (role == Role::main
            && op != Operation::remove)
        || (role == Role::guest
            && (op == Operation::read || op == Operation::list
                || op == Operation::stream));
}

// identity (client-cert CN) -> role, loaded once from HARPIA_RBAC_MAP.
class RoleMap {
public:
    RoleMap() = default;

    static RoleMap from_file(const std::string& path) {
        RoleMap m;
        std::ifstream in(path);
        std::string line;
        while (std::getline(in, line)) {
            // strip a trailing CR (CRLF files) and a `#` comment
            const auto hash = line.find('#');
            if (hash != std::string::npos) line.erase(hash);
            std::istringstream ls(line);
            std::string cn, role;
            if (ls >> cn >> role) m.by_cn_[cn] = parse_role(role);
        }
        return m;
    }

    static RoleMap from_env() {
        const char* p = std::getenv("HARPIA_RBAC_MAP");
        return (p && *p) ? from_file(p) : RoleMap{};
    }

    Role role_for(const std::string& cn) const {
        if (cn.empty()) return Role::none;
        auto it = by_cn_.find(cn);
        return it == by_cn_.end() ? Role::none : it->second;
    }

    bool empty() const { return by_cn_.empty(); }

private:
    std::unordered_map<std::string, Role> by_cn_;
};

// Process-wide map, loaded lazily on first use (thread-safe static init).
inline const RoleMap& role_map() {
    static const RoleMap m = RoleMap::from_env();
    return m;
}

// The gate. `cn` is the transport-verified identity ("" if none). On any
// non-allow decision, emits exactly one AuditSink record and returns the
// decision so the caller can map it to 401/403 or UNAUTHENTICATED/
// PERMISSION_DENIED.
inline Decision decide(const std::string& cn, Operation op,
                       const std::string& subject,
                       ::harpia::compliance::AuditSink& audit =
                           ::harpia::compliance::default_audit_sink()) {
    if (op == Operation::heartbeat) return Decision::allow;

    const Role role = role_map().role_for(cn);
    Decision d;
    if (cn.empty()) {
        d = Decision::unauthenticated;
    } else if (permitted(role, op)) {
        return Decision::allow;
    } else {
        d = Decision::forbidden;   // verified identity, role may not do this
    }

    std::string detail = "cn=";
    detail += cn.empty() ? "<none>" : cn;
    detail += " role=";
    detail += role_name(role);
    detail += " op=";
    detail += op_name(op);
    detail += (d == Decision::unauthenticated) ? " decision=unauthenticated"
                                               : " decision=forbidden";
    audit.record("rbac_denied", subject, detail);
    return d;
}

}  // namespace rbac
}  // namespace harpia

#endif  // HARPIA_RBAC_H
