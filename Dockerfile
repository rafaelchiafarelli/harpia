# Reproducible build/test toolchain for harpia.
#
# Everything the pipeline needs to go from .harpia -> .proto -> compilable C++
# lives in this image, so nothing has to be installed on the host:
#   - Python 3.12 (Ubuntu 24.04 default) + pytest      : run the pipeline & golden tests
#   - python3-yaml                                     : Compliance/context.py's
#                                                      project.harpia.yaml parser (F1)
#   - doxygen                                          : Foundation F6's `doxygen`
#                                                      CMake target (Assets/Doxyfile);
#                                                      doxygen-gated tests skip
#                                                      without it, same as protoc/g++
#   - protobuf-compiler (protoc) + libprotobuf-dev     : Stage 7, .proto -> C++
#   - protobuf-compiler-grpc + libgrpc++-dev           : Stage 13 gRPC stubs
#   - libzmq3-dev + cppzmq-dev                         : Stage 13 ZMQ transport
#   - libsoci-dev + libsoci-sqlite3/postgresql + libpq + libsqlite3-dev
#                                                      : Stage 8 persistence
#       (SOCI is the DB-agnostic access layer the generated DAO is emitted
#        against; sqlite3 backend backs the hermetic tests, postgresql backend
#        the production target. libsqlite3-dev supplies the <sqlite3.h> the SOCI
#        sqlite3 backend header includes — see Database/backends/ +
#        plans/postgres-migration.md)
#   - cmake, g++, make                                 : compile the generated C++
#   - libssl-dev + openssl                              : optional TLS on Crow
#                                                      (REST/SOAP); see
#                                                      examples/consumer -DUSE_TLS=ON
# (Stage 10 XML uses tinyxml2, and Stages 11/12 SOAP+REST use Crow + standalone
#  asio, all vendored in-tree under third_party/ rather than apt — so generated
#  output stays self-contained and cross-compilable on any target board. protobuf,
#  gRPC, ZMQ and SOCI are the heavier libs and come from apt, like on a board.)
#
# The repository is mounted at /harpia at run time (see docker/run.sh), so edits
# on the host are picked up without rebuilding the image.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pytest \
        python3-yaml \
        doxygen \
        protobuf-compiler \
        libprotobuf-dev \
        protobuf-compiler-grpc \
        libgrpc++-dev \
        libzmq3-dev \
        cppzmq-dev \
        libsoci-dev \
        libsoci-sqlite3-4.0 \
        libsoci-postgresql4.0 \
        libpq-dev \
        libsqlite3-dev \
        libboost-dev \
        cmake \
        g++ \
        make \
        libssl-dev \
        openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /harpia

CMD ["bash"]
