// Pusher half of the PUSH/PULL load-balance worked example (transport-
// multipeer-coverage task 6). Unlike `subscriber` above, a PUSH socket only
// round-robins across peers it has actually connect()ed to -- ZMQ has no
// discovery mechanism of its own -- so every `worker` copy's own bind
// endpoint must be listed here explicitly.
//
//   ./pusher <worker_endpoint>... [--count N]
//     at least one worker endpoint required, e.g.:
//       ./pusher tcp://127.0.0.1:5571 tcp://127.0.0.1:5572 tcp://127.0.0.1:5573
//     count  default 20 (~6s of items at the 300ms pace below)
#include "zmq/courier_3ac5d8b36fc7dcfb70888145147ddfb7_zmq.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

int main(int argc, char** argv) {
    std::vector<std::string> endpoints;
    int count = 20;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
            count = std::atoi(argv[++i]);
        } else {
            endpoints.push_back(argv[i]);
        }
    }
    if (endpoints.empty()) {
        std::fprintf(stderr, "usage: pusher <worker_endpoint>... [--count N]\n");
        return 100;
    }

    ::zmq::context_t ctx{1};
    harpia::zmq_transport::courier_sender snd(ctx, endpoints[0]);
    for (std::size_t i = 1; i < endpoints.size(); ++i) {
        snd.socket().connect(endpoints[i]);
    }
    std::printf("pusher: connected to %zu worker(s), sending %d items\n",
               endpoints.size(), count);
    std::fflush(stdout);

    for (int i = 1; i <= count; ++i) {
        ::courier m;
        m.set_payload("seq-" + std::to_string(i));
        snd.send(m);
        std::printf("pusher: sent seq-%d\n", i);
        std::fflush(stdout);
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
    }
    std::printf("pusher: done\n");
    return 0;
}
