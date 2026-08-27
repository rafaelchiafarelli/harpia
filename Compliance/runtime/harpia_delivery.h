// harpia delivery-guarantee runtime -- hand-written, not generated.
// Transport- and payload-agnostic: it moves opaque serialized bytes, so the
// same machinery serves ZMQ (sensitive-data roadmap Phase 3b) and, later,
// gRPC/DDS. Copied verbatim into a generated project the same way
// Capability/runtime/harpia_capability_dispatch.h and
// Compliance/runtime/harpia_audit_sink.h are.
//
// From Initiatives/medical_devices/harpia_sensitive_data_design_rules.md:
//   Rule 3  -- Envelope carries an origin-computed CRC and a monotonic seq.
//              The CRC is verified only at trust-boundary crossings
//              (arrival / departure), never recomputed between internal
//              steps within one custody domain.
//   Rule 4a -- `critical` message types: a bounded queue. On overflow it
//              ROTATES (drops the oldest) and exposes that it did -- never a
//              silent drop, never unbounded growth. seq gives the receiver
//              gap detection.
//   Rule 4b -- latest-value-only (routine telemetry): a single-slot
//              mailbox. Superseding a still-unsent value is an explicit,
//              named event, not a silent loss. Fixed, small memory
//              regardless of throughput.
//   Rule 5  -- every fallible operation returns a distinct, observable
//              outcome; nothing is swallowed, nothing returns bare void.
//   Rule 2  -- NO plausibility/range checks on payload bytes here: sensor
//              truth is the acquisition layer's contract, not delivery's.
//   Rule 4  -- bounded-blocking synchronous send is explicitly rejected;
//              push() never blocks (it rotates instead).
//
// Which container a message type gets is decided by the schema's `critical`
// modifier (Message.is_critical), wired in Phase 3b -- this header is just
// the mechanism, it does not read the schema.
//
// NOT thread-safe -- caller-synchronized, same contract as
// harpia_capability_dispatch.h. Phase 3b decides whether its send path
// needs its own lock.
#ifndef HARPIA_DELIVERY_H
#define HARPIA_DELIVERY_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <utility>

#include "harpia_audit_sink.h"

namespace harpia {
namespace delivery {

namespace detail {

// CRC-32 (IEEE 802.3, reflected, polynomial 0xEDB88320) -- self-contained,
// no <zlib.h> dependency. Table built once on first use.
inline std::uint32_t crc32(const std::string& bytes) {
    static const std::array<std::uint32_t, 256> table = [] {
        std::array<std::uint32_t, 256> t{};
        for (std::uint32_t i = 0; i < 256; ++i) {
            std::uint32_t c = i;
            for (int k = 0; k < 8; ++k)
                c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
            t[i] = c;
        }
        return t;
    }();
    std::uint32_t crc = 0xFFFFFFFFu;
    for (unsigned char b : bytes)
        crc = table[(crc ^ b) & 0xFFu] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

}  // namespace detail

// A payload plus its integrity/ordering metadata. `payload` is opaque
// serialized message bytes -- this runtime never parses it (Rule 2).
struct Envelope {
    std::uint64_t seq = 0;                    // monotonic, assigned at origin
    std::uint32_t crc = 0;                    // CRC-32 of payload, computed at origin
    std::int64_t  delivery_timestamp_ms = 0;  // epoch ms at origin; 0 = unset (latency visibility, Rule 4a)
    std::string   payload;

    // Stamp at ORIGIN (Rule 3): the CRC is computed here, once, and then
    // carried unmodified for the whole lifecycle. `seq` and the timestamp
    // are the caller's to supply (the caller owns the sequence counter and
    // the clock).
    static Envelope stamp(std::uint64_t seq, std::string payload,
                          std::int64_t delivery_timestamp_ms = 0) {
        Envelope e;
        e.seq = seq;
        e.payload = std::move(payload);
        e.delivery_timestamp_ms = delivery_timestamp_ms;
        e.crc = detail::crc32(e.payload);
        return e;
    }

    // Verify at a trust-boundary crossing (Rule 3): true iff the payload
    // still hashes to the CRC stamped at origin.
    bool crc_ok() const { return detail::crc32(payload) == crc; }
};

// Result of the arrival-boundary check (Rule 3 + seq gap detection).
enum class Arrival {
    Ok,           // crc valid, seq is exactly the one expected next
    CrcMismatch,  // payload corrupted in transit -- reject and audit, never "fix" (Rule 5)
    SeqGap,       // env.seq > expected: one or more messages lost in transit
    SeqRegressed  // env.seq < expected: a duplicate or a reordered older message
};

// `expected` is the seq the receiver expects next (typically last_seen + 1).
// For the very first message on a stream, pass expected == env.seq to accept
// any starting point.
inline Arrival check_on_arrival(const Envelope& env, std::uint64_t expected) {
    if (!env.crc_ok())      return Arrival::CrcMismatch;
    if (env.seq < expected) return Arrival::SeqRegressed;
    if (env.seq > expected) return Arrival::SeqGap;
    return Arrival::Ok;
}

// ---- Rule 4a: ordered/complete delivery for `critical` message types -----

enum class PushOutcome {
    Accepted,       // enqueued, capacity was available
    RotatedOldest   // capacity was full: the oldest envelope was dropped to
                    // make room -- an audited event, never silent (Rule 4a)
};

// Fixed-capacity queue. Never grows past `capacity`; never blocks. On
// overflow it drops the OLDEST (rotation), records the event through the
// AuditSink, and keeps a running count -- the "track and expose that
// rotation occurred, don't hide data loss" requirement in Rule 4a.
class BoundedQueue {
public:
    explicit BoundedQueue(
        std::size_t capacity,
        compliance::AuditSink& audit = compliance::default_audit_sink(),
        std::string subject = "delivery_queue")
        : capacity_(capacity ? capacity : 1),
          audit_(audit),
          subject_(std::move(subject)) {}

    PushOutcome push(Envelope env) {
        PushOutcome outcome = PushOutcome::Accepted;
        if (buf_.size() >= capacity_) {
            last_rotated_seq_ = buf_.front().seq;
            buf_.pop_front();
            ++rotations_;
            outcome = PushOutcome::RotatedOldest;
            audit_.record("queue_rotated", subject_,
                          "dropped_seq=" + std::to_string(last_rotated_seq_));
        }
        buf_.push_back(std::move(env));
        return outcome;
    }

    // Oldest-first (FIFO) -- ordered delivery. Empty optional when drained.
    std::optional<Envelope> pop() {
        if (buf_.empty()) return std::nullopt;
        Envelope e = std::move(buf_.front());
        buf_.pop_front();
        return e;
    }

    std::size_t   size() const { return buf_.size(); }
    std::size_t   capacity() const { return capacity_; }
    bool          empty() const { return buf_.empty(); }
    std::size_t   rotations() const { return rotations_; }        // total rotation events
    std::uint64_t last_rotated_seq() const { return last_rotated_seq_; }

private:
    std::size_t          capacity_;
    std::deque<Envelope> buf_;
    std::size_t          rotations_ = 0;
    std::uint64_t        last_rotated_seq_ = 0;
    compliance::AuditSink& audit_;
    std::string          subject_;
};

// ---- Rule 4b: latest-value-only delivery for routine telemetry ----------

enum class PutOutcome {
    Stored,     // slot was empty
    Overwrote   // a still-unsent value was superseded -- an audited, named
                // event, not a silent loss (Rule 4b)
};

// A single pending slot. Structurally cannot "overflow": put() overwrites.
// This is Rule 4b's double-buffer realized as one slot, which is sufficient
// while the runtime is caller-synchronized (no concurrent reader needing a
// stable front buffer); a real front/back split would be a Phase 3b concern
// if the ZMQ send path ends up threaded.
class Mailbox {
public:
    explicit Mailbox(
        compliance::AuditSink& audit = compliance::default_audit_sink(),
        std::string subject = "delivery_mailbox")
        : audit_(audit), subject_(std::move(subject)) {}

    PutOutcome put(Envelope env) {
        PutOutcome outcome = PutOutcome::Stored;
        if (pending_.has_value()) {
            last_overwritten_seq_ = pending_->seq;
            ++overwrites_;
            outcome = PutOutcome::Overwrote;
            audit_.record("mailbox_overwritten", subject_,
                          "superseded_seq=" + std::to_string(last_overwritten_seq_));
        }
        pending_ = std::move(env);
        return outcome;
    }

    // The current pending value, if any; clears the slot.
    std::optional<Envelope> take() {
        if (!pending_.has_value()) return std::nullopt;
        Envelope e = std::move(*pending_);
        pending_.reset();
        return e;
    }

    bool          has_pending() const { return pending_.has_value(); }
    std::size_t   overwrites() const { return overwrites_; }
    std::uint64_t last_overwritten_seq() const { return last_overwritten_seq_; }

private:
    std::optional<Envelope> pending_;
    std::size_t             overwrites_ = 0;
    std::uint64_t           last_overwritten_seq_ = 0;
    compliance::AuditSink&  audit_;
    std::string             subject_;
};

}  // namespace delivery
}  // namespace harpia

#endif  // HARPIA_DELIVERY_H
