# station -- the reference system's DB server (C++; Windows target, also builds
# on Linux for CI). Consumes a harpia-generated project as a black box:
#
#   cmake -S HarpiaTest/app_example/multi_system/station -B build/station -DHARPIA_GEN=<gen>
#   cmake --build build/station
#
# The project must be generated with the HARPIA_DB_BACKEND matching the
# database station will use (sqlite: SQLite file; postgresql: PostgreSQL) --
# the migrations are dialect-specific. Both SOCI backends are linked when
# available, station refuses a --db of the other dialect at startup.
cmake_minimum_required(VERSION 3.16)
project(harpia_ms_station CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/harpia_ms.cmake")
harpia_ms_shim("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/harpia_ms_server.h.in"
               "${CMAKE_CURRENT_BINARY_DIR}/shim/harpia_ms_server.h")

add_executable(station station.cpp)
target_include_directories(station PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/shim")
if(WIN32)
    target_include_directories(station PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${GEN}")
    target_compile_definitions(station PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX
        HARPIA_MS_WITH_SQLITE HARPIA_MS_WITH_POSTGRESQL)
    # same vcpkg soci-port quirks as HarpiaTest/app_example/consumer
    find_package(unofficial-sqlite3 CONFIG REQUIRED)
    if(NOT TARGET SQLite3::SQLite3)
        add_library(SQLite3::SQLite3 ALIAS unofficial::sqlite3::sqlite3)
    endif()
    find_package(PostgreSQL REQUIRED)
    find_package(SOCI CONFIG REQUIRED)
    target_link_libraries(station PRIVATE harpia_ms_protos SOCI::SOCI Threads::Threads)
else()
    target_include_directories(station PRIVATE "${GEN}")
    set(_station_soci soci_core)
    find_library(SOCI_SQLITE3_LIB soci_sqlite3)
    find_library(SOCI_POSTGRESQL_LIB soci_postgresql)
    if(SOCI_SQLITE3_LIB)
        target_compile_definitions(station PRIVATE HARPIA_MS_WITH_SQLITE)
        list(APPEND _station_soci ${SOCI_SQLITE3_LIB})
    endif()
    if(SOCI_POSTGRESQL_LIB)
        find_package(PostgreSQL QUIET)
        if(PostgreSQL_FOUND)
            target_include_directories(station PRIVATE ${PostgreSQL_INCLUDE_DIRS})
            target_compile_definitions(station PRIVATE HARPIA_MS_WITH_POSTGRESQL)
            list(APPEND _station_soci ${SOCI_POSTGRESQL_LIB})
        endif()
    endif()
    target_link_libraries(station PRIVATE harpia_ms_protos ${_station_soci}
        Threads::Threads ${CMAKE_DL_LIBS})
endif()
