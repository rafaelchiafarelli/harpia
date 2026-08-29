"""events-callbacks epic, task 1 -- `event[cached/not-cached]` implementation.

Two halves, same split as test_zmq_critical_delivery.py + test_audit_sink.py:

  - Structural (pure Python, always run): drive the real pipeline
    (UnitTests/run_pipeline.py) and inspect the parsed model + the emitted
    events/ channel headers + the CRUDL publish wiring.
  - Runtime (g++-gated): compile & run a small standalone program against
    Callback/runtime/harpia_event_cache.h, proving the cached vs not-cached
    delivery semantics.

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


def _compile_and_run(tmp_path, cpp_source):
    src = tmp_path / "ec.cpp"
    src.write_text(cpp_source, encoding="utf-8")
    binp = tmp_path / "ec"
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", os.path.dirname(EVENT_CACHE_RUNTIME_SRC),
         str(src), "-o", str(binp)],
        capture_output=True, text=True)
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    r = subprocess.run([str(binp)], capture_output=True, text=True)
    assert r.returncode == 0, "run failed:\n" + r.stdout + r.stderr
    return r


def test_runtime_header_file_exists():
    assert os.path.isfile(EVENT_CACHE_RUNTIME_SRC)
    assert EVENT_CACHE_RUNTIME_SRC.endswith("harpia_event_cache.h")


@_g
def test_cached_late_subscriber_gets_the_last_value_immediately(tmp_path):
    _compile_and_run(tmp_path, r'''
#include "harpia_event_cache.h"
#include <cassert>
using harpia::events::EventChannel;
using harpia::events::CacheMode;
int main() {
    EventChannel<int> c(CacheMode::Cached);
    c.publish(11);                       // publish BEFORE anyone subscribes
    int got = 0, calls = 0;
    c.subscribe([&](const int& v){ got = v; ++calls; });
    assert(calls == 1 && got == 11);     // fired immediately with last value
    c.publish(22);
    assert(calls == 2 && got == 22);
    assert(c.cached() && c.has_last());
    return 0;
}
''')


@_g
def test_not_cached_late_subscriber_gets_nothing_until_next_publish(tmp_path):
    _compile_and_run(tmp_path, r'''
#include "harpia_event_cache.h"
#include <cassert>
#include <string>
using harpia::events::EventChannel;
using harpia::events::CacheMode;
int main() {
    EventChannel<std::string> n(CacheMode::NotCached);
    n.publish("first");                  // retained by nothing
    int calls = 0; std::string last;
    n.subscribe([&](const std::string& s){ ++calls; last = s; });
    assert(calls == 0);                  // late subscriber gets nothing
    n.publish("second");
    assert(calls == 1 && last == "second");
    assert(!n.cached() && !n.has_last());
    return 0;
}
''')


@_g
def test_subscribers_fire_in_order_and_unsubscribe_stops_delivery(tmp_path):
    _compile_and_run(tmp_path, r'''
#include "harpia_event_cache.h"
#include <cassert>
#include <vector>
using harpia::events::EventChannel;
using harpia::events::CacheMode;
int main() {
    EventChannel<int> c(CacheMode::NotCached);
    std::vector<int> order;
    c.subscribe([&](const int&){ order.push_back(1); });
    auto b = c.subscribe([&](const int&){ order.push_back(2); });
    c.subscribe([&](const int&){ order.push_back(3); });
    c.publish(0);
    assert((order == std::vector<int>{1, 2, 3}));   // subscription order
    c.unsubscribe(b);
    order.clear();
    c.publish(0);
    assert((order == std::vector<int>{1, 3}));      // b no longer delivered
    return 0;
}
''')
