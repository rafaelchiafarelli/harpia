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
// Out of scope here (later O sessions): crypto-shredding (O.3), zeroization
// + AuditSink wiring (O.4), the KMS/HSM reference adapter (O.5).
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
#include <random>
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
    explicit LocalKeyProvider(const LocalKeyProviderConfig& cfg)
        : path_(cfg.storage_path) {
        if (cfg.phi_at_scale && !cfg.acknowledged)
            throw LocalKeyProviderRefused();
        if (!load())
            persist();  // fresh store: KEK v1 was minted below in the ctor init
    }

    std::uint64_t active_kek_version() const override { return active_; }

    Dek generate_dek() override { return Dek{random_bytes(kKeyLen)}; }

    WrappedDek wrap_dek(const Dek& dek) override {
        return WrappedDek{active_, Dek::xor_with(dek.material, keks_.at(active_))};
    }

    std::optional<Dek> unwrap_dek(const WrappedDek& w) override {
        auto it = keks_.find(w.kek_version);
        if (it == keks_.end()) return std::nullopt;
        return Dek{Dek::xor_with(w.bytes, it->second)};
    }

    std::uint64_t rotate() override {
        ++active_;
        keks_[active_] = random_bytes(kKeyLen);
        persist();
        return active_;
    }

private:
    static constexpr std::string::size_type kKeyLen = 32;

    static std::string random_bytes(std::string::size_type n) {
        static std::random_device rd;
        std::uniform_int_distribution<int> byte(0, 255);
        std::string out(n, '\0');
        for (auto& c : out) c = static_cast<char>(byte(rd));
        return out;
    }

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
        keks_ = std::move(loaded);
        active_ = max_v;
        return true;
    }

    void persist() const {
        std::ofstream out(path_, std::ios::trunc);
        for (const auto& kv : keks_)
            out << kv.first << " " << to_hex(kv.second) << "\n";
    }

    std::string path_;
    std::map<std::uint64_t, std::string> keks_{{1, random_bytes(kKeyLen)}};
    std::uint64_t active_ = 1;
};

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H
