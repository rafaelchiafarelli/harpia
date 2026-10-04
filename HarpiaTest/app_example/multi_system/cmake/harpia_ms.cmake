# Shared by station/ and edge/ (multi-system-reference / reference-system).
#
# Inputs: -DHARPIA_GEN=<a project generated from ../harpia/multi_system.harpia>.
# Gives:
#   HARPIA_MS_HASH     the schema hash every generated file name carries
#                      (read off the generated reading_<hash>.proto, so no
#                      program source hard-codes it)
#   HARPIA_MS_DIALECT  "sqlite" | "postgresql" -- which HARPIA_DB_BACKEND the
#                      project was generated for (its migrations are dialect-
#                      specific)
#   harpia_ms_protos   static library: the message + gRPC service classes
#   harpia_ms_shim(<template.in> <out.h>)  renders a shim header with the hash
if(NOT DEFINED HARPIA_GEN)
    message(FATAL_ERROR
        "Set -DHARPIA_GEN=<path to a project generated from "
        "HarpiaTest/app_example/multi_system/harpia/multi_system.harpia>.")
endif()
set(GEN "${HARPIA_GEN}/generated/cpp")
set(HARPIA_MS_PROTO_DIR "${HARPIA_GEN}/proto/protofiles")

file(GLOB _ms_reading "${HARPIA_MS_PROTO_DIR}/reading_*.proto")
list(FILTER _ms_reading EXCLUDE REGEX "_service\\.proto$")
list(LENGTH _ms_reading _ms_n)
if(NOT _ms_n EQUAL 1)
    message(FATAL_ERROR "expected exactly one reading_<hash>.proto in ${HARPIA_MS_PROTO_DIR} "
        "-- is HARPIA_GEN generated from multi_system.harpia?")
endif()
string(REGEX MATCH "reading_([0-9a-f]+)\\.proto$" _ms_m "${_ms_reading}")
set(HARPIA_MS_HASH "${CMAKE_MATCH_1}")

set(_ms_migrate "${GEN}/migrate/reading_${HARPIA_MS_HASH}_migrate.h")
if(EXISTS "${_ms_migrate}")
    file(READ "${_ms_migrate}" _ms_migrate_text)
    if(_ms_migrate_text MATCHES "sqlite_master")
        set(HARPIA_MS_DIALECT "sqlite")
    else()
        set(HARPIA_MS_DIALECT "postgresql")
    endif()
else()
    set(HARPIA_MS_DIALECT "none")
endif()
message(STATUS "multi_system: schema hash ${HARPIA_MS_HASH}, DB dialect ${HARPIA_MS_DIALECT}")

find_package(Threads REQUIRED)
find_package(Protobuf REQUIRED)

set(_ms_protos
    errorCode heartBeat
    reading_${HARPIA_MS_HASH} field_note_${HARPIA_MS_HASH} live_sample_${HARPIA_MS_HASH}
    reading_${HARPIA_MS_HASH}_service field_note_${HARPIA_MS_HASH}_service)

if(WIN32)
    # The Docker-baked *.pb.cc are for apt's (old) protobuf/gRPC; regenerate
    # from the raw .proto with vcpkg's own protoc + grpc plugin, the same way
    # HarpiaTest/app_example/consumer does for messages.
    find_package(gRPC CONFIG REQUIRED)
    set(_ms_files "")
    foreach(p ${_ms_protos})
        list(APPEND _ms_files "${HARPIA_MS_PROTO_DIR}/${p}.proto")
    endforeach()
    add_library(harpia_ms_protos STATIC)
    protobuf_generate(TARGET harpia_ms_protos LANGUAGE cpp
        IMPORT_DIRS "${HARPIA_GEN}/proto" PROTOC_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}"
        PROTOS ${_ms_files})
    set(_ms_services
        "${HARPIA_MS_PROTO_DIR}/reading_${HARPIA_MS_HASH}_service.proto"
        "${HARPIA_MS_PROTO_DIR}/field_note_${HARPIA_MS_HASH}_service.proto")
    protobuf_generate(TARGET harpia_ms_protos LANGUAGE grpc
        GENERATE_EXTENSIONS .grpc.pb.h .grpc.pb.cc
        PLUGIN "protoc-gen-grpc=\$<TARGET_FILE:gRPC::grpc_cpp_plugin>"
        IMPORT_DIRS "${HARPIA_GEN}/proto" PROTOC_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}"
        PROTOS ${_ms_services})
    target_include_directories(harpia_ms_protos PUBLIC "${CMAKE_CURRENT_BINARY_DIR}")
    target_link_libraries(harpia_ms_protos PUBLIC protobuf::libprotobuf gRPC::grpc++)
else()
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(GRPCPP REQUIRED IMPORTED_TARGET grpc++)
    set(_ms_srcs "")
    foreach(p ${_ms_protos})
        list(APPEND _ms_srcs "${GEN}/protofiles/${p}.pb.cc")
    endforeach()
    list(APPEND _ms_srcs
        "${GEN}/protofiles/reading_${HARPIA_MS_HASH}_service.grpc.pb.cc"
        "${GEN}/protofiles/field_note_${HARPIA_MS_HASH}_service.grpc.pb.cc")
    add_library(harpia_ms_protos STATIC ${_ms_srcs})
    target_include_directories(harpia_ms_protos PUBLIC "${GEN}")
    target_link_libraries(harpia_ms_protos PUBLIC protobuf::libprotobuf PkgConfig::GRPCPP)
endif()

function(harpia_ms_shim template out)
    set(HARPIA_MS_HASH "${HARPIA_MS_HASH}")
    set(HARPIA_MS_DIALECT "${HARPIA_MS_DIALECT}")
    configure_file("${template}" "${out}" @ONLY)
endfunction()
