// harpia gRPC mTLS credentials -- hand-written, not generated. Copied verbatim
// into a generated project's generated/cpp/grpc/ next to the per-message
// *_grpc.h service impls and the generated grpc_server_bringup.h
// (transport-authn epic, task 2 -- mtls-grpc), the same pattern as
// harpia_dds_security.h for DDS-Security.
//
// Chooses gRPC transport credentials from one bool -- `hardening_required`,
// which grpc_server_bringup.h bakes in from
// Crypto.backend.transport_hardening_required(ComplianceContext) at generation
// time (`risk_class == class_c` or a cloud-connected `topology`; master plan
// §0a -- one project-wide floor, never per-jurisdiction):
//
//   hardening_required == true   mTLS. The server requires AND verifies a
//                                client certificate
//                                (GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY);
//                                the client presents its own cert. An
//                                incomplete MtlsFiles throws SecurityRefused --
//                                never a silent plaintext fallback
//                                (harpia_sensitive_data_design_rules.md).
//   hardening_required == false  grpc::InsecureServerCredentials() /
//                                grpc::InsecureChannelCredentials() -- the
//                                pre-mTLS behaviour, byte-for-byte.
//
// This is the mechanism, not the policy. The per-RPC x-user/x-pswd
// credential-metadata check in each <name>_grpc.h is unchanged and still runs
// on top of whatever transport this selects.
//
// Which crypto module OpenSSL uses (openssl / openssl_fips) is the F5
// CryptoBackend seam's job, recorded in grpc_server_selection.json. gRPC links
// OpenSSL (or BoringSSL) as built; like DDS-Security it has no per-call
// provider knob, so `openssl_provider` is threaded through only to be recorded.
#ifndef HARPIA_GRPC_MTLS_H
#define HARPIA_GRPC_MTLS_H

#include <fstream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

#include <grpcpp/grpcpp.h>
#include <grpcpp/security/credentials.h>
#include <grpcpp/security/server_credentials.h>

namespace harpia {
namespace grpc_transport {

// The three PEM artifacts an mTLS peer needs, as filesystem paths. A generated
// project ships NONE of these -- a deployment provisions identities from its own
// CA / HSM, or the demo's configure-time helper mints a local dev PKI
// (Assets/cmake/mtls_provision.sh, transport-authn task 1, behind -DUSE_MTLS;
// the paths land in a generated harpia_mtls_files.h).
struct MtlsFiles {
    std::string ca_certificate;   // trust anchor for verifying the peer
    std::string certificate;      // this side's identity cert chain (PEM)
    std::string private_key;      // its matching private key (PEM)

    bool complete() const {
        return !ca_certificate.empty() && !certificate.empty()
            && !private_key.empty();
    }
};

// Thrown instead of building an unauthenticated server/channel when the
// compliance profile mandates hardened transport but the PEM artifacts are not
// all present -- same fail-safe posture as DDS-Security's SecurityRefused.
class SecurityRefused : public std::runtime_error {
public:
    explicit SecurityRefused(const std::string& what)
        : std::runtime_error("gRPC mTLS refused: " + what) {}
};

namespace detail {

inline std::string read_pem(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw SecurityRefused("cannot read PEM file: " + path);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

}  // namespace detail

// Server-side transport credentials. `hardening_required` false -> the
// unchanged grpc::InsecureServerCredentials(). True -> mTLS with client-cert
// verification required; an incomplete `files` throws SecurityRefused.
inline std::shared_ptr<::grpc::ServerCredentials> server_credentials(
        bool hardening_required, const MtlsFiles& files) {
    if (!hardening_required) return ::grpc::InsecureServerCredentials();
    if (!files.complete()) {
        throw SecurityRefused(
            "incomplete MtlsFiles (need CA certificate + server certificate + "
            "private key)");
    }
    ::grpc::SslServerCredentialsOptions opts(
        GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY);
    opts.pem_root_certs = detail::read_pem(files.ca_certificate);
    opts.pem_key_cert_pairs.push_back(
        {detail::read_pem(files.private_key),
         detail::read_pem(files.certificate)});
    return ::grpc::SslServerCredentials(opts);
}

// Client-side channel credentials, symmetric with server_credentials():
// `hardening_required` false -> grpc::InsecureChannelCredentials(); true ->
// mTLS presenting this side's client cert, incomplete `files` throws.
inline std::shared_ptr<::grpc::ChannelCredentials> channel_credentials(
        bool hardening_required, const MtlsFiles& files) {
    if (!hardening_required) return ::grpc::InsecureChannelCredentials();
    if (!files.complete()) {
        throw SecurityRefused(
            "incomplete MtlsFiles (need CA certificate + client certificate + "
            "private key)");
    }
    ::grpc::SslCredentialsOptions opts;
    opts.pem_root_certs = detail::read_pem(files.ca_certificate);
    opts.pem_private_key = detail::read_pem(files.private_key);
    opts.pem_cert_chain = detail::read_pem(files.certificate);
    return ::grpc::SslCredentials(opts);
}

}  // namespace grpc_transport
}  // namespace harpia

#endif  // HARPIA_GRPC_MTLS_H
