// harpia KMS/HSM KeyProvider reference adapter (Track O, Session O.5),
// hand-written, not generated.
//
// EXTENSION POINT. To target a real external key-management service -- AWS
// KMS, GCP KMS, Azure Key Vault, HashiCorp Vault, a PKCS#11 HSM -- an
// integrator implements the small `KmsClient` seam below and hands it to a
// `KmsKeyProvider`. `KmsKeyProvider` routes every Session O.1
// harpia::crypto::KeyProvider operation to those calls and adds nothing
// else: swapping backends never changes the KeyProvider interface. That is
// O.5's whole point -- proving the interface is real, not picking a vendor.
//
// Envelope encryption maps onto a KMS the AWS-`GenerateDataKey` way: the
// KEK (a "customer master key") never leaves the service; wrap() asks the
// KMS to encrypt a DEK under the active KEK version, unwrap() asks it to
// decrypt. Rotation is a KMS-side operation; older KEK versions stay usable
// for unwrap. Per-DEK crypto-shred (O.3) is kept as a local revocation set
// here, since most KMS products only delete whole key versions -- a real
// adapter may additionally schedule KMS key-version deletion.
//
// `MockKms` is a reference `KmsClient` for tests and local development: an
// in-process stand-in with in-memory key versions and the same placeholder
// XOR transform as the other backends. It ships in this header the way
// NoOpAuditSink ships in harpia_audit_sink.h.
//
// O.4 carried through: `KmsKeyProvider` takes an AuditSink& and records
// every key op; DEK material is zeroized by the Dek destructor.
//
// Two of Track O's integration tests need a real generated DAO to be
// meaningful (write -> persist -> rotate KEK -> read with no full
// re-encryption; swap default -> this adapter with zero DAO changes) --
// deferred to Track A's A.4, not faked here.
#ifndef HARPIA_CRYPTO_KEY_PROVIDER_KMS_H
#define HARPIA_CRYPTO_KEY_PROVIDER_KMS_H

#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>

#include "harpia_key_provider.h"

namespace harpia {
namespace crypto {

// The seam an integrator implements for their KMS/HSM. Deliberately tiny:
// four operations, all in terms of opaque byte strings and an integer key
// version -- no harpia types leak in, no KMS types leak out.
class KmsClient {
public:
    virtual ~KmsClient() = default;

    // The KMS's current key version. rotate() advances it.
    virtual std::uint64_t active_version() const = 0;

    // Encrypt (wrap) DEK material under key `version`. Returns the opaque
    // blob the caller stores next to the record.
    virtual std::string wrap(std::uint64_t version,
                             const std::string& dek_material) = 0;

    // Decrypt (unwrap) a blob produced by wrap() at `version`. Empty
    // optional when that version is gone at the KMS (retired / deleted).
    virtual std::optional<std::string> unwrap(std::uint64_t version,
                                              const std::string& wrapped) = 0;

    // Ask the KMS to create a new key version and return it. Older versions
    // stay usable for unwrap.
    virtual std::uint64_t rotate() = 0;
};

// A KeyProvider backed by an external KMS/HSM (via the KmsClient seam).
class KmsKeyProvider : public KeyProvider {
public:
    explicit KmsKeyProvider(
        KmsClient& kms,
        compliance::AuditSink& audit = compliance::default_audit_sink())
        : kms_(kms), audit_(audit) {}

    std::uint64_t active_kek_version() const override {
        return kms_.active_version();
    }

    Dek generate_dek() override {
        audit_.record(kOpGenerate, "dek");
        return Dek(detail::random_bytes(kKeyLen));  // DEK minted locally, KMS wraps it
    }

    WrappedDek wrap_dek(const Dek& dek) override {
        const std::uint64_t v = kms_.active_version();
        audit_.record(kOpWrap, "kek:" + std::to_string(v));
        return WrappedDek{v, kms_.wrap(v, dek.material)};
    }

    std::optional<Dek> unwrap_dek(const WrappedDek& w) override {
        const std::string subject = "kek:" + std::to_string(w.kek_version);
        if (shredded_.count(shred_key(w))) {                     // O.3
            audit_.record(kOpUnwrap, subject, "shredded");
            return std::nullopt;
        }
        std::optional<std::string> raw = kms_.unwrap(w.kek_version, w.bytes);
        if (!raw.has_value()) {
            audit_.record(kOpUnwrap, subject, "unknown_version");
            return std::nullopt;
        }
        audit_.record(kOpUnwrap, subject, "ok");
        return Dek(std::move(*raw));
    }

    std::uint64_t rotate() override {
        const std::uint64_t v = kms_.rotate();
        audit_.record(kOpRotate, "kek:" + std::to_string(v));
        return v;
    }

    void shred_dek(const WrappedDek& w) override {
        shredded_.insert(shred_key(w));
        audit_.record(kOpShred, "kek:" + std::to_string(w.kek_version));
    }

private:
    static constexpr std::string::size_type kKeyLen = 32;

    KmsClient&             kms_;
    compliance::AuditSink& audit_;
    std::set<std::string>  shredded_;
};

// Reference KmsClient for tests / local development -- an in-process
// stand-in for a real KMS. In-memory key versions, placeholder XOR wrap
// (NOT crypto). NOT for production.
class MockKms : public KmsClient {
public:
    MockKms() { keys_[active_] = detail::random_bytes(kKeyLen); }

    ~MockKms() override {
        for (auto& kv : keys_) detail::secure_zero(kv.second);
    }

    std::uint64_t active_version() const override { return active_; }

    std::string wrap(std::uint64_t version,
                     const std::string& dek_material) override {
        return Dek::xor_with(dek_material, keys_.at(version));
    }

    std::optional<std::string> unwrap(std::uint64_t version,
                                      const std::string& wrapped) override {
        auto it = keys_.find(version);
        if (it == keys_.end()) return std::nullopt;
        return Dek::xor_with(wrapped, it->second);
    }

    std::uint64_t rotate() override {
        ++active_;
        keys_[active_] = detail::random_bytes(kKeyLen);
        return active_;
    }

    // Stand-in for "the KMS deleted this key version".
    void forget_version(std::uint64_t version) {
        auto it = keys_.find(version);
        if (it == keys_.end()) return;
        detail::secure_zero(it->second);
        keys_.erase(it);
    }

private:
    static constexpr std::string::size_type kKeyLen = 32;

    std::map<std::uint64_t, std::string> keys_;
    std::uint64_t active_ = 1;
};

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_KEY_PROVIDER_KMS_H
