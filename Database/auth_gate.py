"""Access-gate code fills for the generated REST / SOAP / gRPC transports
(transport-authn epic -- flat credential gate in tasks 2/3, three-role RBAC in
task 4, bearer sessions in task 5; message-level-hardening epic,
protected-open-modifiers task 3 -- the gate becomes per-message).

One place decides, per transport, what the `{{auth_*}}` placeholders in
`templates/{{rest,soap,grpc_service}}.h.tmpl` render to, so the three adapters
stay thin. The choice is a generation-time boolean, `rbac`, computed **per
message** by `effective_rbac()` below (was a single project-wide value before
protected-open-modifiers task 3 -- see that function for the current rule):

  rbac == False -> the flat generated credential, unchanged from tasks 2/3:
      REST  X-User/X-Pswd headers        SOAP  <credentials> in the Header
      gRPC  x-user/x-pswd call metadata   -- 401 / UNAUTHENTICATED on mismatch.
  rbac == True  -> a role check on top of the authenticated transport
      (`generated/cpp/{{http,grpc}}/harpia_rbac.h`): the verified client-cert
      subject CommonName -> a role via HARPIA_RBAC_MAP -> allow / 401&
      UNAUTHENTICATED (no identity) / 403 & PERMISSION_DENIED (wrong role),
      with exactly one AuditSink "rbac_denied" record per denial.

**Task 5 (token-sessions), rbac == True only.** Every RBAC gate first consults
an `Authorization: Bearer <token>` header (REST / SOAP) / `authorization` call
metadata (gRPC) via `harpia::session::from_authorization`
(`generated/cpp/{{http,grpc}}/harpia_session.h`): a token that verifies
(signature + expiry + revocation) supplies the CN the RBAC check runs on, in
place of re-reading the client certificate; a token that is presented but does
NOT verify is refused outright (401 / UNAUTHENTICATED), never a silent
fall-through to the cert. Issuance: REST/SOAP get a dedicated
`POST <base>/session` route in the HTTP bring-up (not here); gRPC's `heartBeat`
mints a token into `harpia-session-token` trailing metadata when the call
carries `harpia-issue-session` metadata -- the `{{hb_ctx}}` / `{{session_issue}}`
fills below (empty in the flat variant, so it stays byte-identical).

Each `*_auth_fills(name, hash, rbac)` returns a dict of already-rendered C++
text keyed by the template's placeholder names -- callers splice it straight
into `str.format(**fills, ...)`.

**protected-open-modifiers task 3: per-message override.** A message tagged
`protected` in the DSL (`Message.is_protected`) always gets the RBAC gate,
regardless of the project-wide default; one tagged `open`
(`Message.is_open`) always gets the flat/no-identity-required gate. Neither
tag on a message means it inherits the project-wide default unchanged --
this is what keeps a project using neither modifier byte-identical to before
this task. See `effective_rbac()`. This is a purely per-message decision:
composing an `open` message inside a `protected` one does NOT propagate
`protected` onto it (and cannot conflict the other way either) -- a
deliberate simplicity choice, not an oversight; a message's own declared
modifier is the only input to its own gate.

**Transport-level fallout.** The RBAC gate needs a client certificate's
CommonName to exist at all, and TLS is normally one project-wide on/off
switch -- so a `protected` message in an otherwise-unhardened (plaintext)
project, or an `open` message in an otherwise-hardened (mTLS-required)
project, needs the *transport itself* to change shape, not just that one
message's generated gate code. `transport_mode()` below computes the two
derived constants (`emit_tls` / `client_cert_required`) the adapters bake
into the generated bring-up for this -- see its docstring, and
`Initiatives/message-level-hardening/epics/protected-open-modifiers/tasks/2-mtls-optional-mode-spike-done.md`
for the confirmed feasibility this implements.
"""


def effective_rbac(msg, hardening_required):
    """The per-message gate boolean protected-open-modifiers task 3 feeds into
    `{{rest,soap,grpc}}_auth_fills()`, replacing the single project-wide value
    every caller used before this task.

    `msg.is_protected` always wins (RBAC gate, regardless of the project
    default); `msg.is_open` always wins the other way (flat gate) when
    `is_protected` isn't also set -- task 1 already makes both-set a hard
    generation error, so this function never sees that combination. Neither
    set -> the project-wide default, unchanged.
    """
    return bool(getattr(msg, "is_protected", False)) or (
        hardening_required and not getattr(msg, "is_open", False))


def transport_mode(messages, hardening_required):
    """Whole-project transport shape for protected-open-modifiers task 3,
    derived from every table-bearing message's `effective_rbac()` vs the
    project-wide `hardening_required` default. Returns `(emit_tls,
    client_cert_required)`:

      emit_tls            -- should the generated bring-up run a TLS-capable
                             server at all? True whenever the project is
                             already hardened, OR at least one message is
                             `protected` (it needs a client cert to check --
                             there is no such thing as an RBAC decision with
                             no transport to carry an identity on).
      client_cert_required -- should a connecting client be REQUIRED to
                             present a certificate (today's all-or-nothing
                             mTLS), or only asked for one (task 2's confirmed
                             "requested, not required" mode)? False whenever
                             at least one message is `open` in an otherwise
                             hardened project (an anonymous caller must be
                             able to complete the handshake to reach it) --
                             or whenever `emit_tls` is true only because of a
                             `protected` message in an otherwise-unhardened
                             project (nothing there expects to own a cert).

    Both are exactly `hardening_required` (today's binary behaviour,
    unchanged) whenever no message's `effective_rbac()` diverges from the
    project default -- the byte-identical-output guarantee for a project
    using neither modifier anywhere.

    A message that needs the RBAC gate but whose project doesn't actually
    supply real certificate files (`MtlsFiles.complete()`) is refused at run
    time by `make_server_context()`/`server_credentials()`
    (`SecurityRefused`) exactly as an incomplete hardened project is refused
    today -- never a silent plaintext fallback for a message the schema says
    must be gated.
    """
    any_open_under_hardening = hardening_required and any(
        getattr(m, "is_open", False) for m in messages)
    any_protected_under_open = (not hardening_required) and any(
        getattr(m, "is_protected", False) for m in messages)
    emit_tls = hardening_required or any_protected_under_open
    client_cert_required = hardening_required and not any_open_under_hardening
    return emit_tls, client_cert_required

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
// Role gate for {name} (transport-authn epic, tasks 4 + 5). Identity is either
// a valid `Authorization: Bearer` session token (task 5) or, absent one, the
// verified mTLS client-certificate CommonName (crow::request::client_cert_cn);
// a token that is presented but does not verify is refused (401) with no
// fall-through to the cert. The resolved CN is mapped to a role via the
// HARPIA_RBAC_MAP file and checked against `op`. On deny it stamps the
// response -- 401 (no / unverifiable identity) or 403 (valid identity, wrong
// role) -- and returns false; ::harpia::rbac::decide has already emitted the
// single AuditSink "rbac_denied" record (a bad token emits one
// "session_denied" record instead). Exposed for direct unit testing.
inline bool authz_{name}(const crow::request& req, crow::response& res,
                         ::harpia::rbac::Operation op) {{
    std::string cn = req.client_cert_cn;
    const auto bearer = ::harpia::session::from_authorization(
        req.get_header_value("Authorization"));
    if (bearer.present) {{
        if (bearer.verdict != ::harpia::session::Verdict::ok) {{
            res.code = 401;
            return false;
        }}
        cn = bearer.cn;
    }}
    switch (::harpia::rbac::decide(cn, op, "{name}")) {{
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
        extra = ('#include "http/harpia_rbac.h"\n'
                 '#include "http/harpia_session.h"')
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
        // task 5: a valid Authorization: Bearer session token supplies the
        // identity; a presented-but-invalid token is a 401 Fault (no
        // fall-through to the client certificate).
        std::string rbac_cn = req.client_cert_cn;
        {{
            const auto rbac_bearer = ::harpia::session::from_authorization(
                req.get_header_value("Authorization"));
            if (rbac_bearer.present) {{
                if (rbac_bearer.verdict != ::harpia::session::Verdict::ok) {{
                    res.code = 401;
                    reply(envelope_{name}(
                        "<soap:Fault><faultcode>Client.Authentication</faultcode>"
                        "<faultstring>invalid session token</faultstring>"
                        "</soap:Fault>"));
                    res.end(); return;
                }}
                rbac_cn = rbac_bearer.cn;
            }}
        }}
        ::harpia::rbac::Operation rbac_op = ::harpia::rbac::Operation::read;
        bool rbac_known = true;
        if (name == "get") rbac_op = ::harpia::rbac::Operation::read;
        else if (name == "set") rbac_op = ::harpia::rbac::Operation::create;
        else if (name == "update") rbac_op = ::harpia::rbac::Operation::update;
        else if (name == "delete") rbac_op = ::harpia::rbac::Operation::remove;
        else rbac_known = false;
        if (rbac_known) {{
            const auto rbac_d =
                ::harpia::rbac::decide(rbac_cn, rbac_op, "{name}");
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
            "auth_extra_includes": ('#include "http/harpia_rbac.h"\n'
                                    '#include "http/harpia_session.h"'),
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

    // Raw `authorization` call-metadata value ("Bearer <token>"), or "".
    static ::std::string bearer_metadata(::grpc::ServerContext* ctx) {{
        if (!ctx) return {{}};
        const auto& md = ctx->client_metadata();
        const auto it = md.find("authorization");
        if (it == md.end()) return {{}};
        return ::std::string(it->second.data(), it->second.length());
    }}

    // Role gate for {name} (transport-authn epic, tasks 4 + 5): identity is a
    // valid `authorization: Bearer` session token (task 5) or, absent one,
    // peer_cn() (the verified mTLS client cert); a presented-but-invalid token
    // is UNAUTHENTICATED with no fall-through to the cert. The resolved CN is
    // mapped to a role via the HARPIA_RBAC_MAP file and checked against `op`.
    // OK -> proceed; UNAUTHENTICATED (no / unverifiable identity) or
    // PERMISSION_DENIED (valid identity, wrong role) otherwise.
    // ::harpia::rbac::decide has already emitted the single AuditSink
    // "rbac_denied" record on a denial (a bad token emits one "session_denied"
    // record instead).
    static ::grpc::Status rbac_check(::grpc::ServerContext* ctx,
                                     ::harpia::rbac::Operation op) {{
        ::std::string cn = peer_cn(ctx);
        const auto bearer =
            ::harpia::session::from_authorization(bearer_metadata(ctx));
        if (bearer.present) {{
            if (bearer.verdict != ::harpia::session::Verdict::ok) {{
                return ::grpc::Status(::grpc::StatusCode::UNAUTHENTICATED,
                                      "invalid session token");
            }}
            cn = bearer.cn;
        }}
        switch (::harpia::rbac::decide(cn, op, "{name}")) {{
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

# heartBeat doubles as the session-token issuance point (task 5). Spliced as the
# first line of the heartBeat body; empty in the flat variant so that header
# stays byte-identical. This is a str.format() *value*, not template source, so
# its braces are single (never re-scanned by the templating pass).
_GRPC_SESSION_ISSUE = '''\
        // transport-authn task 5: heartBeat also issues session tokens. A
        // caller that has authenticated the mTLS transport sends
        // `harpia-issue-session` metadata and gets a signed bearer token
        // carrying its RBAC CN + role back as `harpia-session-token` trailing
        // metadata. Never gated -- heartBeat is the open liveness probe.
        if (context) {
            const auto& md = context->client_metadata();
            if (md.find("harpia-issue-session") != md.end()) {
                const ::std::string cn = peer_cn(context);
                if (!cn.empty()) {
                    const auto issue_role =
                        ::harpia::rbac::role_map().role_for(cn);
                    const ::std::string tok = ::harpia::session::issue(
                        cn, ::harpia::rbac::role_name(issue_role));
                    if (!tok.empty()) {
                        context->AddTrailingMetadata("harpia-session-token", tok);
                    }
                }
            }
        }
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
                 '#include "grpc/harpia_rbac.h"\n'
                 '#include "grpc/harpia_session.h"')
        # heartBeat needs a named ServerContext* to read the issue-session
        # metadata off / attach the token to.
        hb_ctx = " context"
        session_issue = _GRPC_SESSION_ISSUE
    else:
        helper = _GRPC_FLAT_HELPER.format(name=name, hash=md5)
        flat = _GRPC_FLAT_GUARD
        guards = {"auth_guard_" + slot: flat for slot in _GRPC_OPS}
        extra = ""
        hb_ctx = ""
        session_issue = ""
    return {"auth_extra_includes": extra, "auth_helper": helper,
            "hb_ctx": hb_ctx, "session_issue": session_issue, **guards}
