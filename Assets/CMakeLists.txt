cmake_minimum_required(VERSION 3.13)
project(example-grpc LANGUAGES CXX)

set(CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
set(CMAKE_CXX_STANDARD 17)

# CURVE encryption (encryption-only: no ZAP client-key allowlist) for the ZMQ
# demo. Off by default so the plain demo build is unchanged. No CLI keygen
# tool ships with apt's libzmq3-dev, so cmake/curve_keygen_probe.cpp is
# compiled and run here (try_run, configure-time) to produce a fresh
# ephemeral keypair per side every configure -- same "ephemeral, ungitignored
# build dir" shape as the TLS self-signed cert in examples/consumer. Runs
# once at the root (not per-subdirectory) so server/ and client/ share the
# same keypairs via CACHE INTERNAL variables regardless of add_subdirectory
# order.
option(USE_ZMQ_CURVE "Enable CURVE encryption on the ZMQ demo (encryption-only, no ZAP allowlist)" OFF)
if(USE_ZMQ_CURVE)
    if(WIN32)
        # vcpkg's zeromq CONFIG package exports target `libzmq` (see
        # Assets/vcpkg.json's curve+sodium features) -- apt's plain
        # find_library("zmq") equivalent doesn't resolve on the vcpkg layout,
        # same gotcha server_template/client_template's CMakeLists already
        # document for the demo targets themselves.
        find_package(ZeroMQ CONFIG REQUIRED)
        set(HARPIA_CURVE_PROBE_LIBS libzmq)
        set(HARPIA_CURVE_PROBE_INCLUDES "${ZeroMQ_INCLUDE_DIR}")
    else()
        find_library(HARPIA_ZMQ_LIB NAMES zmq)
        if(NOT HARPIA_ZMQ_LIB)
            message(FATAL_ERROR "USE_ZMQ_CURVE: libzmq not found")
        endif()
        set(HARPIA_CURVE_PROBE_LIBS "${HARPIA_ZMQ_LIB}")
        set(HARPIA_CURVE_PROBE_INCLUDES "")
    endif()

    try_run(HARPIA_CURVE_KEYGEN_RUN_RESULT HARPIA_CURVE_KEYGEN_COMPILE_RESULT
        "${CMAKE_BINARY_DIR}/curve_keygen_probe"
        "${CMAKE_CURRENT_SOURCE_DIR}/cmake/curve_keygen_probe.cpp"
        CMAKE_FLAGS
            "-DINCLUDE_DIRECTORIES=${HARPIA_CURVE_PROBE_INCLUDES}"
            "-DLINK_LIBRARIES=${HARPIA_CURVE_PROBE_LIBS}"
        COMPILE_OUTPUT_VARIABLE HARPIA_CURVE_KEYGEN_COMPILE_LOG
        RUN_OUTPUT_VARIABLE HARPIA_CURVE_KEYGEN_OUTPUT
    )
    if(NOT HARPIA_CURVE_KEYGEN_COMPILE_RESULT)
        message(FATAL_ERROR "USE_ZMQ_CURVE: failed to compile the CURVE keygen probe (is libzmq built with CURVE/libsodium support?):\n${HARPIA_CURVE_KEYGEN_COMPILE_LOG}")
    endif()
    if(NOT HARPIA_CURVE_KEYGEN_RUN_RESULT EQUAL 0)
        message(FATAL_ERROR "USE_ZMQ_CURVE: keygen probe exited non-zero -- libzmq may have been built without CURVE support")
    endif()

    # Probe stdout: line 1 "<server_pub> <server_sec>", line 2 "<client_pub> <client_sec>"
    string(REGEX MATCH "^([^ \n]+) ([^ \n]+)\n([^ \n]+) ([^ \n]+)" _ "${HARPIA_CURVE_KEYGEN_OUTPUT}")
    set(HARPIA_ZMQ_CURVE_SERVER_PUBLIC "${CMAKE_MATCH_1}")
    set(HARPIA_ZMQ_CURVE_SERVER_SECRET "${CMAKE_MATCH_2}")
    set(HARPIA_ZMQ_CURVE_CLIENT_PUBLIC "${CMAKE_MATCH_3}")
    set(HARPIA_ZMQ_CURVE_CLIENT_SECRET "${CMAKE_MATCH_4}")
    if(HARPIA_ZMQ_CURVE_SERVER_PUBLIC STREQUAL "")
        message(FATAL_ERROR "USE_ZMQ_CURVE: could not parse keypairs from probe output: ${HARPIA_CURVE_KEYGEN_OUTPUT}")
    endif()

    # Z85 keys can contain characters that are hostile to a build-system
    # command line (Make treats '#' as a comment, '$' as a variable
    # reference, etc.) -- passing them through target_compile_definitions
    # round-trips them through exactly that layer and silently corrupts them.
    # Write a generated header instead: CMake writes the file content
    # directly, no shell/Make parsing involved. Z85's alphabet has no '"',
    # '\\' or newline, so plain double-quoting is safe for the C++ literal.
    set(HARPIA_ZMQ_CURVE_KEYS_HEADER "${CMAKE_BINARY_DIR}/harpia_zmq_curve_keys.h")
    file(WRITE "${HARPIA_ZMQ_CURVE_KEYS_HEADER}" "\
#pragma once
// Generated at configure time by USE_ZMQ_CURVE -- ephemeral, not for reuse.
inline constexpr char kHarpiaZmqCurveServerPublic[] = \"${HARPIA_ZMQ_CURVE_SERVER_PUBLIC}\";
inline constexpr char kHarpiaZmqCurveServerSecret[] = \"${HARPIA_ZMQ_CURVE_SERVER_SECRET}\";
inline constexpr char kHarpiaZmqCurveClientPublic[] = \"${HARPIA_ZMQ_CURVE_CLIENT_PUBLIC}\";
inline constexpr char kHarpiaZmqCurveClientSecret[] = \"${HARPIA_ZMQ_CURVE_CLIENT_SECRET}\";
")
    message(STATUS "USE_ZMQ_CURVE: generated ephemeral CURVE keypairs for the ZMQ demo (${HARPIA_ZMQ_CURVE_KEYS_HEADER})")
endif()

add_subdirectory(client)
add_subdirectory(server)
add_subdirectory(proto)

# Generated unit tests (Stage 14). Opt-in so the default demo build is unchanged:
#   cmake -S . -B build -DHARPIA_BUILD_TESTS=ON && cmake --build build && ctest
option(HARPIA_BUILD_TESTS "Build the generated unit tests" OFF)
if(HARPIA_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
