# dds-transport epic, task 2b -- integration harness for test_dds_demo.py.
#
# Builds the GENERATED per-message DDS transport headers (from a pipeline run
# into a tmp dir, passed as -DHARPIA_GEN=<.../build/generated/cpp>, with the
# .pb.{h,cc} for the two demo messages already protoc'd into
# ${HARPIA_GEN}/protofiles/ by the test) plus a driver that exercises the
# critical vs non-critical QoS profiles under a simulated transient receiver
# gap. Standalone -- nothing in the generator emits this.
cmake_minimum_required(VERSION 3.16)
project(harpia_dds_demo CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED HARPIA_GEN)
  message(FATAL_ERROR "pass -DHARPIA_GEN=<path to build/generated/cpp>")
endif()

find_package(Protobuf REQUIRED)
find_package(CycloneDDS-CXX REQUIRED)

# the shared frame IDL + its scaffolding, shipped by DdsAdapter into dds/
add_subdirectory("${HARPIA_GEN}/dds" "${CMAKE_BINARY_DIR}/dds_gen")

# the generated protobuf sources the *_dds.h headers include
file(GLOB PB_SRCS "${HARPIA_GEN}/protofiles/*.pb.cc")

add_executable(dds_demo dds_demo.cpp ${PB_SRCS})
target_include_directories(dds_demo PRIVATE
  "${HARPIA_GEN}" ${Protobuf_INCLUDE_DIRS})
target_link_libraries(dds_demo PRIVATE
  harpia_dds_transport protobuf::libprotobuf)
