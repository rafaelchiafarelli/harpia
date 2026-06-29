cmake_minimum_required(VERSION 3.13)
project(example-grpc LANGUAGES CXX)

set(CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
set(CMAKE_CXX_STANDARD 17)

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
