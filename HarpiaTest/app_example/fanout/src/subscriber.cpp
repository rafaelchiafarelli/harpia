// Subscriber half of the PUB/SUB fan-out worked example (transport-
// multipeer-coverage task 6). Launch as many copies as you like -- each is
// an independent fan-out peer, every copy receives every tick published
// after its own subscription has propagated (see publisher.cpp's comment
// on the slow-joiner). Exits after 10s of silence, so it also works as a
// bounded, scriptable check rather than only an interactive demo.
//
//   ./subscriber [endpoint]
//     endpoint  default tcp://127.0.0.1:5561, must match `publisher`
#include "zmq/pump_tick_3ac5d8b36fc7dcfb70888145147ddfb7_zmq.h"
#include <cstdio>
#include <string>

int main(int argc, char** argv) {
    std::string endpoint = argc > 1 ? argv[1] : "tcp://127.0.0.1:5561";

    ::zmq::context_t ctx{1};
    harpia::zmq_transport::pump_tick_subscriber sub(ctx, endpoint);
    sub.socket().set(::zmq::sockopt::rcvtimeo, 10000);
    std::printf("subscriber: connected to %s\n", endpoint.c_str());
    std::fflush(stdout);

    for (;;) {
        ::pump_tick in;
        if (!sub.receive(&in)) {
            std::printf("subscriber: no tick for 10s, exiting\n");
            break;
        }
        std::printf("subscriber: received sequence=%d rate_mhz=%d\n",
                    in.sequence(), in.rate_mhz());
        std::fflush(stdout);
    }
    return 0;
}
