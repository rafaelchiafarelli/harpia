#
# Dependencies
#
find_package(Threads)

#
# Sources
#
set(SOURCES
    src/main.cpp
)

source_group(TREE ${CMAKE_CURRENT_SOURCE_DIR} FILES ${SOURCES})


#
# Target
#
add_executable(client ${SOURCES})
# generated/cpp holds the harpia json/ and zmq/ adapter headers (and the
# protofiles/*.pb.h they include); protofiles provides the compiled message code.
if(WIN32)
    # generated/cpp/protofiles/*.pb.h was baked by the pipeline's Docker protoc
    # (apt's, an old version) and can't compile against whatever much newer
    # protobuf vcpkg installs (Google has removed/moved internal headers like
    # map_field_inl.h across major versions). proto/CMakeLists.txt already
    # regenerates matching .pb.h from the raw .proto via vcpkg's own protoc
    # into ${CMAKE_BINARY_DIR}/proto/protofiles -- list that dir FIRST so the
    # adapter headers' quoted `#include "protofiles/...pb.h"` resolves there
    # instead of the stale baked copy under generated/cpp.
    target_include_directories(client PRIVATE
        ${CMAKE_BINARY_DIR}/proto
        ${CMAKE_SOURCE_DIR}/generated/cpp)

    # vcpkg's zeromq/cppzmq ports export CONFIG packages, not a bare "zmq"
    # lib findable by name the way apt's libzmq3-dev/cppzmq-dev are on Linux.
    find_package(cppzmq CONFIG REQUIRED)
    target_link_libraries(client PRIVATE protofiles cppzmq)

    # zmq.hpp pulls in <windows.h> for socket APIs; without these its full
    # umbrella defines macros (e.g. min/max) that silently break unrelated
    # identifiers elsewhere in the same translation unit -- a classic,
    # well-documented Windows.h pollution gotcha.
    target_compile_definitions(client PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
else()
    target_include_directories(client PRIVATE ${CMAKE_SOURCE_DIR}/generated/cpp)
    target_link_libraries(client
        PRIVATE
            protofiles
            zmq
    )
endif()

# See root CMakeLists.txt for USE_ZMQ_CURVE / the keygen probe. Client
# connects (PUSH) -- CURVE "client" role, needs the server's public key plus
# its own keypair. Key material comes from the generated
# harpia_zmq_curve_keys.h, not a compile definition (Z85 keys can contain
# characters -- '#', '$', ... -- that a build-system command line would
# mangle).
if(USE_ZMQ_CURVE)
    target_compile_definitions(client PRIVATE HARPIA_DEMO_CURVE)
    target_include_directories(client PRIVATE ${CMAKE_BINARY_DIR})
endif()
