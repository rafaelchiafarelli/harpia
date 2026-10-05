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
//
// File modes (cpp-key-store-permissions-DEFECT): on POSIX the store and the
// .shred sidecar are created and rewritten owner-only (0600), whatever the
// umask -- open(..., 0600) + fchmod before any byte is written, so there is
// no window with wider bits. An existing store or sidecar with any group/
// other bit set is REFUSED (LocalKeyStoreInsecure), never tightened
// silently: its KEK material may already have been read, so the operator
// must decide (rotate, then chmod 0600). On Windows there are no POSIX
// modes; protecting the file (ACLs) is out of scope and the check is
// compiled out.
#ifndef HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H
#define HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H

#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <ios>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#ifndef _WIN32
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>
#endif

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

// Thrown by LocalKeyProvider's constructor when the existing KEK store or
// its .shred sidecar is readable/writable by group or others (POSIX only).
class LocalKeyStoreInsecure : public std::runtime_error {
public:
    LocalKeyStoreInsecure(const std::string& path, unsigned mode)
        : std::runtime_error(
              "LocalKeyProvider refused: key store file " + path +
              " has mode " + octal(mode) + "; it must be 0600 (owner-only). "
              "Its key material may have been exposed: rotate, then "
              "chmod 0600") {}

private:
    static std::string octal(unsigned mode) {
        std::ostringstream os;
        os << std::oct << std::setw(4) << std::setfill('0') << (mode & 0777u);
        return os.str();
    }
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

// Thread-safe (db-concurrency task 1b): every operation holds mu_, including
// the store rewrite in rotate() and the shred-sidecar append.
class LocalKeyProvider : public KeyProvider {
public:
    explicit LocalKeyProvider(
        const LocalKeyProviderConfig& cfg,
        compliance::AuditSink& audit = compliance::default_audit_sink())
        : audit_(audit), path_(cfg.storage_path) {
        if (cfg.phi_at_scale && !cfg.acknowledged)
            throw LocalKeyProviderRefused();
        refuse_if_loose(path_);
        refuse_if_loose(shred_path());
        if (!load()) {
            persist();  // fresh store: KEK v1 was minted in the ctor init
            audit_.record(kOpGenerate, "kek:" + std::to_string(active_));
        }
        load_shreds();
    }

    ~LocalKeyProvider() override {
        for (auto& kv : keks_) detail::secure_zero(kv.second);  // O.4
    }

    std::uint64_t active_kek_version() const override {
        std::lock_guard<std::mutex> lock(mu_);
        return active_;
    }

    Dek generate_dek() override {
        audit_.record(kOpGenerate, "dek");
        return Dek(detail::random_bytes(kKeyLen));
    }

    WrappedDek wrap_dek(const Dek& dek) override {
        std::lock_guard<std::mutex> lock(mu_);
        audit_.record(kOpWrap, "kek:" + std::to_string(active_));
        return WrappedDek{active_, Dek::xor_with(dek.material, keks_.at(active_))};
    }

    std::optional<Dek> unwrap_dek(const WrappedDek& w) override {
        std::lock_guard<std::mutex> lock(mu_);
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
        std::lock_guard<std::mutex> lock(mu_);
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
        std::lock_guard<std::mutex> lock(mu_);
        if (shredded_.insert(shred_key(w)).second)
            write_private(shred_path(),
                          std::to_string(w.kek_version) + " " +
                              to_hex(w.bytes) + "\n",
                          true);
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
        std::string text;
        for (const auto& kv : keks_)
            text += std::to_string(kv.first) + " " + to_hex(kv.second) + "\n";
        write_private(path_, text, false);
        detail::secure_zero(text);
    }

    // Owner-only write (truncate or append). POSIX: the fd is opened 0600
    // and fchmod'ed before any byte lands, so a pre-existing file being
    // rewritten never holds key material with wider bits either.
    static void write_private(const std::string& path, const std::string& data,
                              bool append) {
#ifndef _WIN32
        const int flags = O_WRONLY | O_CREAT | (append ? O_APPEND : O_TRUNC);
        const int fd = ::open(path.c_str(), flags, 0600);
        if (fd < 0) return;
        if (::fchmod(fd, 0600) != 0) { ::close(fd); return; }
        const char* p = data.data();
        std::string::size_type left = data.size();
        while (left > 0) {
            const ::ssize_t n = ::write(fd, p, left);
            if (n < 0) { if (errno == EINTR) continue; break; }
            p += n;
            left -= static_cast<std::string::size_type>(n);
        }
        ::close(fd);
#else
        std::ofstream out(path, append ? std::ios::app : std::ios::trunc);
        out << data;
#endif
    }

    // An existing file with any group/other bit is refused (never tightened).
    static void refuse_if_loose(const std::string& path) {
#ifndef _WIN32
        struct ::stat st;
        if (::stat(path.c_str(), &st) == 0 && (st.st_mode & 077) != 0)
            throw LocalKeyStoreInsecure(path, static_cast<unsigned>(st.st_mode));
#else
        (void)path;
#endif
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
    mutable std::mutex mu_;          // 1b: guards keks_/active_/shredded_ + files
    std::string path_;
    std::map<std::uint64_t, std::string> keks_{{1, detail::random_bytes(kKeyLen)}};
    std::uint64_t active_ = 1;
    std::set<std::string> shredded_;  // O.3: shred_key(w) of every shredded DEK
};

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_KEY_PROVIDER_LOCAL_H
