// Publisher half of the PUB/SUB fan-out worked example (transport-
// multipeer-coverage task 6). Binds once, ticks `pump_tick` messages at a
// human-watchable pace so any number of `subscriber` copies -- launched
// before or after this process, ZMQ's tcp:// transport retries a connect
// lazily until the peer exists -- can watch the stream.
//
//   ./publisher [endpoint] [count]
//     endpoint  default tcp://127.0.0.1:5561
//     count     default 20 (~6s of ticks at the 300ms pace below)
//
// A subscriber that connects only after some ticks have already gone out
// misses those (the classic ZMQ PUB/SUB "slow joiner" -- see
// ZmqAdapter/CLAUDE.md and UnitTests/test_zmq_pubsub_fanout.py, which
// makes exactly this behavior an explicit, asserted fact); it picks up
// every tick sent from the moment its subscription propagates onward.
#include "zmq/pump_tick_3ac5d8b36fc7dcfb70888145147ddfb7_zmq.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>

int main(int argc, char** argv) {
    std::string endpoint = argc > 1 ? argv[1] : "tcp://127.0.0.1:5561";
    int count = argc > 2 ? std::atoi(argv[2]) : 20;

    ::zmq::context_t ctx{1};
    harpia::zmq_transport::pump_tick_publisher pub(ctx, endpoint);
    std::printf("publisher: bound to %s, sending %d ticks\n", endpoint.c_str(), count);
    std::fflush(stdout);
    // A subscriber launched right before this process needs a moment for
    // its (lazily-retried, if the endpoint didn't exist yet) tcp:// connect
    // and subscription to actually reach this socket -- without this, the
    // very first tick can beat that handshake even though "launch order
    // doesn't matter" is the whole point of this demo.
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    for (int i = 1; i <= count; ++i) {
        ::pump_tick m;
        m.set_sequence(i);
        m.set_rate_mhz(1000 + i);
        pub.publish(m);
        std::printf("publisher: sent sequence=%d\n", i);
        std::fflush(stdout);
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
    }
    std::printf("publisher: done\n");
    return 0;
}
