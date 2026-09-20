// Worker half of the PUSH/PULL load-balance worked example (transport-
// multipeer-coverage task 6). Each copy needs its OWN endpoint -- a bound
// PULL socket can't share a port with another copy -- so pass it a
// distinct port and list every worker's endpoint on `pusher`'s argv.
// Exits after 10s of silence, so it also works as a bounded, scriptable
// check rather than only an interactive demo.
//
//   ./worker [endpoint]
//     endpoint  default tcp://127.0.0.1:5571
#include "zmq/courier_3ac5d8b36fc7dcfb70888145147ddfb7_zmq.h"
#include <cstdio>
#include <string>

int main(int argc, char** argv) {
    std::string endpoint = argc > 1 ? argv[1] : "tcp://127.0.0.1:5571";

    ::zmq::context_t ctx{1};
    harpia::zmq_transport::courier_receiver rcv(ctx, endpoint);
    rcv.socket().set(::zmq::sockopt::rcvtimeo, 10000);
    std::printf("worker: bound to %s\n", endpoint.c_str());
    std::fflush(stdout);

    for (;;) {
        ::courier in;
        if (!rcv.recv(&in)) {
            std::printf("worker: no work for 10s, exiting\n");
            break;
        }
        std::printf("worker: processed %s\n", in.payload().c_str());
        std::fflush(stdout);
    }
    return 0;
}
