# edge -- the reference system's Linux program (C++, no database). Consumes a
# harpia-generated project as a black box:
#
#   cmake -S HarpiaTest/app_example/multi_system/edge -B build/edge -DHARPIA_GEN=<gen>
#   cmake --build build/edge
#
# Links protobuf + gRPC + libzmq only: edge must never link a database
# library (checked by UnitTests/test_multi_system_example.py with ldd).
cmake_minimum_required(VERSION 3.16)
project(harpia_ms_edge CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/harpia_ms.cmake")
harpia_ms_shim("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/harpia_ms_client.h.in"
               "${CMAKE_CURRENT_BINARY_DIR}/shim/harpia_ms_client.h")

add_executable(edge edge.cpp)
target_include_directories(edge PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/shim")
if(WIN32)
    target_include_directories(edge PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${GEN}")
    target_compile_definitions(edge PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
    find_package(cppzmq CONFIG REQUIRED)
    target_link_libraries(edge PRIVATE harpia_ms_protos cppzmq Threads::Threads)
else()
    target_include_directories(edge PRIVATE "${GEN}")
    target_link_libraries(edge PRIVATE harpia_ms_protos zmq Threads::Threads)
endif()
