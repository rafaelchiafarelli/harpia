"""transport-multipeer-coverage / zmq-multipeer task 3 -- in-process event
channel, more consumers under load.

`test_events_callbacks.py` already proves `EventChannel<T>` correct at small
scale (3 subscribers, one throwing callback isolated, detached dispatch does
not block `publish()`). This is a sibling module (that file was already
520+ lines, per the task's own "or add a sibling module if that file is
getting crowded") hardening the *scale* dimension only, same runtime
(`Callback/runtime/harpia_event_cache.h`), not new correctness surface:

  - 10+ subscribers on one channel, a 50+ message burst: every subscriber's
    callback fires exactly once per published value, with the right values.
  - One deliberately slow (sleeping) subscriber and one that throws on every
    call, mixed in among well-behaved ones: the well-behaved subscribers are
    unaffected -- no starvation, no missed deliveries, no crash.

Per `harpia_event_cache.h`'s own documented contract, order is preserved
*within* one `publish()` call (one sequential dispatch thread) but NOT
*across* different `publish()` calls (each gets its own detached thread) --
so these tests check delivery counts and the received value SET per
subscriber, not a strict receive order across the whole burst. That is the
actual contract, not a weaker test standing in for a stronger one.

g++-gated, same as `test_events_callbacks.py`'s runtime half; no protoc/pkg-config
needed (`EventChannel<T>` has no socket, this is in-process only):

    Docker/run.sh pytest UnitTests/test_events_callbacks_scale.py
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Callback.callback_common import EVENT_CACHE_RUNTIME_SRC
from Compliance.audit_common import AUDIT_SINK_RUNTIME_SRC

_g = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")

_PROLOGUE = r'''
#include "harpia_event_cache.h"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
using harpia::events::EventChannel;
using harpia::events::CacheMode;

template <class F>
static bool wait_for(F pred, int timeout_ms = 5000) {
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (std::chrono::steady_clock::now() < deadline) {
        if (pred()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return pred();
}
'''

_RUNTIME_INC = [os.path.dirname(EVENT_CACHE_RUNTIME_SRC),
                os.path.dirname(AUDIT_SINK_RUNTIME_SRC)]


def _compile_and_run(tmp_path, body):
    src = tmp_path / "ec_scale.cpp"
    src.write_text(_PROLOGUE + "\nint main() {\n" + body + "\n    return 0;\n}\n",
                   encoding="utf-8")
    binp = tmp_path / "ec_scale"
    inc = []
    for d in _RUNTIME_INC:
        inc += ["-I", d]
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
         *inc, str(src), "-o", str(binp)],
        capture_output=True, text=True)
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    r = subprocess.run([str(binp)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, "run failed:\n" + r.stdout + r.stderr
    return r


@_g
def test_ten_plus_subscribers_burst_publish_every_value_delivered(tmp_path):
    _compile_and_run(tmp_path, r'''
    constexpr int kSubs = 12;
    constexpr int kN = 60;
    EventChannel<int> c(CacheMode::NotCached);

    std::mutex locks[kSubs];
    std::vector<int> received[kSubs];
    std::atomic<int> counts[kSubs];
    for (int i = 0; i < kSubs; ++i) counts[i] = 0;

    for (int i = 0; i < kSubs; ++i) {
        c.subscribe([&, i](const int& v) {
            std::lock_guard<std::mutex> lk(locks[i]);
            received[i].push_back(v);
            ++counts[i];
        });
    }

    for (int v = 0; v < kN; ++v) c.publish(v);

    for (int i = 0; i < kSubs; ++i) {
        assert(wait_for([&, i] { return counts[i].load() >= kN; }));
    }
    for (int i = 0; i < kSubs; ++i) {
        std::lock_guard<std::mutex> lk(locks[i]);
        assert((int)received[i].size() == kN);   // exactly once each, no dupes
        std::vector<int> sorted_copy = received[i];
        std::sort(sorted_copy.begin(), sorted_copy.end());
        for (int v = 0; v < kN; ++v) assert(sorted_copy[v] == v);  // right values, none missing
    }
''')


@_g
def test_slow_and_throwing_subscriber_do_not_starve_well_behaved_ones(tmp_path):
    _compile_and_run(tmp_path, r'''
    constexpr int kGood = 10;
    constexpr int kN = 20;
    EventChannel<int> c(CacheMode::NotCached);

    std::mutex locks[kGood];
    std::vector<int> received[kGood];
    std::atomic<int> counts[kGood];
    for (int i = 0; i < kGood; ++i) counts[i] = 0;

    // mixed in among the well-behaved subscribers, not first or last
    for (int i = 0; i < kGood / 2; ++i) {
        c.subscribe([&, i](const int& v) {
            std::lock_guard<std::mutex> lk(locks[i]);
            received[i].push_back(v);
            ++counts[i];
        });
    }
    c.subscribe([](const int&) {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    });
    c.subscribe([](const int&) { throw std::runtime_error("boom"); });
    for (int i = kGood / 2; i < kGood; ++i) {
        c.subscribe([&, i](const int& v) {
            std::lock_guard<std::mutex> lk(locks[i]);
            received[i].push_back(v);
            ++counts[i];
        });
    }

    for (int v = 0; v < kN; ++v) c.publish(v);

    for (int i = 0; i < kGood; ++i) {
        assert(wait_for([&, i] { return counts[i].load() >= kN; }));
    }
    for (int i = 0; i < kGood; ++i) {
        std::lock_guard<std::mutex> lk(locks[i]);
        assert((int)received[i].size() == kN);   // no missed deliveries
        std::vector<int> sorted_copy = received[i];
        std::sort(sorted_copy.begin(), sorted_copy.end());
        for (int v = 0; v < kN; ++v) assert(sorted_copy[v] == v);
    }
    // process reaching here at all is the "no crash" assertion -- a throw
    // escaping the dispatch thread would std::terminate before this point.
''')
