// harpia KeyProvider -- abstract interface for envelope encryption of `phi`
// data (Track O), hand-written, not generated. O.1 fixed the interface +
// envelope shape + an in-memory dummy; O.3 added shred_dek() (crypto-shred)
// to the interface and the dummy. The real backends -- a TPM/keystore-
// sealed local default, a KMS/HSM reference adapter -- are O.2
// (harpia_key_provider_local.h) and O.5; zeroization and AuditSink wiring
// on every key operation are O.4. See
// Initiatives/medical_devices/epics/thread-1-data-and-keys/histories/key-management/.
//
// Envelope encryption, baked in from the start (O.1's explicit ask, so O.2
// does not have to retrofit it):
//
//   * every `phi` value/record gets its OWN data-encryption key (DEK);
//   * the DEK -- and only the DEK -- ever touches the value (Dek::seal /
//     Dek::open);
//   * the key-encryption key (KEK) only ever WRAPS DEKs, never the value;
//   * a WrappedDek carries the KEK version that wrapped it, so key rotation
//     is O(number of keys) -- re-wrap the DEKs -- not O(data size). rotate()
//     mints a new KEK version and leaves every existing WrappedDek and every
//     ciphertext untouched.
//
// Injection point for generated code (Track A): a generated DAO that
// encrypts a `phi` column holds a `KeyProvider&`, generate_dek()s once per
// row, seal()s the value with that DEK, wrap_dek()s the DEK with the active
// KEK, and stores {ciphertext, WrappedDek} together.
//
// Rule 5 (harpia_sensitive_data_design_rules.md): a fallible operation
// returns a distinct, observable outcome -- unwrap_dek() returns an empty
// optional when the recorded KEK version is unknown (rotated away and
// dropped, or crypto-shredded in O.3), it does not throw or return a
// zeroed key.
#ifndef HARPIA_CRYPTO_KEY_PROVIDER_H
#define HARPIA_CRYPTO_KEY_PROVIDER_H

#include <cstdint>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <string>

namespace harpia {
namespace crypto {

// A data-encryption key: one per `phi` value/record. The transform here is
// a DUMMY reversible XOR -- NOT encryption. O.2 replaces InMemoryKeyProvider
// with a real backend (AES-GCM value sealing, AES-KW DEK wrapping) resolved
// through the Foundation F5 CryptoBackend seam; the INTERFACE shape below is
// what O.1 fixes in place.
struct Dek {
    std::string material;  // raw key bytes

    std::string seal(const std::string& plaintext) const {
        return xor_with(plaintext, material);
    }
    std::string open(const std::string& ciphertext) const {
        return xor_with(ciphertext, material);  // XOR is its own inverse
    }

    static std::string xor_with(const std::string& data, const std::string& key) {
        std::string out(data.size(), '\0');
        for (std::string::size_type i = 0; i < data.size(); ++i)
            out[i] = static_cast<char>(
                static_cast<unsigned char>(data[i]) ^
                static_cast<unsigned char>(key.empty() ? 0 : key[i % key.size()]));
        return out;
    }
};

// A DEK wrapped by a KEK, plus the KEK version needed to unwrap it. This is
// what gets stored next to the ciphertext. Rotation only ever rewrites
// these -- never the ciphertext.
struct WrappedDek {
    std::uint64_t kek_version = 0;
    std::string   bytes;
};

// Stable per-wrapped-DEK identity for the crypto-shred registry (O.3): the
// KEK version plus the wrapped bytes, exact, no hashing -- each DEK is 32
// random bytes so two distinct records never collide. Shared by every
// KeyProvider implementation.
inline std::string shred_key(const WrappedDek& w) {
    return std::to_string(w.kek_version) + ":" + w.bytes;
}

class KeyProvider {
public:
    virtual ~KeyProvider() = default;

    // The active KEK version -- monotonically increasing; rotate() bumps it.
    virtual std::uint64_t active_kek_version() const = 0;

    // Mint a fresh DEK for a new `phi` value.
    virtual Dek generate_dek() = 0;

    // Wrap a DEK with the ACTIVE KEK. The returned WrappedDek records that
    // version so a later unwrap still works after any number of rotations.
    virtual WrappedDek wrap_dek(const Dek& dek) = 0;

    // Unwrap using the KEK version recorded in `w`. Empty optional when that
    // version is unknown -- rotated past retention, or crypto-shredded
    // (O.3). Never throws, never returns a zeroed key (Rule 5).
    virtual std::optional<Dek> unwrap_dek(const WrappedDek& w) = 0;

    // Mint a NEW active KEK version and return it. Existing WrappedDeks stay
    // valid (they carry their own version; older KEKs are retained); no
    // ciphertext and no existing WrappedDek is touched here. Re-wrapping
    // live DEKs onto the new version is the caller's O(keys) pass, done
    // lazily or in a maintenance job -- not forced here.
    virtual std::uint64_t rotate() = 0;

    // Crypto-shred (O.3): permanently and irreversibly discard the DEK this
    // WrappedDek refers to. Afterwards unwrap_dek(w) returns nullopt even
    // though the KEK is intact -- exactly that record's ciphertext becomes
    // unrecoverable, with no need to locate or rewrite the ciphertext
    // itself (the right-to-erasure mechanism: destroy the key, not the
    // data). Per-DEK: shredding one record does not affect any other.
    // Idempotent. There is no un-shred.
    virtual void shred_dek(const WrappedDek& w) = 0;
};

// In-memory, non-persistent, DUMMY implementation -- for this session's
// tests and for downstream tracks' tests that need a working KeyProvider
// before O.2's real backend exists. NOT for production: keys live only in
// process memory and the wrap/seal transforms are XOR, not crypto.
class InMemoryKeyProvider : public KeyProvider {
public:
    InMemoryKeyProvider() {
        keks_[active_] = random_bytes(kKeyLen);
    }

    std::uint64_t active_kek_version() const override { return active_; }

    Dek generate_dek() override { return Dek{random_bytes(kKeyLen)}; }

    WrappedDek wrap_dek(const Dek& dek) override {
        return WrappedDek{active_, Dek::xor_with(dek.material, keks_.at(active_))};
    }

    std::optional<Dek> unwrap_dek(const WrappedDek& w) override {
        if (shredded_.count(shred_key(w))) return std::nullopt;  // O.3
        auto it = keks_.find(w.kek_version);
        if (it == keks_.end()) return std::nullopt;
        return Dek{Dek::xor_with(w.bytes, it->second)};
    }

    std::uint64_t rotate() override {
        ++active_;
        keks_[active_] = random_bytes(kKeyLen);
        return active_;
    }

    void shred_dek(const WrappedDek& w) override {
        shredded_.insert(shred_key(w));
    }

    // Drops a whole KEK version. Distinct from shred_dek() (which discards
    // one record's DEK): this is the coarse "retire an old KEK entirely"
    // case, exposed since O.1 for deterministic unknown-version tests.
    void forget_kek_version(std::uint64_t version) { keks_.erase(version); }

private:
    static constexpr std::string::size_type kKeyLen = 32;

    static std::string random_bytes(std::string::size_type n) {
        static std::random_device rd;
        std::uniform_int_distribution<int> byte(0, 255);
        std::string out(n, '\0');
        for (auto& c : out) c = static_cast<char>(byte(rd));
        return out;
    }

    std::map<std::uint64_t, std::string> keks_;
    std::uint64_t active_ = 1;
    std::set<std::string> shredded_;  // O.3: shred_key(w) of every shredded DEK
};

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_KEY_PROVIDER_H
