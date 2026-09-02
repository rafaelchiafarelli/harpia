// harpia bearer-session tokens -- hand-written, not generated. Copied verbatim
// into a generated project's output next to the transport headers
// (transport-authn epic, task 5 -- token-sessions), the same pattern as
// harpia_rbac.h / harpia_audit_sink.h. Copied into generated/cpp/http/ (shared
// REST + SOAP bring-up, by RestAdapter) and generated/cpp/grpc/ (the gRPC
// service impls, by GrpcServiceAdapter).
//
// Layered ON TOP OF the RBAC gate (task 4), not instead of it. The flow:
//
//   1. Obtain a token. A client that has already authenticated the transport
//      (mTLS client cert -> a verified subject CommonName -> a role via the
//      HARPIA_RBAC_MAP file) asks for a token:
//        REST  POST  <rest_base>/session          -> {"token":"...", ...}
//        SOAP  POST  <soap_base>/session with     -> <sessionToken>...</...>
//              <soap:Body><issueSession/></soap:Body>
//        gRPC  heartBeat() with request metadata `harpia-issue-session: 1`
//              -> a `harpia-session-token` trailing-metadata value
//      The issuing side embeds the caller's CN, its RBAC role, an issued-at and
//      an expiry into the token; nothing server-side is stored.
//
//   2. Present the token on subsequent calls instead of re-deriving the
//      identity from the client certificate every time:
//        REST / SOAP   Authorization: Bearer <token>
//        gRPC          authorization: Bearer <token>   (call metadata)
//      The gate verifies the token (signature + expiry + revocation) and gates
//      the call on the CN it carries. A call that presents a token which does
//      not verify is refused outright (HTTP 401 / gRPC UNAUTHENTICATED) -- it
//      does NOT silently fall back to the client certificate.
//
//   3. Revocation. HARPIA_SESSION_REVOCATIONS names a file of revoked token ids
//      (`jti`), one per line (`#` comments, blank lines ignored). It is
//      re-read whenever its contents change, so revoking a token takes effect
//      on the next call without restarting the server -- "checked on every
//      call".
//
// Configuration is deployment configuration, read once from the environment at
// startup (same posture as HARPIA_RBAC_MAP -- not schema, not compiled in):
//
//   HARPIA_SESSION_KEY          the HMAC signing key. Raw key material, or
//                               "@<path>" to read the key bytes from a file.
//                               Unset / empty -> sessions are disabled:
//                               issue() returns "" and verify() returns
//                               Verdict::no_key. Fail-safe: no key, no tokens.
//   HARPIA_SESSION_TTL          token lifetime in seconds (default 900).
//   HARPIA_SESSION_REVOCATIONS  path to the revoked-jti file (optional).
//
// Signing is real HMAC-SHA256 over a small, self-contained SHA-256 bundled
// below -- deliberately NOT a call into OpenSSL, so this header stays pure
// standard C++ and links anywhere the RBAC header does (harpia_rbac.h is
// pure-std for the same reason). WHICH crypto module a project is validated
// against (openssl / openssl_fips) is still the F5 CryptoBackend seam's
// decision, recorded in http_server_selection.json / grpc_server_selection.json
// alongside the mTLS choice; a future binding of a real crypto backend to that
// seam is where this would route through the provider's own HMAC instead.
//
// Whether any of this is compiled into the gate is a generation-time decision
// (transport_hardening_required(compliance) -- the same predicate as mTLS and
// RBAC); this header is the mechanism, not that policy.
#ifndef HARPIA_SESSION_H
#define HARPIA_SESSION_H

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <unordered_set>

#include "harpia_audit_sink.h"

namespace harpia {
namespace session {

// Domain-separation prefix mixed into every MAC so a harpia session token can
// never be mistaken for (or forged from) some other HMAC over the same key.
inline constexpr const char* kTokenContext = "harpiasess.v1.";
inline constexpr long long kDefaultTtlSeconds = 900;

struct Claims {
    std::string cn;
    std::string role;
    std::string jti;
    long long   issued_at = 0;
    long long   expires_at = 0;
};

enum class Verdict { ok, no_key, malformed, bad_signature, expired, revoked };

inline const char* verdict_name(Verdict v) {
    switch (v) {
        case Verdict::ok:            return "ok";
        case Verdict::no_key:        return "no_key";
        case Verdict::malformed:     return "malformed";
        case Verdict::bad_signature: return "bad_signature";
        case Verdict::expired:       return "expired";
        case Verdict::revoked:       return "revoked";
    }
    return "?";
}

namespace detail {

// --- base64url (no padding), self-contained ---------------------------------
inline const char* b64_alphabet() {
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
}

inline std::string b64url_encode(const std::string& in) {
    const char* a = b64_alphabet();
    std::string out;
    out.reserve((in.size() + 2) / 3 * 4);
    std::size_t i = 0;
    while (i + 3 <= in.size()) {
        const std::uint32_t n = (static_cast<std::uint8_t>(in[i]) << 16) |
                                (static_cast<std::uint8_t>(in[i + 1]) << 8) |
                                (static_cast<std::uint8_t>(in[i + 2]));
        out += a[(n >> 18) & 0x3F];
        out += a[(n >> 12) & 0x3F];
        out += a[(n >> 6) & 0x3F];
        out += a[n & 0x3F];
        i += 3;
    }
    const std::size_t rem = in.size() - i;
    if (rem == 1) {
        const std::uint32_t n = static_cast<std::uint8_t>(in[i]) << 16;
        out += a[(n >> 18) & 0x3F];
        out += a[(n >> 12) & 0x3F];
    } else if (rem == 2) {
        const std::uint32_t n = (static_cast<std::uint8_t>(in[i]) << 16) |
                                (static_cast<std::uint8_t>(in[i + 1]) << 8);
        out += a[(n >> 18) & 0x3F];
        out += a[(n >> 12) & 0x3F];
        out += a[(n >> 6) & 0x3F];
    }
    return out;
}

inline bool b64url_decode(const std::string& in, std::string* out) {
    auto val = [](char c) -> int {
        if (c >= 'A' && c <= 'Z') return c - 'A';
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;
        if (c >= '0' && c <= '9') return c - '0' + 52;
        if (c == '-') return 62;
        if (c == '_') return 63;
        return -1;
    };
    out->clear();
    std::uint32_t buf = 0;
    int bits = 0;
    for (char c : in) {
        const int v = val(c);
        if (v < 0) return false;
        buf = (buf << 6) | static_cast<std::uint32_t>(v);
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out->push_back(static_cast<char>((buf >> bits) & 0xFF));
        }
    }
    return true;
}

inline std::string to_hex(const unsigned char* p, std::size_t n) {
    static const char* h = "0123456789abcdef";
    std::string s;
    s.reserve(n * 2);
    for (std::size_t i = 0; i < n; ++i) {
        s += h[(p[i] >> 4) & 0xF];
        s += h[p[i] & 0xF];
    }
    return s;
}

// --- SHA-256 (FIPS 180-4), self-contained, no third-party dependency --------
class Sha256 {
public:
    Sha256() {
        static const std::uint32_t iv[8] = {
            0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
            0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
        std::memcpy(h_, iv, sizeof h_);
    }

    void update(const unsigned char* data, std::size_t n) {
        total_ += n;
        while (n) {
            const std::size_t take = std::min<std::size_t>(64 - fill_, n);
            std::memcpy(buf_ + fill_, data, take);
            fill_ += take;
            data += take;
            n -= take;
            if (fill_ == 64) { block(buf_); fill_ = 0; }
        }
    }

    void finish(unsigned char out[32]) {
        const std::uint64_t bits = total_ * 8;
        const unsigned char one = 0x80;
        update(&one, 1);
        const unsigned char zero = 0;
        while (fill_ != 56) update(&zero, 1);
        unsigned char lenbuf[8];
        for (int i = 0; i < 8; ++i)
            lenbuf[i] = static_cast<unsigned char>(bits >> (56 - 8 * i));
        update(lenbuf, 8);
        for (int i = 0; i < 8; ++i) {
            out[i * 4 + 0] = static_cast<unsigned char>(h_[i] >> 24);
            out[i * 4 + 1] = static_cast<unsigned char>(h_[i] >> 16);
            out[i * 4 + 2] = static_cast<unsigned char>(h_[i] >> 8);
            out[i * 4 + 3] = static_cast<unsigned char>(h_[i]);
        }
    }

private:
    static std::uint32_t rotr(std::uint32_t x, unsigned n) {
        return (x >> n) | (x << (32 - n));
    }

    void block(const unsigned char* p) {
        static const std::uint32_t k[64] = {
            0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,
            0x923f82a4u,0xab1c5ed5u,0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,
            0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,0xe49b69c1u,0xefbe4786u,
            0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
            0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,
            0x06ca6351u,0x14292967u,0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,
            0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,0xa2bfe8a1u,0xa81a664bu,
            0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
            0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,
            0x5b9cca4fu,0x682e6ff3u,0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,
            0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
        std::uint32_t w[64];
        for (int i = 0; i < 16; ++i)
            w[i] = (std::uint32_t(p[i * 4]) << 24) |
                   (std::uint32_t(p[i * 4 + 1]) << 16) |
                   (std::uint32_t(p[i * 4 + 2]) << 8) |
                   std::uint32_t(p[i * 4 + 3]);
        for (int i = 16; i < 64; ++i) {
            const std::uint32_t s0 =
                rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const std::uint32_t s1 =
                rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        std::uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3];
        std::uint32_t e = h_[4], f = h_[5], g = h_[6], hh = h_[7];
        for (int i = 0; i < 64; ++i) {
            const std::uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            const std::uint32_t ch = (e & f) ^ (~e & g);
            const std::uint32_t t1 = hh + S1 + ch + k[i] + w[i];
            const std::uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            const std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t t2 = S0 + maj;
            hh = g; g = f; f = e; e = d + t1;
            d = c; c = b; b = a; a = t1 + t2;
        }
        h_[0] += a; h_[1] += b; h_[2] += c; h_[3] += d;
        h_[4] += e; h_[5] += f; h_[6] += g; h_[7] += hh;
    }

    std::uint32_t h_[8];
    std::uint64_t total_ = 0;
    unsigned char buf_[64]{};
    std::size_t fill_ = 0;
};

inline void sha256(const unsigned char* data, std::size_t n,
                   unsigned char out[32]) {
    Sha256 s;
    s.update(data, n);
    s.finish(out);
}

// HMAC-SHA256 (RFC 2104), hex-encoded. Block size 64.
inline std::string hmac_sha256_hex(const std::string& key,
                                   const std::string& msg) {
    unsigned char k0[64];
    std::memset(k0, 0, sizeof k0);
    if (key.size() > 64) {
        sha256(reinterpret_cast<const unsigned char*>(key.data()), key.size(),
               k0);  // remaining 32 bytes stay zero
    } else {
        std::memcpy(k0, key.data(), key.size());
    }
    unsigned char ipad[64], opad[64];
    for (int i = 0; i < 64; ++i) {
        ipad[i] = static_cast<unsigned char>(k0[i] ^ 0x36);
        opad[i] = static_cast<unsigned char>(k0[i] ^ 0x5c);
    }
    unsigned char inner[32];
    {
        Sha256 s;
        s.update(ipad, 64);
        s.update(reinterpret_cast<const unsigned char*>(msg.data()), msg.size());
        s.finish(inner);
    }
    unsigned char mac[32];
    {
        Sha256 s;
        s.update(opad, 64);
        s.update(inner, 32);
        s.finish(mac);
    }
    return to_hex(mac, 32);
}

// 128-bit random hex id for a token's jti (revocation key). std::random_device
// is a nonce source here, not a long-term key -- adequate for a token id.
inline std::string random_hex_128() {
    std::random_device rd;
    unsigned char b[16];
    for (int i = 0; i < 16; i += 4) {
        const std::uint32_t r = rd();
        b[i + 0] = static_cast<unsigned char>(r);
        b[i + 1] = static_cast<unsigned char>(r >> 8);
        b[i + 2] = static_cast<unsigned char>(r >> 16);
        b[i + 3] = static_cast<unsigned char>(r >> 24);
    }
    return to_hex(b, 16);
}

// length-independent equal-time compare of two hex MAC strings.
inline bool constant_time_equal(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) return false;
    unsigned char diff = 0;
    for (std::size_t i = 0; i < a.size(); ++i)
        diff |= static_cast<unsigned char>(a[i] ^ b[i]);
    return diff == 0;
}

inline std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return {};
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

// trim one trailing '\n'/'\r' run -- a key file usually ends with a newline the
// author never meant to be part of the key.
inline std::string rstrip_newline(std::string s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
    return s;
}

}  // namespace detail

// The HMAC signing key, resolved once. "" means sessions are disabled.
inline const std::string& signing_key() {
    static const std::string key = [] {
        const char* v = std::getenv("HARPIA_SESSION_KEY");
        if (!v || !*v) return std::string{};
        std::string s(v);
        if (s.size() > 1 && s[0] == '@')
            return detail::rstrip_newline(detail::read_file(s.substr(1)));
        return s;
    }();
    return key;
}

inline long long default_ttl_seconds() {
    static const long long ttl = [] {
        const char* v = std::getenv("HARPIA_SESSION_TTL");
        if (v && *v) {
            const long long n = std::atoll(v);
            if (n > 0) return n;
        }
        return kDefaultTtlSeconds;
    }();
    return ttl;
}

// Revoked-jti set, re-read from HARPIA_SESSION_REVOCATIONS whenever the file's
// mtime moves. Thread-safe (a small critical section per lookup) -- unlike
// harpia_rbac.h's load-once RoleMap, because a revocation must land without a
// server restart.
class RevocationList {
public:
    static RevocationList& instance() {
        static RevocationList inst;
        return inst;
    }

    bool contains(const std::string& jti) {
        if (jti.empty()) return false;
        std::lock_guard<std::mutex> lock(mu_);
        reload_if_changed();
        return revoked_.count(jti) != 0;
    }

private:
    RevocationList() {
        const char* p = std::getenv("HARPIA_SESSION_REVOCATIONS");
        if (p && *p) path_ = p;
    }

    void reload_if_changed() {
        if (path_.empty()) return;
        std::ifstream in(path_, std::ios::binary);
        if (!in) { revoked_.clear(); loaded_stamp_.clear(); return; }
        std::ostringstream ss;
        ss << in.rdbuf();
        const std::string body = ss.str();
        // content-hash the file rather than stat() it: robust across filesystems
        // whose mtime granularity is coarse (a test revokes a jti milliseconds
        // after issuing it).
        const std::string stamp =
            detail::hmac_sha256_hex("revlist", body);
        if (stamp == loaded_stamp_) return;
        revoked_.clear();
        std::istringstream lines(body);
        std::string line;
        while (std::getline(lines, line)) {
            const auto hash = line.find('#');
            if (hash != std::string::npos) line.erase(hash);
            std::istringstream ls(line);
            std::string tok;
            if (ls >> tok) revoked_.insert(tok);
        }
        loaded_stamp_ = stamp;
    }

    std::mutex mu_;
    std::string path_;
    std::string loaded_stamp_;
    std::unordered_set<std::string> revoked_;
};

// Decode a token's payload WITHOUT checking the MAC, expiry or revocation.
// Diagnostics + the gate's audit records. false on a structurally bad token.
inline bool decode(const std::string& token, Claims* out) {
    // v1.<b64url(payload)>.<machex>
    if (token.compare(0, 3, "v1.") != 0) return false;
    const auto dot = token.rfind('.');
    if (dot == std::string::npos || dot <= 2) return false;
    const std::string b64 = token.substr(3, dot - 3);
    std::string payload;
    if (!detail::b64url_decode(b64, &payload)) return false;
    // payload = cn \n role \n iat \n exp \n jti
    std::istringstream ps(payload);
    std::string cn, role, iat, exp, jti;
    if (!std::getline(ps, cn) || !std::getline(ps, role) ||
        !std::getline(ps, iat) || !std::getline(ps, exp) ||
        !std::getline(ps, jti)) {
        return false;
    }
    out->cn = cn;
    out->role = role;
    out->issued_at = std::atoll(iat.c_str());
    out->expires_at = std::atoll(exp.c_str());
    out->jti = jti;
    return true;
}

// Mint a bearer token for an identity the transport has already authenticated.
// `cn` / `role` come straight from the RBAC gate. Returns "" when there is no
// signing key, `cn` is empty, or `cn`/`role` contain a newline (they never do
// in practice -- a cert CN / an RBAC role -- but the format is line-delimited).
inline std::string issue(const std::string& cn, const std::string& role,
                         long long ttl_seconds = 0, long long now = 0) {
    if (signing_key().empty() || cn.empty()) return {};
    if (cn.find('\n') != std::string::npos ||
        role.find('\n') != std::string::npos) {
        return {};
    }
    if (ttl_seconds <= 0) ttl_seconds = default_ttl_seconds();
    if (now <= 0) now = static_cast<long long>(std::time(nullptr));

    const std::string jti = detail::random_hex_128();

    std::ostringstream payload;
    payload << cn << '\n' << role << '\n' << now << '\n'
            << (now + ttl_seconds) << '\n' << jti;
    const std::string b64 = detail::b64url_encode(payload.str());
    const std::string mac =
        detail::hmac_sha256_hex(signing_key(), kTokenContext + b64);
    return "v1." + b64 + "." + mac;
}

// Full verification: structure, MAC, expiry, revocation. Fills *out on ok.
// Emits exactly one AuditSink "session_denied" record on any non-ok verdict --
// verdict + jti + cn metadata only, never the token bytes (design-rules Rule 5;
// record()'s signature structurally cannot carry a secret).
inline Verdict verify(const std::string& token, Claims* out, long long now = 0,
                      ::harpia::compliance::AuditSink& audit =
                          ::harpia::compliance::default_audit_sink()) {
    auto deny = [&](Verdict v, const Claims& c) {
        std::string detail = "verdict=";
        detail += verdict_name(v);
        detail += " cn=";
        detail += c.cn.empty() ? "<none>" : c.cn;
        detail += " jti=";
        detail += c.jti.empty() ? "<none>" : c.jti;
        audit.record("session_denied", "session", detail);
        return v;
    };

    if (signing_key().empty()) return deny(Verdict::no_key, Claims{});

    Claims c;
    if (!decode(token, &c)) return deny(Verdict::malformed, Claims{});

    const auto dot = token.rfind('.');
    const std::string b64 = token.substr(3, dot - 3);
    const std::string presented = token.substr(dot + 1);
    const std::string expected =
        detail::hmac_sha256_hex(signing_key(), kTokenContext + b64);
    if (!detail::constant_time_equal(presented, expected))
        return deny(Verdict::bad_signature, c);

    if (now <= 0) now = static_cast<long long>(std::time(nullptr));
    if (now >= c.expires_at) return deny(Verdict::expired, c);

    if (RevocationList::instance().contains(c.jti))
        return deny(Verdict::revoked, c);

    *out = c;
    return Verdict::ok;
}

// What a transport gate needs from an Authorization header: whether a bearer
// token was presented at all, and -- if so -- its verify() verdict and the CN
// it carries. `header_value` is the raw header ("Bearer <tok>", "bearer <tok>"
// or a bare "<tok>"), or "" when the header is absent.
//
// A caller substitutes `cn` for its transport-verified identity ONLY when
// `present && verdict == Verdict::ok`; when `present` and the verdict is
// anything else it must refuse the call (401 / UNAUTHENTICATED) rather than
// fall through to the client certificate.
struct Bearer {
    bool present = false;
    Verdict verdict = Verdict::malformed;
    std::string cn;
    std::string role;
};

inline Bearer from_authorization(const std::string& header_value,
                                 long long now = 0,
                                 ::harpia::compliance::AuditSink& audit =
                                     ::harpia::compliance::default_audit_sink()) {
    Bearer b;
    std::string tok = header_value;
    // strip a leading "Bearer " / "bearer " (case-insensitive on the scheme)
    if (tok.size() >= 7) {
        std::string scheme = tok.substr(0, 7);
        for (auto& ch : scheme)
            ch = static_cast<char>(
                std::tolower(static_cast<unsigned char>(ch)));
        if (scheme == "bearer ") tok = tok.substr(7);
    }
    // trim surrounding whitespace
    while (!tok.empty() && (tok.front() == ' ' || tok.front() == '\t'))
        tok.erase(tok.begin());
    while (!tok.empty() && (tok.back() == ' ' || tok.back() == '\t' ||
                            tok.back() == '\r' || tok.back() == '\n'))
        tok.pop_back();
    if (tok.empty()) return b;   // no token presented

    b.present = true;
    Claims c;
    b.verdict = verify(tok, &c, now, audit);
    if (b.verdict == Verdict::ok) {
        b.cn = c.cn;
        b.role = c.role;
    }
    return b;
}

}  // namespace session
}  // namespace harpia

#endif  // HARPIA_SESSION_H
