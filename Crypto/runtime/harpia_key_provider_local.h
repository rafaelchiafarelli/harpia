// harpia LocalKeyProvider -- the default KeyProvider for integrators with no
// external KMS/HSM (Track O, Session O.2), hand-written, not generated.
// Implements the Session O.1 harpia::crypto::KeyProvider interface with
// KEK material persisted to a local file, so keys survive a process
// restart (unlike O.1's purely in-process InMemoryKeyProvider).
//
// FAIL-SAFE DEFAULT (harpia_medical_master_plan.md's fail-safe rule, and
// the F1 "strictest when ambiguous" posture): when the active compliance
// profile implies PHI AT SCALE, constructing this provider WITHOUT an
// explicit acknowledgment is refused -- it throws LocalKeyProviderRefused.
// The integrator must consciously choose the local fallback over a real KMS
// integration (set LocalKeyProviderConfig::acknowledged, e.g. from
// local_key_provider_acknowledged() reading HARPIA_ACK_LOCAL_KEY_PROVIDER),
// rather than silently shipping it into production.
//
// Still a PLACEHOLDER cipher: wrap/seal are the same dummy XOR transforms as
// O.1 (inherited via Dek / the base contract). The real AES-KW / AES-GCM
// operations land when this provider is bound to the Foundation F5
// CryptoBackend seam. O.2's contribution is the persistence + the
// acknowledgment gate, not the crypto primitive.
//
// Crypto-shred (O.3): shred_dek() appends to a `<storage_path>.shred`
// append-only sidecar so a discard survives a restart; the KEK store is
// never touched. O.4: the ctor takes an AuditSink& (every key op is
// recorded); KEKs are zeroized on eviction and in the destructor. Out of
// scope here: the KMS/HSM reference adapter (O.5, harpia_key_provider_kms.h).
#ifndef HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H
#define HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H

#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <ios>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "harpia_key_provider.h"

namespace harpia {
namespace crypto {

// Thrown by LocalKeyProvider's constructor when a PHI-at-scale profile is
// active and the local fallback has not been explicitly acknowledged.
class LocalKeyProviderRefused : public std::runtime_error {
public:
    LocalKeyProviderRefused()
        : std::runtime_error(
              "LocalKeyProvider refused: the compliance profile implies PHI "
              "at scale and the local key backend was not explicitly "
              "acknowledged (set LocalKeyProviderConfig::acknowledged / "
              "HARPIA_ACK_LOCAL_KEY_PROVIDER after making a KMS-vs-local "
              "decision)") {}
};

struct LocalKeyProviderConfig {
    // File the KEK material is read from / written to. Created (with KEK v1)
    // if it does not exist.
    std::string storage_path;
    // Does the active compliance profile put PHI at scale? (Track A wires
    // this from ComplianceContext at generation time; supplied directly
    // here.)
    bool phi_at_scale = false;
    // Has the integrator explicitly opted into the local fallback despite
    // phi_at_scale? Ignored when phi_at_scale is false.
    bool acknowledged = false;
};

// Truthy value in HARPIA_ACK_LOCAL_KEY_PROVIDER ("1" / "true", any case) ->
// the integrator has acknowledged the local fallback. A convenience source
// for LocalKeyProviderConfig::acknowledged; callers may set that field by
// any means.
inline bool local_key_provider_acknowledged() {
    const char* v = std::getenv("HARPIA_ACK_LOCAL_KEY_PROVIDER");
    if (v == nullptr) return false;
    std::string s(v);
    for (auto& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s == "1" || s == "true" || s == "yes";
}

class LocalKeyProvider : public KeyProvider {
public:
    explicit LocalKeyProvider(
        const LocalKeyProviderConfig& cfg,
        compliance::AuditSink& audit = compliance::default_audit_sink())
        : audit_(audit), path_(cfg.storage_path) {
        if (cfg.phi_at_scale && !cfg.acknowledged)
            throw LocalKeyProviderRefused();
        if (!load()) {
            persist();  // fresh store: KEK v1 was minted in the ctor init
            audit_.record(kOpGenerate, "kek:" + std::to_string(active_));
        }
        load_shreds();
    }

    ~LocalKeyProvider() override {
        for (auto& kv : keks_) detail::secure_zero(kv.second);  // O.4
    }

    std::uint64_t active_kek_version() const override { return active_; }

    Dek generate_dek() override {
        audit_.record(kOpGenerate, "dek");
        return Dek(detail::random_bytes(kKeyLen));
    }

    WrappedDek wrap_dek(const Dek& dek) override {
        audit_.record(kOpWrap, "kek:" + std::to_string(active_));
        return WrappedDek{active_, Dek::xor_with(dek.material, keks_.at(active_))};
    }

    std::optional<Dek> unwrap_dek(const WrappedDek& w) override {
        const std::string subject = "kek:" + std::to_string(w.kek_version);
        if (shredded_.count(shred_key(w))) {                     // O.3
            audit_.record(kOpUnwrap, subject, "shredded");
            return std::nullopt;
        }
        auto it = keks_.find(w.kek_version);
        if (it == keks_.end()) {
            audit_.record(kOpUnwrap, subject, "unknown_version");
            return std::nullopt;
        }
        audit_.record(kOpUnwrap, subject, "ok");
        return Dek(Dek::xor_with(w.bytes, it->second));
    }

    std::uint64_t rotate() override {
        ++active_;
        keks_[active_] = detail::random_bytes(kKeyLen);
        persist();
        audit_.record(kOpRotate, "kek:" + std::to_string(active_));
        return active_;
    }

    // Crypto-shred (O.3). Appends to a `<storage_path>.shred` sidecar (an
    // append-only log -- there is no un-shred) so the discard survives a
    // restart. The KEK store is untouched: shredding one record leaves
    // every other record, and every KEK, exactly as they were.
    void shred_dek(const WrappedDek& w) override {
        if (shredded_.insert(shred_key(w)).second) {
            std::ofstream out(shred_path(), std::ios::app);
            out << w.kek_version << " " << to_hex(w.bytes) << "\n";
        }
        audit_.record(kOpShred, "kek:" + std::to_string(w.kek_version));
    }

private:
    static constexpr std::string::size_type kKeyLen = 32;

    static std::string to_hex(const std::string& raw) {
        std::ostringstream os;
        os << std::hex << std::setfill('0');
        for (unsigned char c : raw) os << std::setw(2) << static_cast<int>(c);
        return os.str();
    }

    static std::string from_hex(const std::string& hex) {
        std::string out(hex.size() / 2, '\0');
        for (std::string::size_type i = 0; i + 1 < hex.size(); i += 2)
            out[i / 2] = static_cast<char>(
                std::stoi(hex.substr(i, 2), nullptr, 16));
        return out;
    }

    // Returns true if an existing store was loaded; false if none was found
    // (and the ctor-initialized KEK v1 stands).
    bool load() {
        std::ifstream in(path_);
        if (!in) return false;
        std::map<std::uint64_t, std::string> loaded;
        std::uint64_t max_v = 0;
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty()) continue;
            std::istringstream ls(line);
            std::uint64_t v = 0;
            std::string hex;
            if (!(ls >> v >> hex)) continue;
            loaded[v] = from_hex(hex);
            if (v > max_v) max_v = v;
        }
        if (loaded.empty()) return false;
        for (auto& kv : keks_) detail::secure_zero(kv.second);  // O.4: wipe the
        keks_ = std::move(loaded);                              // throwaway v1 KEK
        active_ = max_v;
        return true;
    }

    void persist() const {
        std::ofstream out(path_, std::ios::trunc);
        for (const auto& kv : keks_)
            out << kv.first << " " << to_hex(kv.second) << "\n";
    }

    std::string shred_path() const { return path_ + ".shred"; }

    void load_shreds() {
        std::ifstream in(shred_path());
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty()) continue;
            std::istringstream ls(line);
            std::uint64_t v = 0;
            std::string hex;
            if (!(ls >> v >> hex)) continue;
            shredded_.insert(shred_key(WrappedDek{v, from_hex(hex)}));
        }
    }

    compliance::AuditSink& audit_;   // O.4
    std::string path_;
    std::map<std::uint64_t, std::string> keks_{{1, detail::random_bytes(kKeyLen)}};
    std::uint64_t active_ = 1;
    std::set<std::string> shredded_;  // O.3: shred_key(w) of every shredded DEK
};

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H
