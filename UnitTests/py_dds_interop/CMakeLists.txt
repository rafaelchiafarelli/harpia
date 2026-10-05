# python-target / py-dds -- the C++ peer test_py_dds.py runs against Python
# DDS endpoints. Builds the GENERATED dds/ headers of a Python-target
# generation (-DHARPIA_GEN=<gen>/generated/cpp, whose protofiles/ already
# hold the .pb.{h,cc}) plus a small driver. Standalone -- nothing in the
# generator emits this.
cmake_minimum_required(VERSION 3.16)
project(harpia_py_dds_interop CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED HARPIA_GEN)
  message(FATAL_ERROR "pass -DHARPIA_GEN=<path to generated/cpp>")
endif()

find_package(Protobuf REQUIRED)
find_package(CycloneDDS-CXX REQUIRED)

add_subdirectory("${HARPIA_GEN}/dds" "${CMAKE_BINARY_DIR}/dds_gen")

add_executable(dds_peer dds_peer.cpp
  "${HARPIA_GEN}/protofiles/alarm_event_${HARPIA_HASH}.pb.cc"
  "${HARPIA_GEN}/protofiles/vitals_publication_${HARPIA_HASH}.pb.cc")
target_include_directories(dds_peer PRIVATE "${HARPIA_GEN}" ${Protobuf_INCLUDE_DIRS})
target_link_libraries(dds_peer PRIVATE harpia_dds_transport protobuf::libprotobuf)
