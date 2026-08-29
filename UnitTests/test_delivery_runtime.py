"""Tests for the delivery-guarantee runtime (sensitive-data roadmap Phase 3a).

Compliance/runtime/harpia_delivery.h is hand-written, transport-agnostic C++,
copied verbatim into generated output later (Phase 3b wires ZmqAdapter to it).
Same test pattern as test_audit_sink.py: compile and run small standalone C++
programs against the header directly, no generated project needed. Skipped
when g++ is absent.

Covers, from harpia_sensitive_data_design_rules.md:
  - Rule 3  -- Envelope stamps a CRC at origin; crc_ok() catches a mutated
               payload; check_on_arrival distinguishes Ok / CrcMismatch /
               SeqGap / SeqRegressed.
  - Rule 4a -- BoundedQueue: FIFO, fixed capacity, overflow ROTATES (drops
               oldest) with an observable PushOutcome, a running rotations()
               count, last_rotated_seq(), and an AuditSink "queue_rotated"
               record -- never a silent drop. peek() is a non-destructive
               look at the oldest, so a drain loop can send-then-pop and
               keep order across a failed send.
  - Rule 4b -- Mailbox: latest-value-only, put() overwrites with an
               observable PutOutcome, overwrites() count, and an AuditSink
               "mailbox_overwritten" record.
  - Rule 5  -- every fallible op returns a distinct value; a corrupt payload
               is rejected, never "corrected".
Plus a unit-level rehearsal of Phase 3c's headline test: a simulated stall
overruns the queue, then a drain replays the survivors in order.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

from Compliance.delivery_common import DELIVERY_RUNTIME_SRC  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile_and_run(tmp_path, cpp_source, name):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(cpp_source, encoding="utf-8")
    binpath = tmp_path / name
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", REPO_ROOT,
         str(src), "-o", str(binpath)],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    return subprocess.run([str(binpath)], capture_output=True, text=True)


# A test AuditSink that counts record() calls per operation, so a test can
# assert rotation/overwrite really are audited (never silent). Mirrors the
# "invent your own operation strings" contract in harpia_audit_sink.h.
_COUNTING_SINK = '''
#include "Compliance/runtime/harpia_delivery.h"
#include <map>
#include <string>
struct CountingSink : harpia::compliance::AuditSink {
    std::map<std::string, int> calls;
    std::string last_detail;
    void record(const std::string& op, const std::string& /*subject*/,
                const std::string& detail = "") override {
        calls[op] += 1;
        last_detail = detail;
    }
};
'''


def _run_case(tmp_path, name, body, extra_top=""):
    return _compile_and_run(tmp_path, _COUNTING_SINK + extra_top + '''
int main() {
''' + body + '''
    return 0;
}
''', name)


# -- Rule 3: envelope integrity + ordering ---------------------------------

def test_envelope_stamp_and_crc_ok(tmp_path):
    r = _run_case(tmp_path, "crc_ok", '''
    using namespace harpia::delivery;
    Envelope e = Envelope::stamp(1, "the-payload-bytes", 1234);
    if (e.seq != 1) return 10;
    if (e.delivery_timestamp_ms != 1234) return 11;
    if (e.crc == 0) return 12;                 // a crc was computed
    if (!e.crc_ok()) return 13;                // untouched payload verifies
    e.payload[0] = 'X';                        // corrupt in transit
    if (e.crc_ok()) return 14;                 // must now fail
''')
    assert r.returncode == 0, r.stdout + r.stderr


def test_crc_differs_by_payload(tmp_path):
    r = _run_case(tmp_path, "crc_differs", '''
    using namespace harpia::delivery;
    Envelope a = Envelope::stamp(1, "alpha");
    Envelope b = Envelope::stamp(1, "bravo");
    if (a.crc == b.crc) return 20;
    Envelope a2 = Envelope::stamp(9, "alpha");   // same bytes, different seq
    if (a.crc != a2.crc) return 21;             // crc is over payload only
''')
    assert r.returncode == 0, r.stdout + r.stderr


def test_check_on_arrival_outcomes(tmp_path):
    r = _run_case(tmp_path, "arrival", '''
    using namespace harpia::delivery;
    Envelope e = Envelope::stamp(5, "p");
    if (check_on_arrival(e, 5) != Arrival::Ok) return 30;
    if (check_on_arrival(e, 4) != Arrival::SeqGap) return 31;        // expected 4, got 5
    if (check_on_arrival(e, 6) != Arrival::SeqRegressed) return 32;  // expected 6, got 5
    Envelope bad = Envelope::stamp(5, "p");
    bad.payload = "tampered";
    if (check_on_arrival(bad, 5) != Arrival::CrcMismatch) return 33; // crc checked first
''')
    assert r.returncode == 0, r.stdout + r.stderr


# -- Rule 4a: BoundedQueue -------------------------------------------------

def test_bounded_queue_fifo_within_capacity(tmp_path):
    r = _run_case(tmp_path, "q_fifo", '''
    using namespace harpia::delivery;
    CountingSink sink;
    BoundedQueue q(4, sink);
    for (std::uint64_t i = 1; i <= 3; ++i)
        if (q.push(Envelope::stamp(i, "m" + std::to_string(i))) != PushOutcome::Accepted)
            return 40;
    if (q.size() != 3) return 41;
    for (std::uint64_t i = 1; i <= 3; ++i) {
        auto e = q.pop();
        if (!e || e->seq != i) return 42;      // oldest-first
    }
    if (q.pop().has_value()) return 43;        // drained -> nullopt
    if (q.rotations() != 0) return 44;
    if (sink.calls.count("queue_rotated")) return 45;  // nothing rotated
''')
    assert r.returncode == 0, r.stdout + r.stderr


def test_bounded_queue_overflow_rotates_oldest_and_audits(tmp_path):
    r = _run_case(tmp_path, "q_rotate", '''
    using namespace harpia::delivery;
    CountingSink sink;
    BoundedQueue q(3, sink);
    q.push(Envelope::stamp(1, "a"));
    q.push(Envelope::stamp(2, "b"));
    q.push(Envelope::stamp(3, "c"));
    if (q.size() != 3) return 50;
    PushOutcome o = q.push(Envelope::stamp(4, "d"));   // full -> rotate
    if (o != PushOutcome::RotatedOldest) return 51;
    if (q.size() != 3) return 52;                      // never grows
    if (q.rotations() != 1) return 53;
    if (q.last_rotated_seq() != 1) return 54;          // seq 1 was the oldest
    if (sink.calls["queue_rotated"] != 1) return 55;   // audited, not silent
    if (sink.last_detail != "dropped_seq=1") return 56;
    // survivors are 2,3,4 in order
    std::uint64_t expect[3] = {2, 3, 4};
    for (int i = 0; i < 3; ++i) {
        auto e = q.pop();
        if (!e || e->seq != expect[i]) return 57;
    }
''')
    assert r.returncode == 0, r.stdout + r.stderr


def test_bounded_queue_peek_is_nondestructive_and_ordered(tmp_path):
    r = _run_case(tmp_path, "q_peek", '''
    using namespace harpia::delivery;
    CountingSink sink;
    BoundedQueue q(4, sink);
    if (q.peek() != nullptr) return 63;                // empty -> nullptr
    q.push(Envelope::stamp(1, "a"));
    q.push(Envelope::stamp(2, "b"));
    const Envelope* p1 = q.peek();
    if (!p1 || p1->seq != 1) return 64;                // oldest, not newest
    if (q.size() != 2) return 65;                      // peek did not consume
    if (q.peek()->seq != 1) return 66;                 // still there, stable
    q.pop();
    if (q.peek()->seq != 2) return 67;                 // advances after pop
''')
    assert r.returncode == 0, r.stdout + r.stderr


def test_bounded_queue_zero_capacity_clamped_to_one(tmp_path):
    r = _run_case(tmp_path, "q_zero", '''
    using namespace harpia::delivery;
    CountingSink sink;
    BoundedQueue q(0, sink);
    if (q.capacity() != 1) return 60;
    q.push(Envelope::stamp(1, "a"));
    if (q.push(Envelope::stamp(2, "b")) != PushOutcome::RotatedOldest) return 61;
    auto e = q.pop();
    if (!e || e->seq != 2) return 62;
''')
    assert r.returncode == 0, r.stdout + r.stderr


# -- Rule 4b: Mailbox ---------------------------------------------------------

def test_mailbox_stores_then_overwrites_and_audits(tmp_path):
    r = _run_case(tmp_path, "mbox", '''
    using namespace harpia::delivery;
    CountingSink sink;
    Mailbox mb(sink);
    if (mb.has_pending()) return 70;
    if (mb.put(Envelope::stamp(1, "old")) != PutOutcome::Stored) return 71;
    if (!mb.has_pending()) return 72;
    if (mb.put(Envelope::stamp(2, "new")) != PutOutcome::Overwrote) return 73;
    if (mb.overwrites() != 1) return 74;
    if (mb.last_overwritten_seq() != 1) return 75;
    if (sink.calls["mailbox_overwritten"] != 1) return 76;
    if (sink.last_detail != "superseded_seq=1") return 77;
    auto e = mb.take();
    if (!e || e->seq != 2 || e->payload != "new") return 78;   // latest wins
    if (mb.has_pending()) return 79;
    if (mb.take().has_value()) return 80;                       // empty -> nullopt
''')
    assert r.returncode == 0, r.stdout + r.stderr


# -- Phase 3c rehearsal: a stall overruns the queue, drain replays in order --

def test_stall_then_drain_replays_critical_survivors_in_order(tmp_path):
    r = _run_case(tmp_path, "stall", '''
    using namespace harpia::delivery;
    CountingSink sink;
    // capacity sized to the workload, not arbitrarily deep (Rule 4a).
    BoundedQueue q(5, sink);

    // --- transport is "stalled": 8 critical samples produced, none sent ---
    int rotated = 0;
    for (std::uint64_t i = 1; i <= 8; ++i)
        if (q.push(Envelope::stamp(i, "sample" + std::to_string(i)))
                == PushOutcome::RotatedOldest)
            ++rotated;
    if (rotated != 3) return 90;                       // seq 1,2,3 rotated out
    if (q.rotations() != 3) return 91;
    if (sink.calls["queue_rotated"] != 3) return 92;   // every loss audited

    // --- "reconnect": drain. Survivors 4..8, in order, crc intact ---------
    std::uint64_t expected = 4;
    while (auto e = q.pop()) {
        if (check_on_arrival(*e, expected) != Arrival::Ok) return 93;
        ++expected;
    }
    if (expected != 9) return 94;                      // saw exactly 4,5,6,7,8
''')
    assert r.returncode == 0, r.stdout + r.stderr


# -- header sanity ---------------------------------------------------------

def test_runtime_header_file_exists():
    assert os.path.isfile(DELIVERY_RUNTIME_SRC)
    assert DELIVERY_RUNTIME_SRC.endswith("harpia_delivery.h")


def test_default_audit_sink_used_when_none_passed(tmp_path):
    # BoundedQueue / Mailbox default their AuditSink& to the shared no-op
    # instance, so an untagged/simple project uses them without wiring audit.
    r = _run_case(tmp_path, "default_sink", '''
    using namespace harpia::delivery;
    BoundedQueue q(2);
    q.push(Envelope::stamp(1, "a"));
    q.push(Envelope::stamp(2, "b"));
    if (q.push(Envelope::stamp(3, "c")) != PushOutcome::RotatedOldest) return 100;
    Mailbox mb;
    mb.put(Envelope::stamp(1, "x"));
    if (mb.put(Envelope::stamp(2, "y")) != PutOutcome::Overwrote) return 101;
''')
    assert r.returncode == 0, r.stdout + r.stderr
