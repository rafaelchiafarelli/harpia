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
