# Reproducible build/test toolchain for harpia.
#
# Everything the pipeline needs to go from .harpia -> .proto -> compilable C++
# lives in this image, so nothing has to be installed on the host:
#   - Python 3.12 (Ubuntu 24.04 default) + pytest      : run the pipeline & golden tests
#   - protobuf-compiler (protoc) + libprotobuf-dev     : Stage 7, .proto -> C++
#   - protobuf-compiler-grpc + libgrpc++-dev           : gRPC stubs (later stages)
#   - cmake, g++, make                                 : compile the generated C++
#
# The repository is mounted at /harpia at run time (see docker/run.sh), so edits
# on the host are picked up without rebuilding the image.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pytest \
        protobuf-compiler \
        libprotobuf-dev \
        protobuf-compiler-grpc \
        libgrpc++-dev \
        cmake \
        g++ \
        make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /harpia

CMD ["bash"]
