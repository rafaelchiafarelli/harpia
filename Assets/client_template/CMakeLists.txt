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
target_include_directories(client PRIVATE ${CMAKE_SOURCE_DIR}/generated/cpp)
target_link_libraries(client
    PRIVATE
        protofiles
        zmq
)
