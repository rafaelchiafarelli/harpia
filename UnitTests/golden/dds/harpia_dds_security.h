// harpia DDS-Security wiring -- hand-written, not generated. Copied verbatim
// into a generated project's generated/cpp/dds/ next to the per-message
// *_dds.h headers (dds-transport epic, task 3), the same pattern as
// harpia_audit_sink.h / harpia_dds_frame.hpp.
//
// OMG DDS-Security (authentication + access-control + cryptographic builtin
// plugins) for the Eclipse Cyclone DDS stack task 2a vendored. ddscxx
// 0.10.5 has no C++ `Property` QoS policy, so security is configured the
// Cyclone-native way: a `<CycloneDDS><Domain><Security>` config block fed
// through the `CYCLONEDDS_URI` environment variable (Cyclone treats a value
// starting with `<` as the literal configuration). `scoped_security_config`
// installs that block for the duration of participant construction and
// restores the previous value afterwards; Cyclone captures the security
// configuration into the domain at creation time.
//
// Fail-safe (harpia_sensitive_data_design_rules.md; master plan §0a): if a
// caller asks for security but has not supplied every PKI artifact, this
// throws `SecurityRefused` -- it never quietly falls back to a plaintext
// participant. Whether a project *must* use this is a compliance-profile
// decision recorded at generation time in
// generated/cpp/dds/security/dds_security_selection.json (from the F5
// CryptoBackend seam + risk_class/topology); this header is the mechanism,
// not the policy.
//
// Which crypto module the builtin plugins link is the F5 CryptoBackend
// seam's job (openssl / openssl_fips). Cyclone's builtin auth/crypto
// plugins use OpenSSL directly and pick their provider from the process
// OpenSSL configuration (OPENSSL_CONF / OPENSSL_MODULES), which the build
// or deployment sets; there is no per-plugin provider knob in ddscxx
// 0.10.5, so `openssl_provider` is threaded through only to be recorded in
// the emitted config as a comment.
#ifndef HARPIA_DDS_SECURITY_H
#define HARPIA_DDS_SECURITY_H

#include <cstdlib>
#include <stdexcept>
#include <string>

#include "dds/dds.hpp"

namespace harpia {
namespace dds_security {

// The six PKI artifacts an OMG DDS-Security participant needs. A generated
// project ships NONE of these -- a deployment provisions identities from its
// own CA / HSM, or the demo's configure-time probe
// (Assets/cmake/dds_security_provision.sh) mints throwaway ones. These are
// filesystem paths, not blobs: Cyclone reads them itself via `file:` URIs.
struct SecurityFiles {
    std::string identity_ca;           // trust anchor for peer identities
    std::string identity_certificate;  // this participant's identity cert
    std::string private_key;           // its matching private key
    std::string permissions_ca;        // trust anchor for governance/permissions
    std::string governance;            // S/MIME-signed governance document
    std::string permissions;           // S/MIME-signed permissions document

    bool complete() const {
        return !identity_ca.empty() && !identity_certificate.empty() &&
               !private_key.empty() && !permissions_ca.empty() &&
               !governance.empty() && !permissions.empty();
    }
};

// Thrown instead of silently constructing a plaintext participant when the
// caller asked for security but did not supply every artifact.
class SecurityRefused : public std::runtime_error {
public:
    explicit SecurityRefused(const std::string& what)
        : std::runtime_error("DDS-Security refused: " + what) {}
};

namespace detail {

inline std::string xml_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        switch (c) {
            case '&':  out += "&amp;";  break;
            case '<':  out += "&lt;";   break;
            case '>':  out += "&gt;";   break;
            case '"':  out += "&quot;"; break;
            default:   out += c;        break;
        }
    }
    return out;
}

// A full CycloneDDS configuration document carrying only the <Security>
// block, applied to every domain ("any"). Plugin `path` values are the
// bare builtin sonames Cyclone resolves from its own install
// (libdds_security_auth / _ac / _crypto .so) -- task 2a built Cyclone with
// -DENABLE_SECURITY=ON -DENABLE_SSL=ON, so they are present.
inline std::string security_config_xml(const SecurityFiles& f,
                                       const std::string& openssl_provider) {
    return
        "<CycloneDDS><Domain id=\"any\">"
        "<!-- harpia DDS-Security; crypto module via F5 CryptoBackend, "
        "openssl_provider=" + xml_escape(openssl_provider) + " -->"
        "<Security>"
          "<Authentication>"
            "<Library path=\"dds_security_auth\" "
              "initFunction=\"init_authentication\" "
              "finalizeFunction=\"finalize_authentication\"/>"
            "<IdentityCA>file:" + xml_escape(f.identity_ca) + "</IdentityCA>"
            "<IdentityCertificate>file:" + xml_escape(f.identity_certificate) +
              "</IdentityCertificate>"
            "<PrivateKey>file:" + xml_escape(f.private_key) + "</PrivateKey>"
          "</Authentication>"
          "<AccessControl>"
            // Cyclone builtin access-control plugin soname is
            // libdds_security_ac.so (task 2a's -DENABLE_SECURITY=ON build).
            "<Library path=\"dds_security_ac\" "
              "initFunction=\"init_access_control\" "
              "finalizeFunction=\"finalize_access_control\"/>"
            "<PermissionsCA>file:" + xml_escape(f.permissions_ca) +
              "</PermissionsCA>"
            "<Governance>file:" + xml_escape(f.governance) + "</Governance>"
            "<Permissions>file:" + xml_escape(f.permissions) + "</Permissions>"
          "</AccessControl>"
          "<Cryptographic>"
            "<Library path=\"dds_security_crypto\" "
              "initFunction=\"init_crypto\" "
              "finalizeFunction=\"finalize_crypto\"/>"
          "</Cryptographic>"
        "</Security>"
        "</Domain></CycloneDDS>";
}

}  // namespace detail

// RAII: point CYCLONEDDS_URI at the inline secured config for this object's
// lifetime, restoring whatever was there before on destruction. Any
// DomainParticipant constructed on a not-yet-created domain while an
// instance is in scope comes up secured. Not thread-safe (it mutates a
// process environment variable) -- construct participants on one thread,
// the same discipline the rest of the DDS runtime already assumes.
class scoped_security_config {
public:
    explicit scoped_security_config(const SecurityFiles& files,
                                    const std::string& openssl_provider =
                                        "default") {
        if (!files.complete()) {
            throw SecurityRefused(
                "incomplete SecurityFiles (need identity CA + certificate + "
                "private key, and permissions CA + governance + permissions)");
        }
        xml_ = detail::security_config_xml(files, openssl_provider);
        const char* prev = std::getenv(kEnv);
        had_prev_ = prev != nullptr;
        if (had_prev_) prev_ = prev;
#ifdef _WIN32
        _putenv_s(kEnv, xml_.c_str());
#else
        ::setenv(kEnv, xml_.c_str(), /*overwrite=*/1);
#endif
    }

    ~scoped_security_config() {
#ifdef _WIN32
        _putenv_s(kEnv, had_prev_ ? prev_.c_str() : "");
#else
        if (had_prev_) ::setenv(kEnv, prev_.c_str(), 1);
        else ::unsetenv(kEnv);
#endif
    }

    scoped_security_config(const scoped_security_config&) = delete;
    scoped_security_config& operator=(const scoped_security_config&) = delete;

    const std::string& xml() const { return xml_; }

private:
    static constexpr const char* kEnv = "CYCLONEDDS_URI";
    bool had_prev_ = false;
    std::string prev_;
    std::string xml_;
};

// Convenience: a secured DomainParticipant on `domain_id`. Throws
// `SecurityRefused` when `files` is incomplete -- never a silent plaintext
// fallback. The scoped config is applied only across participant
// construction; Cyclone binds the security configuration into the domain at
// creation, so the participant stays secured after the env var is restored.
inline ::dds::domain::DomainParticipant secured_participant(
        uint32_t domain_id, const SecurityFiles& files,
        const std::string& openssl_provider = "default") {
    scoped_security_config guard(files, openssl_provider);
    return ::dds::domain::DomainParticipant(domain_id);
}

}  // namespace dds_security
}  // namespace harpia

#endif  // HARPIA_DDS_SECURITY_H
