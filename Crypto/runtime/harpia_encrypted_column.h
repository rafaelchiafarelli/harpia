// harpia EncryptedColumn -- Track A / Session A.1. Field-level encryption of
// `phi` database columns, built on Track O's envelope-encryption KeyProvider
// (harpia_key_provider.h). Hand-written, copied verbatim into a generated
// project's output by CrudlAdapter whenever a message has a `phi` column --
// same pattern as harpia_audit_sink.h / harpia_key_provider*.h.
//
// A `phi` value is never persisted in plaintext. On the DAO write path
// (create / update), encrypt_field():
//   1. mints a fresh DEK for this value          (KeyProvider::generate_dek)
//   2. seals the value with that DEK             (Dek::seal)
//   3. wraps the DEK with the active KEK         (KeyProvider::wrap_dek)
//   4. frames {kek_version, wrapped_dek, ciphertext} and hex-encodes it
//      behind a versioned "enc:v1:" marker, so it stores in the column's
//      existing TEXT type unchanged (hex is NUL-free; a raw ciphertext blob
//      would truncate at the first NUL through SOCI's default TEXT binding).
// On the read path, decrypt_field() reverses it. An unknown or
// crypto-shredded DEK yields "" -- never a throw, never a zeroed-key
// plaintext (Rule 5: KeyProvider::unwrap_dek returns nullopt).
//
// The XOR "cipher" is inherited from the O.* placeholder KeyProvider -- the
// real AEAD lands when a backend is bound to the F5 CryptoBackend seam.
// This file adds no crypto of its own: it only frames and routes.
#ifndef HARPIA_CRYPTO_ENCRYPTED_COLUMN_H
#define HARPIA_CRYPTO_ENCRYPTED_COLUMN_H

#include <cstdint>
#include <cstdlib>
#include <optional>
#include <string>

#include "harpia_key_provider.h"

namespace harpia {
namespace crypto {

// Versioned marker prefixing every encrypted column value. Its presence is
// how the read path (and a raw DB inspection) tells ciphertext from a
// legacy plaintext row.
inline constexpr const char* kEncMarker = "enc:v1:";

namespace detail {

inline std::string to_hex(const std::string& raw) {
    static const char* kDigits = "0123456789abcdef";
    std::string out;
    out.reserve(raw.size() * 2);
    for (unsigned char c : raw) {
        out.push_back(kDigits[c >> 4]);
        out.push_back(kDigits[c & 0x0f]);
    }
    return out;
}

inline bool from_hex(const std::string& hex, std::string& out) {
    if (hex.size() % 2 != 0) return false;
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    out.clear();
    out.reserve(hex.size() / 2);
    for (std::string::size_type i = 0; i < hex.size(); i += 2) {
        const int hi = nibble(hex[i]);
        const int lo = nibble(hex[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back(static_cast<char>((hi << 4) | lo));
    }
    return true;
}

inline void put_u64(std::string& s, std::uint64_t v) {
    for (int i = 7; i >= 0; --i)
        s.push_back(static_cast<char>((v >> (i * 8)) & 0xff));
}

inline void put_u32(std::string& s, std::uint32_t v) {
    for (int i = 3; i >= 0; --i)
        s.push_back(static_cast<char>((v >> (i * 8)) & 0xff));
}

inline std::uint64_t get_u64(const std::string& s, std::string::size_type off) {
    std::uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v = (v << 8) | static_cast<unsigned char>(s[off + i]);
    return v;
}

inline std::uint32_t get_u32(const std::string& s, std::string::size_type off) {
    std::uint32_t v = 0;
    for (int i = 0; i < 4; ++i)
        v = (v << 8) | static_cast<unsigned char>(s[off + i]);
    return v;
}

}  // namespace detail

// A process-wide default KeyProvider so a generated DAO's constructor can
// offer a no-argument form. In-process, non-persistent, DUMMY (see
// InMemoryKeyProvider) -- a real deployment constructs its own
// LocalKeyProvider / KmsKeyProvider and passes it explicitly.
inline KeyProvider& default_key_provider() {
    static InMemoryKeyProvider instance;
    return instance;
}

// Encrypt one `phi` value for storage. The result is always marker-prefixed
// hex, so it is safe in a TEXT column and trivially distinguishable from
// plaintext by a raw DB query.
inline std::string encrypt_field(KeyProvider& kp, const std::string& plaintext) {
    Dek dek = kp.generate_dek();
    const std::string ciphertext = dek.seal(plaintext);
    const WrappedDek w = kp.wrap_dek(dek);

    std::string frame;
    detail::put_u64(frame, w.kek_version);
    detail::put_u32(frame, static_cast<std::uint32_t>(w.bytes.size()));
    frame += w.bytes;
    frame += ciphertext;
    return std::string(kEncMarker) + detail::to_hex(frame);
}

// Reverse encrypt_field(). A value without the marker is returned unchanged
// (defensive: a pre-encryption row, or a non-`phi` caller). A malformed
// frame, or an unknown / crypto-shredded DEK, yields "" -- never a throw
// (Rule 5).
inline std::string decrypt_field(KeyProvider& kp, const std::string& stored) {
    const std::string marker(kEncMarker);
    if (stored.size() < marker.size() ||
        stored.compare(0, marker.size(), marker) != 0)
        return stored;

    std::string frame;
    if (!detail::from_hex(stored.substr(marker.size()), frame) ||
        frame.size() < 12)
        return "";
    const std::uint64_t kek_version = detail::get_u64(frame, 0);
    const std::uint32_t wrapped_len = detail::get_u32(frame, 8);
    if (frame.size() < 12u + wrapped_len) return "";

    WrappedDek w;
    w.kek_version = kek_version;
    w.bytes = frame.substr(12, wrapped_len);
    const std::string ciphertext = frame.substr(12u + wrapped_len);

    std::optional<Dek> dek = kp.unwrap_dek(w);
    if (!dek) return "";
    return dek->open(ciphertext);
}

// decrypt_field() + a parse back to a numeric field's own type, for a `phi`
// column whose declared type is not text. A non-recoverable value ("" from
// decrypt_field) parses to 0 -- the same fail-safe zero the read path
// already substitutes for a NULL column, never a throw.
inline long long decrypt_field_ll(KeyProvider& kp, const std::string& stored) {
    const std::string p = decrypt_field(kp, stored);
    return p.empty() ? 0 : std::strtoll(p.c_str(), nullptr, 10);
}

inline int decrypt_field_int(KeyProvider& kp, const std::string& stored) {
    return static_cast<int>(decrypt_field_ll(kp, stored));
}

inline double decrypt_field_double(KeyProvider& kp, const std::string& stored) {
    const std::string p = decrypt_field(kp, stored);
    if (p.empty()) return 0.0;
    char* end = nullptr;
    const double v = std::strtod(p.c_str(), &end);
    return end == p.c_str() ? 0.0 : v;
}

}  // namespace crypto
}  // namespace harpia

#endif  // HARPIA_CRYPTO_ENCRYPTED_COLUMN_H
