# A standalone project that consumes Harpia-generated ZMQ transport code as
# a black box -- packages the multi-peer scenarios proven in
# UnitTests/test_zmq_pubsub_fanout.py / test_zmq_pushpull_loadbalance.py as
# actual run-N-copies binaries (transport-multipeer-coverage task 6). It
# does NOT need the Harpia repo -- only a project generated with
# run_harpia.sh, pointed at via -DHARPIA_GEN. See README.md for how to run
# each pair.
cmake_minimum_required(VERSION 3.13)
project(harpia_fanout_example CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED HARPIA_GEN)
    message(FATAL_ERROR
        "Set -DHARPIA_GEN=<path to a harpia-generated project> "
        "(the folder run_harpia.sh wrote, containing generated/ and third_party/).")
endif()
set(GEN "${HARPIA_GEN}/generated/cpp")

find_package(Threads REQUIRED)
find_package(Protobuf REQUIRED)

# pump_tick (event, PUB/SUB fan-out) + courier (push-only, PUSH/PULL
# load-balance) -- the exact same two fixtures tasks 1/2/4/5 already proved
# this scenario against, from HarpiaTest/Include/file3.harpia.
if(WIN32)
    # See HarpiaTest/app_example/consumer/CMakeLists.txt for why: the
    # Docker-baked protoc's *.pb.cc won't compile against vcpkg's much newer
    # protobuf, so regenerate from the raw .proto via vcpkg's own protoc.
    protobuf_generate(
        LANGUAGE cpp
        OUT_VAR HARPIA_FANOUT_MSGS_GENERATED
        IMPORT_DIRS "${HARPIA_GEN}/proto"
        PROTOC_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}"
        PROTOS "${HARPIA_GEN}/proto/protofiles/pump_tick_3ac5d8b36fc7dcfb70888145147ddfb7.proto"
               "${HARPIA_GEN}/proto/protofiles/courier_3ac5d8b36fc7dcfb70888145147ddfb7.proto")
    add_library(harpia_fanout_msgs STATIC ${HARPIA_FANOUT_MSGS_GENERATED})
    target_include_directories(harpia_fanout_msgs PUBLIC ${CMAKE_CURRENT_BINARY_DIR})
    target_link_libraries(harpia_fanout_msgs PUBLIC protobuf::libprotobuf)
    # vcpkg's zeromq/cppzmq ports export CONFIG packages, not a bare "zmq"
    # lib findable by name the way apt's libzmq3-dev/cppzmq-dev are on Linux
    # (same distinction Assets/client_template/CMakeLists.txt makes).
    find_package(cppzmq CONFIG REQUIRED)
else()
    add_library(harpia_fanout_msgs STATIC
        "${GEN}/protofiles/pump_tick_3ac5d8b36fc7dcfb70888145147ddfb7.pb.cc"
        "${GEN}/protofiles/courier_3ac5d8b36fc7dcfb70888145147ddfb7.pb.cc")
    target_include_directories(harpia_fanout_msgs PUBLIC "${GEN}")
    target_link_libraries(harpia_fanout_msgs PUBLIC protobuf::libprotobuf)
endif()

function(harpia_fanout_binary name)
    add_executable(${name} src/${name}.cpp)
    if(WIN32)
        target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_BINARY_DIR} "${GEN}")
        # zmq.hpp pulls in <windows.h> for socket APIs; without these its
        # full umbrella defines macros (e.g. min/max) that silently break
        # unrelated identifiers elsewhere in the same translation unit.
        target_compile_definitions(${name} PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
        target_link_libraries(${name} PRIVATE harpia_fanout_msgs cppzmq Threads::Threads)
    else()
        target_include_directories(${name} PRIVATE "${GEN}")
        target_link_libraries(${name} PRIVATE harpia_fanout_msgs zmq Threads::Threads)
    endif()
endfunction()

harpia_fanout_binary(publisher)
harpia_fanout_binary(subscriber)
harpia_fanout_binary(pusher)
harpia_fanout_binary(worker)
