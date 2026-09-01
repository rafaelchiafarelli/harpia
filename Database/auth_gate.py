"""Access-gate code fills for the generated REST / SOAP / gRPC transports
(transport-authn epic -- flat credential gate in tasks 2/3, three-role RBAC in
task 4).

One place decides, per transport, what the `{{auth_*}}` placeholders in
`templates/{{rest,soap,grpc_service}}.h.tmpl` render to, so the three adapters
stay thin. The choice is a single generation-time boolean, `rbac` (=
`Crypto.backend.transport_hardening_required(compliance)` -- the same predicate
that turns on mTLS), never a per-jurisdiction fan-out:

  rbac == False -> the flat generated credential, unchanged from tasks 2/3:
      REST  X-User/X-Pswd headers        SOAP  <credentials> in the Header
      gRPC  x-user/x-pswd call metadata   -- 401 / UNAUTHENTICATED on mismatch.
  rbac == True  -> a role check on top of the authenticated transport
      (`generated/cpp/{{http,grpc}}/harpia_rbac.h`): the verified client-cert
      subject CommonName -> a role via HARPIA_RBAC_MAP -> allow / 401&
      UNAUTHENTICATED (no identity) / 403 & PERMISSION_DENIED (wrong role),
      with exactly one AuditSink "rbac_denied" record per denial.

Each `*_auth_fills(name, hash, rbac)` returns a dict of already-rendered C++
text keyed by the template's placeholder names -- callers splice it straight
into `str.format(**fills, ...)`.
"""

# REST verb / gRPC RPC / SOAP operation -> ::harpia::rbac::Operation member.
# GET-list -> list, GET-item / pullByID -> read, POST / push -> create,
# PUT -> update, DELETE -> remove, streamSrc -> stream.  heartBeat is never
# gated (open liveness probe, both variants).

# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------

_REST_FLAT_HELPER = '''\
// True iff the request carries the correct credential for {name}. Exposed so it
// can be unit-tested directly.
inline bool authorized_{name}(const crow::request& req) {{
    return req.get_header_value("X-User") == "{name}" &&
           req.get_header_value("X-Pswd") == "{hash}";
}}
'''

_REST_RBAC_HELPER = '''\
// Role gate for {name} (transport-authn epic, task 4). Resolves the verified
// mTLS client-certificate CommonName (crow::request::client_cert_cn) to a role
// via the HARPIA_RBAC_MAP file and checks it against `op`. On deny it stamps
// the response -- 401 (no / unverifiable identity) or 403 (valid identity,
// wrong role) -- and returns false; ::harpia::rbac::decide has already emitted
// the single AuditSink "rbac_denied" record. Exposed for direct unit testing.
inline bool authz_{name}(const crow::request& req, crow::response& res,
                         ::harpia::rbac::Operation op) {{
    switch (::harpia::rbac::decide(req.client_cert_cn, op, "{name}")) {{
        case ::harpia::rbac::Decision::allow:
            return true;
        case ::harpia::rbac::Decision::unauthenticated:
            res.code = 401;
            return false;
        default:
            res.code = 403;
            return false;
    }}
}}
'''

_REST_FLAT_GUARD = (
    'if (!authorized_{name}(req)) {{ res.code = 401; res.end(); return; }}')
_REST_RBAC_GUARD = (
    'if (!authz_{name}(req, res, ::harpia::rbac::Operation::{op})) '
    '{{ res.end(); return; }}')

_REST_OPS = {
    "list": "list", "read": "read", "create": "create",
    "update": "update", "remove": "remove",
}


def rest_auth_fills(name, md5, rbac):
    if rbac:
        helper = _REST_RBAC_HELPER.format(name=name, hash=md5)
        guards = {
            "auth_guard_" + slot: _REST_RBAC_GUARD.format(name=name, op=op)
            for slot, op in _REST_OPS.items()
        }
        extra = '#include "http/harpia_rbac.h"'
    else:
        helper = _REST_FLAT_HELPER.format(name=name, hash=md5)
        flat = _REST_FLAT_GUARD.format(name=name)
        guards = {"auth_guard_" + slot: flat for slot in _REST_OPS}
        extra = ""
    return {"auth_extra_includes": extra, "auth_helper": helper, **guards}


# --------------------------------------------------------------------------
# SOAP  (one crow::SimpleApp route; the RBAC check needs the parsed operation
#        name, so for that variant it moves below the op-element parse)
# --------------------------------------------------------------------------

_SOAP_FLAT_HELPER = '''\
// True iff the envelope carries the correct credential for {name}. The handler
// gates every operation on this; exposed so it can be unit-tested directly.
inline bool authorized_{name}(const ::tinyxml2::XMLDocument& doc) {{
    const auto* env = doc.RootElement();                       // soap:Envelope
    const auto* header = ::harpia::soap::detail::find_child(env, "Header");
    const auto* cred = ::harpia::soap::detail::find_child(header, "credentials");
    if (!cred) return false;
    return ::harpia::soap::detail::child_text(cred, "user") == "{name}" &&
           ::harpia::soap::detail::child_text(cred, "pswd") == "{hash}";
}}

inline bool authorized_{name}(const std::string& soap_xml) {{
    ::tinyxml2::XMLDocument doc;
    if (doc.Parse(soap_xml.c_str()) != ::tinyxml2::XML_SUCCESS) return false;
    return authorized_{name}(doc);
}}
'''

_SOAP_FLAT_GUARD_EARLY = '''\
        if (!authorized_{name}(doc)) {{
            res.code = 401;
            reply(envelope_{name}(
                "<soap:Fault><faultcode>Client.Authentication</faultcode>"
                "<faultstring>unauthorized</faultstring></soap:Fault>"));
            res.end(); return;
        }}'''

_SOAP_RBAC_GUARD_OP = '''\
        ::harpia::rbac::Operation rbac_op = ::harpia::rbac::Operation::read;
        bool rbac_known = true;
        if (name == "get") rbac_op = ::harpia::rbac::Operation::read;
        else if (name == "set") rbac_op = ::harpia::rbac::Operation::create;
        else if (name == "update") rbac_op = ::harpia::rbac::Operation::update;
        else if (name == "delete") rbac_op = ::harpia::rbac::Operation::remove;
        else rbac_known = false;
        if (rbac_known) {{
            const auto rbac_d =
                ::harpia::rbac::decide(req.client_cert_cn, rbac_op, "{name}");
            if (rbac_d != ::harpia::rbac::Decision::allow) {{
                res.code = (rbac_d == ::harpia::rbac::Decision::unauthenticated)
                               ? 401 : 403;
                reply(envelope_{name}(
                    "<soap:Fault><faultcode>Client.Authentication</faultcode>"
                    "<faultstring>" +
                    std::string(
                        rbac_d == ::harpia::rbac::Decision::unauthenticated
                            ? "unauthenticated" : "forbidden") +
                    "</faultstring></soap:Fault>"));
                res.end(); return;
            }}
        }}'''


def soap_auth_fills(name, md5, rbac):
    if rbac:
        return {
            "auth_extra_includes": '#include "http/harpia_rbac.h"',
            "auth_helper": "",
            "auth_guard_early": "",
            "auth_guard_op": _SOAP_RBAC_GUARD_OP.format(name=name),
        }
    return {
        "auth_extra_includes": "",
        "auth_helper": "\n" + _SOAP_FLAT_HELPER.format(name=name, hash=md5),
        "auth_guard_early": _SOAP_FLAT_GUARD_EARLY.format(name=name),
        "auth_guard_op": "",
    }


# --------------------------------------------------------------------------
# gRPC  (static members on the <name>_service class; guards are if-init blocks)
# --------------------------------------------------------------------------

_GRPC_FLAT_HELPER = '''\
    // True iff the call carries the correct credential metadata for {name}. A
    // null context (direct in-process call, no wire) is allowed; the wire path
    // always supplies a context.
    static bool authorized(::grpc::ServerContext* ctx) {{
        if (!ctx) return true;
        const auto& md = ctx->client_metadata();
        auto u = md.find("x-user");
        auto p = md.find("x-pswd");
        return u != md.end() && p != md.end() &&
               ::std::string(u->second.data(), u->second.length()) == "{name}" &&
               ::std::string(p->second.data(), p->second.length()) == "{hash}";
    }}
'''

_GRPC_RBAC_HELPER = '''\
    // x509 subject CommonName of the verified mTLS client certificate, or "".
    static ::std::string peer_cn(::grpc::ServerContext* ctx) {{
        if (!ctx) return {{}};
        const auto ac = ctx->auth_context();
        if (!ac) return {{}};
        const auto vals = ac->FindPropertyValues(GRPC_X509_CN_PROPERTY_NAME);
        if (vals.empty()) return {{}};
        return ::std::string(vals[0].data(), vals[0].size());
    }}

    // Role gate for {name} (transport-authn epic, task 4): resolve peer_cn() to
    // a role via the HARPIA_RBAC_MAP file and check it against `op`. OK ->
    // proceed; UNAUTHENTICATED (no / unverifiable identity) or PERMISSION_DENIED
    // (valid identity, wrong role) otherwise. ::harpia::rbac::decide has already
    // emitted the single AuditSink "rbac_denied" record on a denial.
    static ::grpc::Status rbac_check(::grpc::ServerContext* ctx,
                                     ::harpia::rbac::Operation op) {{
        switch (::harpia::rbac::decide(peer_cn(ctx), op, "{name}")) {{
            case ::harpia::rbac::Decision::allow:
                return ::grpc::Status::OK;
            case ::harpia::rbac::Decision::unauthenticated:
                return ::grpc::Status(::grpc::StatusCode::UNAUTHENTICATED,
                                      "unauthenticated");
            default:
                return ::grpc::Status(::grpc::StatusCode::PERMISSION_DENIED,
                                      "forbidden");
        }}
    }}
'''

# no placeholders -> spliced verbatim (single braces, not str.format-doubled)
_GRPC_FLAT_GUARD = (
    'if (!authorized(context)) {\n'
    '            return ::grpc::Status(::grpc::StatusCode::UNAUTHENTICATED, "unauthorized");\n'
    '        }')

_GRPC_RBAC_GUARD = '''\
if (const auto rbac_s = rbac_check(context, ::harpia::rbac::Operation::{op});
            !rbac_s.ok()) {{
            return rbac_s;
        }}'''

_GRPC_OPS = {"create": "create", "read": "read", "stream": "stream"}


def grpc_auth_fills(name, md5, rbac):
    if rbac:
        helper = _GRPC_RBAC_HELPER.format(name=name)
        guards = {
            "auth_guard_" + slot: _GRPC_RBAC_GUARD.format(op=op)
            for slot, op in _GRPC_OPS.items()
        }
        extra = ('#include <grpcpp/security/auth_context.h>\n'
                 '#include "grpc/harpia_rbac.h"')
    else:
        helper = _GRPC_FLAT_HELPER.format(name=name, hash=md5)
        flat = _GRPC_FLAT_GUARD
        guards = {"auth_guard_" + slot: flat for slot in _GRPC_OPS}
        extra = ""
    return {"auth_extra_includes": extra, "auth_helper": helper, **guards}
