# A standalone project that consumes Harpia-generated code.
#
# It does NOT need the Harpia repo -- only a project you generated with
# run_harpia.sh, pointed at via -DHARPIA_GEN:
#
#   # 1. generate a project from your .harpia (SQLite backend shown)
#   ./run_harpia.sh HarpiaTest /tmp/gen --no-build
#   # 2. build this consumer against it
#   cmake -S HarpiaTest/app_example/consumer -B /tmp/consumer_build -DHARPIA_GEN=/tmp/gen
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

# TLS on the REST server (Crow), opt-in -- see USAGE.md "Enabling TLS on
# REST/SOAP/gRPC". Off by default so the plain demo build/run is unchanged.
option(USE_TLS "Build the consumer with Crow SSL enabled" OFF)

# PostgreSQL backend, opt-in -- see USAGE.md §8/§12. Off by default so the
# plain SQLite demo build/run is unchanged; requires HARPIA_GEN to have been
# generated with HARPIA_DB_BACKEND=postgresql (its CRUDL SQL is dialect-
# specific) and, at runtime, HARPIA_PG_CONNINFO pointing at a live server.
option(USE_POSTGRES "Build the consumer against the SOCI PostgreSQL backend instead of SQLite" OFF)

find_package(Threads REQUIRED)
find_package(Protobuf REQUIRED)

# The generated message C++ (protobuf). `users` has no composed fields, so it is
# self-contained; a message that embeds/refers to others would also need those
# <name>_<hash>.pb.cc files here (the generated project's proto/CMakeLists.txt
# shows the full set).
if(WIN32)
    # ${GEN}/protofiles/*.pb.cc was baked by the pipeline's Docker protoc (apt's,
    # an old version) and won't compile against whatever much newer protobuf
    # vcpkg installs (Google has removed/moved internal headers across major
    # versions -- see Assets/server_template/CMakeLists.txt for the same issue
    # on the generated project's own demo). Regenerate from the raw .proto via
    # vcpkg's own protoc instead, same as Assets/proto/CMakeLists.txt does.
    protobuf_generate(
        LANGUAGE cpp
        OUT_VAR HARPIA_MSGS_GENERATED
        IMPORT_DIRS "${HARPIA_GEN}/proto"
        PROTOC_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}"
        PROTOS "${HARPIA_GEN}/proto/protofiles/users_3ac5d8b36fc7dcfb70888145147ddfb7.proto")
    add_library(harpia_msgs STATIC ${HARPIA_MSGS_GENERATED})
    target_include_directories(harpia_msgs PUBLIC ${CMAKE_CURRENT_BINARY_DIR})
    target_link_libraries(harpia_msgs PUBLIC protobuf::libprotobuf)
else()
    add_library(harpia_msgs STATIC
        "${GEN}/protofiles/users_3ac5d8b36fc7dcfb70888145147ddfb7.pb.cc")
    target_include_directories(harpia_msgs PUBLIC "${GEN}")
    target_link_libraries(harpia_msgs PUBLIC protobuf::libprotobuf)
endif()

# tinyxml2 (used by the XML/SOAP paths and REST content-negotiation) is vendored
# inside the generated project.
add_library(harpia_tinyxml2 STATIC
    "${HARPIA_GEN}/third_party/tinyxml2/tinyxml2.cpp")
target_include_directories(harpia_tinyxml2 PUBLIC
    "${HARPIA_GEN}/third_party/tinyxml2")

add_executable(consumer src/main.cpp)
if(WIN32)
    # The db/json/rest headers under ${GEN} quote-include "protofiles/....pb.h"
    # relative to whichever -I root is found first; list the freshly
    # regenerated dir ahead of ${GEN} so that resolves to the vcpkg-compatible
    # copy instead of the stale Docker-baked one (see harpia_msgs above).
    target_include_directories(consumer PRIVATE
        ${CMAKE_CURRENT_BINARY_DIR}
        "${GEN}"
        "${HARPIA_GEN}/third_party/crow"
        "${HARPIA_GEN}/third_party/asio")

    # Crow/asio pull in <windows.h> for socket APIs; without these, its full
    # umbrella (winuser.h etc.) defines macros like GetMessage that silently
    # rewrite any identifier of that name elsewhere in the same translation
    # unit (e.g. protobuf's Reflection::GetMessage()) into GetMessageA/W --
    # a classic, well-documented Windows.h pollution gotcha.
    target_compile_definitions(consumer PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

    # vcpkg's soci port exports a CONFIG package (SOCI::SOCI, linking every
    # installed backend component); apt's soci-dev has no such package, only
    # bare .so names findable by the linker's default search path.
    # SOCI::SQLite3's own link interface references the SQLite3::SQLite3
    # imported target without importing it itself. vcpkg's sqlite3 port has
    # no CONFIG package under that name (only "unofficial-sqlite3", target
    # unofficial::sqlite3::sqlite3) and CMake's builtin MODULE-mode
    # FindSQLite3 doesn't reliably win the search under the vcpkg toolchain,
    # so alias it in by hand -- a known vcpkg soci-port quirk.
    find_package(unofficial-sqlite3 CONFIG REQUIRED)
    if(NOT TARGET SQLite3::SQLite3)
        add_library(SQLite3::SQLite3 ALIAS unofficial::sqlite3::sqlite3)
    endif()
    if(USE_POSTGRES)
        # vcpkg's libpq port has no CONFIG package of its own; it ships a
        # vcpkg-cmake-wrapper.cmake that hooks CMake's builtin MODULE-mode
        # FindPostgreSQL, which defines PostgreSQL::PostgreSQL directly (no
        # "unofficial-" alias needed here, unlike SQLite3 above).
        find_package(PostgreSQL REQUIRED)
    endif()
    find_package(SOCI CONFIG REQUIRED)
    target_link_libraries(consumer PRIVATE
        harpia_msgs harpia_tinyxml2
        SOCI::SOCI
        Threads::Threads ${CMAKE_DL_LIBS})
else()
    target_include_directories(consumer PRIVATE
        "${GEN}"                                  # the generated headers (db/ json/ rest/ ...)
        "${HARPIA_GEN}/third_party/crow"          # Crow (REST/SOAP server) -- vendored, header-only
        "${HARPIA_GEN}/third_party/asio")         # asio (Crow's transport) -- vendored, header-only
    target_link_libraries(consumer PRIVATE
        harpia_msgs harpia_tinyxml2
        soci_core soci_sqlite3                 # SOCI + the SQLite backend (system libs)
        Threads::Threads ${CMAKE_DL_LIBS})
endif()

if(USE_POSTGRES)
    target_compile_definitions(consumer PRIVATE HARPIA_DEMO_POSTGRES)
endif()

if(USE_TLS)
    # Self-signed, ephemeral -- regenerated on every configure, never committed.
    set(HARPIA_DEMO_CERT "${CMAKE_BINARY_DIR}/harpia_demo.crt")
    set(HARPIA_DEMO_KEY "${CMAKE_BINARY_DIR}/harpia_demo.key")

    # On Linux the system `openssl` CLI (apt's openssl package) is on PATH.
    # On Windows there's no system-wide openssl by default; vcpkg's openssl
    # port ships the CLI only under its "tools" feature, not on PATH -- look
    # there too so -DUSE_TLS=ON works out of the box against this project's
    # own vcpkg install.
    find_program(HARPIA_OPENSSL_EXE NAMES openssl
        HINTS "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/tools/openssl"
              "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/debug/tools/openssl")
    if(NOT HARPIA_OPENSSL_EXE)
        message(FATAL_ERROR "openssl CLI not found (checked PATH and this "
            "project's vcpkg tools dir) -- needed to generate the demo TLS cert/key")
    endif()

    # vcpkg's openssl.exe has no system-wide install, so it falls back to a
    # hardcoded default config path (C:\Program Files\Common Files\SSL\
    # openssl.cnf) that doesn't exist there, and fails outright without a
    # config at all -- point it at the copy vcpkg ships next to the binary.
    find_file(HARPIA_OPENSSL_CNF NAMES openssl.cnf
        HINTS "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/tools/openssl"
              "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/debug/tools/openssl")
    set(HARPIA_OPENSSL_ARGS req -x509 -newkey rsa:2048 -nodes
        -keyout "${HARPIA_DEMO_KEY}" -out "${HARPIA_DEMO_CERT}"
        -days 1 -subj "/CN=localhost")
    if(HARPIA_OPENSSL_CNF)
        execute_process(
            COMMAND "${CMAKE_COMMAND}" -E env "OPENSSL_CONF=${HARPIA_OPENSSL_CNF}"
                    "${HARPIA_OPENSSL_EXE}" ${HARPIA_OPENSSL_ARGS}
            RESULT_VARIABLE HARPIA_CERT_RC
            OUTPUT_VARIABLE HARPIA_CERT_OUT ERROR_VARIABLE HARPIA_CERT_OUT)
    else()
        execute_process(
            COMMAND "${HARPIA_OPENSSL_EXE}" ${HARPIA_OPENSSL_ARGS}
            RESULT_VARIABLE HARPIA_CERT_RC
            OUTPUT_VARIABLE HARPIA_CERT_OUT ERROR_VARIABLE HARPIA_CERT_OUT)
    endif()
    if(NOT HARPIA_CERT_RC EQUAL 0)
        message(FATAL_ERROR "openssl failed to generate the demo TLS cert/key: ${HARPIA_CERT_OUT}")
    endif()

    find_package(OpenSSL REQUIRED)
    target_link_libraries(consumer PRIVATE OpenSSL::SSL OpenSSL::Crypto)
    target_compile_definitions(consumer PRIVATE
        CROW_ENABLE_SSL
        HARPIA_DEMO_TLS
        HARPIA_DEMO_CERT="${HARPIA_DEMO_CERT}"
        HARPIA_DEMO_KEY="${HARPIA_DEMO_KEY}")
endif()
