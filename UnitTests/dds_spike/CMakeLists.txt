# dds-transport epic, task 2a -- throwaway spike build.
#
# Standalone: nothing in the generator emits this. `test_dds_vendor_spike.py`
# copies this dir to a tmp path, configures + builds it against the Cyclone
# DDS + ddscxx installed in the Docker toolchain image
# (see Docker/Dockerfile / third_party/cyclonedds*/VENDORED.md), and runs the
# resulting binary to confirm a sample crosses a publisher/subscriber pair.
cmake_minimum_required(VERSION 3.16)
project(harpia_dds_spike CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CycloneDDS-CXX REQUIRED)

# idlc + the idlcxx plugin turn VitalsSample.idl into C++ at build time.
idlcxx_generate(TARGET vitals_sample_lib FILES "${CMAKE_CURRENT_SOURCE_DIR}/VitalsSample.idl")

add_executable(dds_pubsub_spike dds_pubsub_spike.cpp)
target_link_libraries(dds_pubsub_spike
  PRIVATE vitals_sample_lib CycloneDDS-CXX::ddscxx)
