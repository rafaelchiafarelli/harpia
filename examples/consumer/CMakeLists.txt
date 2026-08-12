# A standalone project that consumes Harpia-generated code.
#
# It does NOT need the Harpia repo -- only a project you generated with
# run_harpia.sh, pointed at via -DHARPIA_GEN:
#
#   # 1. generate a project from your .harpia (SQLite backend shown)
#   ./run_harpia.sh HarpiaTest /tmp/gen --no-build
#   # 2. build this consumer against it
#   cmake -S examples/consumer -B /tmp/consumer_build -DHARPIA_GEN=/tmp/gen
#   cmake --build /tmp/consumer_build
#   /tmp/consumer_build/consumer
cmake_minimum_required(VERSION 3.13)
project(harpia_consumer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED HARPIA_GEN)
    message(FATAL_ERROR
        "Set -DHARPIA_GEN=<path to a harpia-generated project> "
        "(the folder run_harpia.sh wrote, containing generated/ and third_party/).")
endif()
set(GEN "${HARPIA_GEN}/generated/cpp")

# TLS on the REST server (Crow), opt-in -- see USAGE.md "Enabling TLS on
# REST/SOAP/gRPC". Off by default so the plain demo build/run is unchanged.
option(USE_TLS "Build the consumer with Crow SSL enabled" OFF)

find_package(Threads REQUIRED)
find_package(Protobuf REQUIRED)

# The generated message C++ (protobuf). `users` has no composed fields, so it is
# self-contained; a message that embeds/refers to others would also need those
# <name>_<hash>.pb.cc files here (the generated project's proto/CMakeLists.txt
# shows the full set).
add_library(harpia_msgs STATIC
    "${GEN}/protofiles/users_c96f8fd7f45108efee5a8ecb43eab1da.pb.cc")
target_include_directories(harpia_msgs PUBLIC "${GEN}")
target_link_libraries(harpia_msgs PUBLIC protobuf::libprotobuf)

# tinyxml2 (used by the XML/SOAP paths and REST content-negotiation) is vendored
# inside the generated project.
add_library(harpia_tinyxml2 STATIC
    "${HARPIA_GEN}/third_party/tinyxml2/tinyxml2.cpp")
target_include_directories(harpia_tinyxml2 PUBLIC
    "${HARPIA_GEN}/third_party/tinyxml2")

add_executable(consumer src/main.cpp)
target_include_directories(consumer PRIVATE
    "${GEN}"                                  # the generated headers (db/ json/ rest/ ...)
    "${HARPIA_GEN}/third_party/crow"          # Crow (REST/SOAP server) -- vendored, header-only
    "${HARPIA_GEN}/third_party/asio")         # asio (Crow's transport) -- vendored, header-only
target_link_libraries(consumer PRIVATE
    harpia_msgs harpia_tinyxml2
    soci_core soci_sqlite3                     # SOCI + the SQLite backend (system libs)
    Threads::Threads ${CMAKE_DL_LIBS})

if(USE_TLS)
    # Self-signed, ephemeral -- regenerated on every configure, never committed.
    set(HARPIA_DEMO_CERT "${CMAKE_BINARY_DIR}/harpia_demo.crt")
    set(HARPIA_DEMO_KEY "${CMAKE_BINARY_DIR}/harpia_demo.key")
    execute_process(COMMAND openssl req -x509 -newkey rsa:2048 -nodes
        -keyout "${HARPIA_DEMO_KEY}" -out "${HARPIA_DEMO_CERT}"
        -days 1 -subj "/CN=localhost"
        RESULT_VARIABLE HARPIA_CERT_RC
        OUTPUT_QUIET ERROR_QUIET)
    if(NOT HARPIA_CERT_RC EQUAL 0)
        message(FATAL_ERROR "openssl failed to generate the demo TLS cert/key")
    endif()

    find_package(OpenSSL REQUIRED)
    target_link_libraries(consumer PRIVATE OpenSSL::SSL OpenSSL::Crypto)
    target_compile_definitions(consumer PRIVATE
        CROW_ENABLE_SSL
        HARPIA_DEMO_TLS
        HARPIA_DEMO_CERT="${HARPIA_DEMO_CERT}"
        HARPIA_DEMO_KEY="${HARPIA_DEMO_KEY}")
endif()
