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
#   - Eclipse Cyclone DDS + ddscxx (built from source near the end of this
#                                                      file, not apt)
#                                                      : the dds-transport epic's
#                                                      DDS transport (ASTM F2761 /
#                                                      OpenICE-class bedside bus)
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
#                                                      HarpiaTest/app_example/consumer -DUSE_TLS=ON
# (Stage 10 XML uses tinyxml2, and Stages 11/12 SOAP+REST use Crow + standalone
#  asio, all vendored in-tree under third_party/ rather than apt — so generated
#  output stays self-contained and cross-compilable on any target board. protobuf,
#  gRPC, ZMQ and SOCI are the heavier libs and come from apt, like on a board.)
#
#   - openjdk-17-jdk + Gradle 8.5           : Java target (thread-1-java-target)
#                                              build/test toolchain -- matches
#                                              GradleAdapter's `java` plugin
#                                              output and HarpiaTest/app_example/android_consumer's
#                                              AGP 8.2.2 pin (compileOptions
#                                              VERSION_17). Gradle comes from a
#                                              pinned binary distribution, not
#                                              apt's `gradle` package, which on
#                                              Ubuntu 24.04 is a much older 4.x
#                                              line too old for AGP 8.2.2 (needs
#                                              Gradle 8.2+). Unblocks this repo's
#                                              own gradle+JDK-gated tests
#                                              (UnitTests/test_java_*.py,
#                                              UnitTests/_java_gradle_helpers.py),
#                                              previously skipped for lack of a
#                                              JDK in this image.
#   - Android SDK cmdline-tools + platform-tools + platform 34 + build-tools 34.0.0
#                                            : compiles HarpiaTest/app_example/android_consumer
#                                              (compileSdk 34) and runs
#                                              `./gradlew assembleRelease` for
#                                              the R8/DEX-count check
#                                              protobuf-runtime-variant-decision.md
#                                              (J.24) calls for.
#   - Android SDK emulator + system-images;android-34;default;x86_64
#                                            : lets Docker/run_android_emulator_tests.sh
#                                              boot a headless emulator and run the
#                                              three `connectedAndroidTest`s
#                                              (J.25-J.27). Baked in at build time
#                                              (as root, like the rest of the SDK)
#                                              rather than sdkmanager-installed at
#                                              `docker run` time, because
#                                              /opt/android-sdk is root-owned and
#                                              run.sh's containers run as the host
#                                              UID -- only hardware virtualization
#                                              access (/dev/kvm + the kvm group) is
#                                              wired in separately at `docker run`
#                                              time, not the SDK packages.
#
# The repository is mounted at /harpia at run time (see Docker/run.sh), so edits
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
        openjdk-17-jdk \
        unzip \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Gradle 8.5 (AGP 8.2.2 needs Gradle 8.2+; apt's `gradle` on Ubuntu 24.04 is 4.x).
RUN wget -q https://services.gradle.org/distributions/gradle-8.5-bin.zip -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && rm /tmp/gradle.zip
ENV PATH="/opt/gradle-8.5/bin:${PATH}"

# Pre-create Gradle's cache dir with sticky-bit-world-writable perms, same as
# /tmp itself, so it's writable no matter which -u UID a container runs as.
# Docker/run.sh and run_harpia.sh mount a named volume here AND set
# GRADLE_USER_HOME=/tmp/.gradle explicitly -- the JVM's `user.home` property
# is resolved from the OS passwd entry for the current UID (getpwuid), NOT
# from the HOME env var (confirmed: HOME=/tmp but `java
# -XshowSettings:properties` still reports user.home=/home/ubuntu, the base
# image's baked-in UID-1000 passwd entry), so Gradle's default
# ~/.gradle would silently land outside this volume without the explicit
# override. With it, dependency downloads (and, with the Gradle daemon left
# on -- see UnitTests/_java_gradle_helpers.py -- JIT-warmed daemon state) persist
# across separate `docker run --rm` invocations, not just within one.
# Without this, every fresh container starts from a cold Maven Central
# cache -- previously the single biggest cost of running the Java
# gradle+JDK-gated tests even once in a while.
RUN mkdir -p /tmp/.gradle && chmod 1777 /tmp/.gradle

# Android SDK command-line tools -> platform-tools + platform 34 + build-tools
# 34.0.0, matching HarpiaTest/app_example/android_consumer's compileSdk/AGP pin. Licenses
# accepted non-interactively (`yes |`) since this is a throwaway build image,
# not a workstation install.
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME="${ANDROID_SDK_ROOT}"
RUN mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline-tools.zip \
    && unzip -q /tmp/cmdline-tools.zip -d "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && mv "${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools" "${ANDROID_SDK_ROOT}/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip
ENV PATH="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools:${ANDROID_SDK_ROOT}/emulator:${PATH}"
RUN yes | sdkmanager --licenses >/dev/null \
    && sdkmanager --install "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
        "emulator" "system-images;android-34;default;x86_64" >/dev/null

# Eclipse Cyclone DDS + its ddscxx C++ binding -- the ASTM F2761 / OpenICE-class
# bedside-bus transport for the dds-transport epic. Not in Ubuntu 24.04 apt, and
# a full CMake C library with no amalgamation, so (unlike the header-only /
# amalgamated third_party/ libs compiled inline by the generated project) it is
# built once here from the exact vendored source snapshot under third_party/ --
# the same "heavier lib, built in the toolchain image, like on a board" posture
# as protobuf/gRPC/ZMQ/SOCI above. See third_party/cyclonedds/VENDORED.md.
# Security plugins are OpenSSL-backed (libssl-dev, above) so they line up with
# the F5 CryptoBackend seam dds-transport task 3 wires in. Placed last so
# touching the DDS snapshot doesn't invalidate the apt / JDK / Android layers.
# Two COPY+RUN pairs (core, then the C++ binding) so editing the ddscxx
# snapshot doesn't force a core rebuild, and vice versa.
COPY third_party/cyclonedds /tmp/dds-src/cyclonedds
RUN cmake -S /tmp/dds-src/cyclonedds -B /tmp/dds-src/build-core \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DDSPERF=OFF \
        -DBUILD_IDLC=ON -DENABLE_SECURITY=ON -DENABLE_SSL=ON -DENABLE_LTO=OFF \
    && cmake --build /tmp/dds-src/build-core -j"$(nproc)" \
    && cmake --install /tmp/dds-src/build-core \
    && ldconfig && rm -rf /tmp/dds-src/build-core
COPY third_party/cyclonedds-cxx /tmp/dds-src/cyclonedds-cxx
RUN cmake -S /tmp/dds-src/cyclonedds-cxx -B /tmp/dds-src/build-cxx \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF \
    && cmake --build /tmp/dds-src/build-cxx -j"$(nproc)" \
    && cmake --install /tmp/dds-src/build-cxx \
    && ldconfig && rm -rf /tmp/dds-src
# /usr/local is already a default CMake search prefix; set it explicitly so
# find_package(CycloneDDS-CXX) resolves even when a caller overrides the path.
ENV CMAKE_PREFIX_PATH="/usr/local"

WORKDIR /harpia

CMD ["bash"]
