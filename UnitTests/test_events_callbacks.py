"""events-callbacks epic, tasks 1 & 2.

Two halves, same split as test_zmq_critical_delivery.py + test_audit_sink.py:

  - Structural (pure Python, always run): drive the real pipeline
    (UnitTests/run_pipeline.py) and inspect the parsed model + the emitted
    events/ channel headers + the CRUDL publish wiring.  [task 1]
  - Runtime (g++-gated): compile & run a small standalone program against
    Callback/runtime/harpia_event_cache.h -- cached vs not-cached delivery
    [task 1], plus detached-thread dispatch + callback-exception isolation
    [task 2]. Delivery is asynchronous since task 2, so these poll an
    atomic with a bounded deadline instead of asserting inline.

Fixture: HarpiaTest/Include/file3.harpia -- `bed_state` is `event[cached]`,
`pump_tick` is `event[not-cached]`, `alarm_event` is bare `critical event`
(cached, the standard). `beacon_log` is a non-event table message.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

from Callback.callback_common import EVENT_CACHE_RUNTIME, EVENT_CACHE_RUNTIME_SRC


# --------------------------------------------------------------------------
# structural
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_events")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    base = str(out)
    cpp = os.path.join(base, "build", "generated", "cpp")
    return {
        "messages": _read(os.path.join(base, "messages.txt")),
        "events": os.path.join(cpp, "events"),
        "events_snapshot": os.path.join(base, "events"),
        "db": os.path.join(cpp, "db"),
        "proto": os.path.join(base, "proto"),
    }


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _message_line(messages, name):
    for line in messages.splitlines():
        if " name:{} ".format(name) in line:
            return line
    raise AssertionError("no message line for {}".format(name))


def test_cache_mode_parsed_onto_the_model(generated):
    m = generated["messages"]
    assert "event_cache_mode:not-cached" in _message_line(m, "pump_tick")
    assert "event_cache_mode:cached" in _message_line(m, "bed_state")
    # bare `event` == cached, the standard
    assert "event_cache_mode:cached" in _message_line(m, "alarm_event")
    # a non-event message carries no cache mode at all
    assert "event_cache_mode" not in _message_line(m, "beacon_log")


def test_cache_mode_is_flag_only_in_the_proto(generated):
    for name in ("pump_tick", "bed_state"):
        proto = _read(os.path.join(generated["proto"],
                                   "{}_{}.proto".format(name, HASH)))
        for trace in ("cached", "not-cached", "event", "["):
            assert trace not in proto, (
                "{} leaked into {}'s .proto".format(trace, name))


def test_event_channel_headers_emitted_with_the_right_cache_mode(generated):
    d = generated["events"]
    assert os.path.isfile(os.path.join(d, EVENT_CACHE_RUNTIME))

    not_cached = _read(os.path.join(d, "pump_tick_{}_events.h".format(HASH)))
    assert "CacheMode::NotCached" in not_cached
    assert "EventChannel<::pump_tick>& pump_tick_channel()" in not_cached

    for name in ("bed_state", "alarm_event"):
        cached = _read(os.path.join(d, "{}_{}_events.h".format(name, HASH)))
        assert "CacheMode::Cached" in cached
        assert "EventChannel<::{n}>& {n}_channel()".format(n=name) in cached


def test_runtime_header_not_snapshotted(generated):
    # same convention as harpia_xml.h / the capability Dispatcher -- the
    # static runtime lives in the repo, only the per-message wrappers are
    # golden-snapshotted.
    snap = generated["events_snapshot"]
    assert os.path.isdir(snap)
    names = os.listdir(snap)
    assert names, "no event wrappers snapshotted"
    assert EVENT_CACHE_RUNTIME not in names


def test_crudl_dao_fires_publish_on_create_and_update_only(generated):
    # alarm_event is `critical event` + has a table -> its DAO fires.
    h = _read(os.path.join(generated["db"],
                           "alarm_event_{}_crudl.h".format(HASH)))
    assert '#include "events/alarm_event_{}_events.h"'.format(HASH) in h
    publish = "::harpia::events::alarm_event_channel().publish(msg);"
    assert h.count(publish) == 2

    def _body(method):
        start = h.index("bool {}(".format(method))
        end = h.index("catch (const std::exception&)", start)
        return h[start:end]

    assert publish in _body("create")
    assert publish in _body("update")
    assert publish not in _body("read")
    assert publish not in _body("list")
    assert publish not in _body("remove")


def test_non_event_table_message_dao_is_untouched(generated):
    h = _read(os.path.join(generated["db"],
                           "beacon_log_{}_crudl.h".format(HASH)))
    assert "events/" not in h
    assert "_channel().publish(" not in h


def test_callback_adapter_makes_no_events_dir_without_event_messages(tmp_path):
    from Callback.CallbackAdapter import CallbackAdapter

    class _FakeMsg:
        isEnum = False
        access_modifiers = [("PUSH", "push ", 1, 0)]
        name = "plain"
        md5Hash = HASH
        event_cache_mode = None

    dest = str(tmp_path)
    assert CallbackAdapter([_FakeMsg()], dest).Process() is None
    assert not os.path.isdir(os.path.join(dest, "generated", "cpp", "events"))


# --------------------------------------------------------------------------
# runtime (g++-gated)
# --------------------------------------------------------------------------
_g = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")

# Delivery is asynchronous since task 2, so every runtime test polls an
# atomic against a hard deadline instead of asserting right after publish.
_PROLOGUE = r'''
#include "harpia_event_cache.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using harpia::events::EventChannel;
using harpia::events::CacheMode;

template <class F>
static bool wait_for(F pred) {
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (std::chrono::steady_clock::now() < deadline) {
        if (pred()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return pred();
}
inline void settle() {   // inline, not static: unused-in-a-TU must not -Werror
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
}
'''


def _compile_and_run(tmp_path, body):
    src = tmp_path / "ec.cpp"
    src.write_text(_PROLOGUE + "\nint main() {\n" + body + "\n    return 0;\n}\n",
                   encoding="utf-8")
    binp = tmp_path / "ec"
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
         "-I", os.path.dirname(EVENT_CACHE_RUNTIME_SRC),
         str(src), "-o", str(binp)],
        capture_output=True, text=True)
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    r = subprocess.run([str(binp)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, "run failed:\n" + r.stdout + r.stderr
    return r


def test_runtime_header_file_exists():
    assert os.path.isfile(EVENT_CACHE_RUNTIME_SRC)
    assert EVENT_CACHE_RUNTIME_SRC.endswith("harpia_event_cache.h")


@_g
def test_cached_late_subscriber_gets_the_last_value(tmp_path):
    _compile_and_run(tmp_path, r'''
    EventChannel<int> c(CacheMode::Cached);
    c.publish(11);                       // publish BEFORE anyone subscribes
    std::atomic<int> got{0}, calls{0};
    c.subscribe([&](const int& v){ got = v; ++calls; });
    assert(wait_for([&]{ return calls.load() >= 1; }));   // replayed
    assert(got.load() == 11);
    c.publish(22);
    assert(wait_for([&]{ return calls.load() >= 2; }));
    assert(got.load() == 22);
    assert(c.cached() && c.has_last());
''')


@_g
def test_not_cached_late_subscriber_gets_nothing_until_next_publish(tmp_path):
    _compile_and_run(tmp_path, r'''
    EventChannel<std::string> n(CacheMode::NotCached);
    n.publish("first");                  // retained by nothing
    std::atomic<int> calls{0};
    n.subscribe([&](const std::string&){ ++calls; });
    settle();                            // any bogus replay would land here
    assert(calls.load() == 0);           // late subscriber got nothing
    n.publish("second");
    assert(wait_for([&]{ return calls.load() >= 1; }));
    assert(!n.cached() && !n.has_last());
''')


@_g
def test_order_within_one_publish_and_unsubscribe_stops_delivery(tmp_path):
    _compile_and_run(tmp_path, r'''
    EventChannel<int> c(CacheMode::NotCached);
    std::vector<int> order;              // one dispatch thread touches this
    std::atomic<int> fired{0};
    c.subscribe([&](const int&){ order.push_back(1); ++fired; });
    auto b = c.subscribe([&](const int&){ order.push_back(2); ++fired; });
    c.subscribe([&](const int&){ order.push_back(3); ++fired; });
    c.publish(0);
    assert(wait_for([&]{ return fired.load() >= 3; }));
    assert((order == std::vector<int>{1, 2, 3}));   // subscription order
    c.unsubscribe(b);
    order.clear();
    fired = 0;
    c.publish(0);
    assert(wait_for([&]{ return fired.load() >= 2; }));
    settle();                            // a stray 3rd delivery would show
    assert((order == std::vector<int>{1, 3}));
''')


@_g
def test_a_throwing_callback_is_isolated(tmp_path):
    # task 2: an exception inside a callback neither propagates to publish()
    # nor terminates the process, and its siblings still run.
    _compile_and_run(tmp_path, r'''
    EventChannel<int> c(CacheMode::NotCached);
    std::atomic<int> good{0};
    c.subscribe([](const int&){ throw std::runtime_error("boom"); });
    c.subscribe([&](const int&){ ++good; });
    c.publish(0);                        // must not throw on the caller thread
    assert(wait_for([&]{ return good.load() >= 1; }));   // sibling still ran
    c.publish(0);                        // process survived the first throw
    assert(wait_for([&]{ return good.load() >= 2; }));
''')


@_g
def test_publish_is_asynchronous(tmp_path):
    # task 2: publish() returns well before a slow callback finishes.
    _compile_and_run(tmp_path, r'''
    EventChannel<int> c(CacheMode::NotCached);
    std::atomic<bool> done{false};
    c.subscribe([&](const int&){
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        done = true;
    });
    auto t0 = std::chrono::steady_clock::now();
    c.publish(0);
    auto elapsed = std::chrono::steady_clock::now() - t0;
    assert(elapsed < std::chrono::milliseconds(200));   // did not block
    assert(!done.load());                               // still running
    assert(wait_for([&]{ return done.load(); }));       // finishes later
''')


@_g
def test_concurrent_publish_and_subscribe_churn_do_not_crash(tmp_path):
    # task 2: the internal mutex holds up under contention.
    _compile_and_run(tmp_path, r'''
    EventChannel<int> c(CacheMode::NotCached);
    std::atomic<int> delivered{0};
    auto keep = c.subscribe([&](const int&){ ++delivered; });
    (void)keep;
    std::atomic<bool> stop{false};
    std::thread churn([&]{
        while (!stop.load()) {
            auto id = c.subscribe([](const int&){});
            c.unsubscribe(id);
        }
    });
    const int N = 200;
    for (int i = 0; i < N; ++i) c.publish(i);
    stop = true;
    churn.join();
    assert(wait_for([&]{ return delivered.load() >= 1; }));
    int d = delivered.load();
    assert(d >= 1 && d <= N);
''')
