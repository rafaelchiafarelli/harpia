// harpia REST/SOAP mTLS context -- hand-written, not generated. Copied verbatim
// into a generated project's generated/cpp/http/ next to the rendered
// http_server_bringup.h (transport-authn epic, task 3 -- mtls-rest-soap), the
// same pattern as harpia_grpc_mtls.h for gRPC and harpia_dds_security.h for DDS.
//
// REST and SOAP share one crow::SimpleApp. Crow's built-in .ssl_file() does
// server-side TLS only (it sets verify_peer + verify_client_once -- a client
// with NO certificate still connects). True mTLS -- require AND verify a client
// certificate -- needs verify_fail_if_no_peer_cert, which crow exposes only via
// its `app.ssl(asio::ssl::context&&)` overload that takes a fully-configured
// context. This header builds that context.
//
//   hardening_required == true  -> the bring-up calls make_server_context() and
//                                  hands the result to app.ssl(); an incomplete
//                                  MtlsFiles throws SecurityRefused -- never a
//                                  silent plaintext server.
//   hardening_required == false -> the bring-up never touches this header; the
//                                  app serves plain HTTP exactly as before.
//
// `client_cert_required` (message-level-hardening epic, protected-open-
// modifiers task 3; default true, so every existing call site is unaffected):
// when hardening is on but the project mixes a project-wide default with a
// per-message override (an `open` message under a hardened default, or a
// `protected` message forcing hardening on in an otherwise-open project --
// see Database/auth_gate.py's `transport_mode()`), pass false to get task 2's
// confirmed "requested, not required" mode instead of full mTLS: a client
// with no certificate still completes the handshake (`crow::request::
// client_cert_cn` comes back "" for that connection, the input
// Compliance/runtime/harpia_rbac.h's `decide()` already treats as
// unauthenticated), while a certificate that IS presented is still fully
// verified against the CA -- this never means "unverified when presented",
// only "not mandatory at the TLS layer". The per-message RBAC/flat choice
// (unchanged, computed by auth_gate.py) is what actually enforces each
// message's own requirement on top of this.
//
// The per-route X-User/X-Pswd (REST) and <credentials> (SOAP) checks are
// unchanged and still run on top of whatever transport this selects.
//
// Needs standalone asio + OpenSSL (the same stack crow.h already pulls in when
// built with CROW_ENABLE_SSL). Which OpenSSL provider is used (openssl /
// openssl_fips) is the F5 CryptoBackend seam's job, recorded in
// http_server_selection.json.
#ifndef HARPIA_HTTP_MTLS_H
#define HARPIA_HTTP_MTLS_H

#include <stdexcept>
#include <string>

#ifndef ASIO_STANDALONE
#define ASIO_STANDALONE
#endif
#include <asio/ssl.hpp>

namespace harpia {
namespace http_transport {

// The three PEM artifacts an mTLS peer needs, as filesystem paths. A generated
// project ships NONE of these -- a deployment provisions identities from its own
// CA / HSM, or the demo's configure-time helper mints a local dev PKI
// (Assets/cmake/mtls_provision.sh, transport-authn task 1, behind -DUSE_MTLS).
struct MtlsFiles {
    std::string ca_certificate;   // trust anchor for verifying the client
    std::string certificate;      // this server's identity cert chain (PEM)
    std::string private_key;      // its matching private key (PEM)

    bool complete() const {
        return !ca_certificate.empty() && !certificate.empty()
            && !private_key.empty();
    }
};

// Thrown instead of building a plaintext / no-verify server when the compliance
// profile mandates hardened transport but the PEM artifacts are not all present
// -- same fail-safe posture as harpia_grpc_mtls.h / harpia_dds_security.h.
class SecurityRefused : public std::runtime_error {
public:
    explicit SecurityRefused(const std::string& what)
        : std::runtime_error("REST/SOAP mTLS refused: " + what) {}
};

// A server-side asio::ssl::context configured for mTLS: this server's cert/key,
// and -- the point -- verify_peer (optionally | verify_fail_if_no_peer_cert)
// against files.ca_certificate. Hand the result to crow: `app.ssl(std::move(ctx))`.
//
// `hardening_required` false is a programming error here (the bring-up only
// calls this when true) -- it throws, symmetric with harpia_grpc_mtls.h.
// `client_cert_required` true (default): a client presenting no certificate
// is refused at the handshake -- today's full-mTLS behaviour, unchanged.
// false: a client with no certificate still completes the handshake (task
// 2's "requested, not required" mode); one that DOES present a certificate
// is still fully verified against files.ca_certificate.
inline asio::ssl::context make_server_context(
        bool hardening_required, const MtlsFiles& files,
        bool client_cert_required = true) {
    if (!hardening_required) {
        throw SecurityRefused(
            "make_server_context() called without hardening required");
    }
    if (!files.complete()) {
        throw SecurityRefused(
            "incomplete MtlsFiles (need CA certificate + server certificate + "
            "private key)");
    }
    asio::ssl::context ctx(asio::ssl::context::tls_server);
    ctx.set_options(asio::ssl::context::default_workarounds
                    | asio::ssl::context::no_sslv2
                    | asio::ssl::context::no_sslv3
                    | asio::ssl::context::single_dh_use);
    ctx.use_certificate_chain_file(files.certificate);
    ctx.use_private_key_file(files.private_key, asio::ssl::context::pem);
    ctx.load_verify_file(files.ca_certificate);
    ctx.set_verify_mode(client_cert_required
                        ? (asio::ssl::verify_peer
                           | asio::ssl::verify_fail_if_no_peer_cert)
                        : asio::ssl::verify_peer);
    return ctx;
}

}  // namespace http_transport
}  // namespace harpia

#endif  // HARPIA_HTTP_MTLS_H
