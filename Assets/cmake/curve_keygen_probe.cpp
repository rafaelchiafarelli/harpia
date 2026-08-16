// Configure-time helper for -DUSE_ZMQ_CURVE=ON, run via CMake's try_run
// (see Assets/CMakeLists.txt). Prints one ephemeral CURVE keypair per line
// (server, then client) as "PUBLIC SECRET", Z85-encoded (zmq_curve_keypair's
// native output -- cppzmq's curve_* sockopts accept Z85 text directly, no
// binary decode step needed). Not part of the generated project itself.
#include <cstdio>
#include <zmq.h>

static int print_keypair() {
    char pub[41];
    char sec[41];
    if (zmq_curve_keypair(pub, sec) != 0) {
        return 1;
    }
    std::printf("%s %s\n", pub, sec);
    return 0;
}

int main() {
    // Line 1: server keypair. Line 2: client keypair.
    if (print_keypair() != 0) return 1;
    if (print_keypair() != 0) return 1;
    return 0;
}
