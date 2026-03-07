find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)
find_package(Threads)

#
# Protobuf/Grpc source files
#
file(GLOB_RECURSE PROTO_FILES protofiles/*.proto)
#set(PROTO_FILES
#    protofiles/address.proto
#    protofiles/addressbook.proto
#)

#
# Add Library target with protobuf sources
#
add_library(protofiles ${PROTO_FILES})
target_link_libraries(protofiles
    PUBLIC
        protobuf::libprotobuf
        gRPC::grpc
        gRPC::grpc++
)
target_include_directories(protofiles PUBLIC ${CMAKE_CURRENT_BINARY_DIR})

#
# Compile protobuf and grpc files in protofiles target to cpp
#
get_target_property(grpc_cpp_plugin_location gRPC::grpc_cpp_plugin LOCATION)
protobuf_generate(TARGET protofiles LANGUAGE cpp)
protobuf_generate(TARGET protofiles LANGUAGE grpc GENERATE_EXTENSIONS .grpc.pb.h .grpc.pb.cc PLUGIN "protoc-gen-grpc=${grpc_cpp_plugin_location}")
