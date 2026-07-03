#!/usr/bin/env bash
#
# run_harpia.sh — run the Harpia generator against an input folder and emit a
#                 self-contained, buildable C++ project into an output folder.
#                 One script to do it all: codegen -> cmake -> ctest.
#
#   ./run_harpia.sh <input_folder> <output_folder> [--no-build]
#
#   <input_folder>   a directory containing exactly one .harpia file
#                    (and, optionally, an Include/ subfolder of import modules)
#   <output_folder>  where the generated project is written (cleaned first).
#                    Both folders may live ANYWHERE on the filesystem.
#
#   --no-build       generate only; skip the cmake build + ctest run.
#
# The generated output folder is self-contained: it vendors its own copy of the
# third-party C++ libs (sqlite/tinyxml2/cpp-httplib), so you can copy it to any
# machine with a C++17 toolchain + protoc/grpc and build it — see the
# HOW_TO_BUILD.md this script drops into the output folder.
#
# Everything runs inside the `harpia-build` Docker image (non-TTY-safe, so this
# works in CI/agent shells too).
#
set -euo pipefail

IMAGE=harpia-build

usage() {
    echo "usage: $0 <input_folder> <output_folder> [--no-build]" >&2
    exit 2
}

BUILD=1
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --no-build) BUILD=0 ;;
        -h|--help)  usage ;;
        -*)         echo "error: unknown option: $arg" >&2; usage ;;
        *)          POSITIONAL+=("$arg") ;;
    esac
done
[ ${#POSITIONAL[@]} -eq 2 ] || usage
INPUT_FOLDER=${POSITIONAL[0]}
OUTPUT_FOLDER=${POSITIONAL[1]}

# Repo root = the directory this script lives in (mounted read-write at /harpia:
# it holds main.py, Assets/, and the third_party/ that gets vendored out).
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

[ -d "$INPUT_FOLDER" ] || { echo "error: input folder not found: $INPUT_FOLDER" >&2; exit 1; }

# Locate the single .harpia in the input folder.
mapfile -t HARPIA_FILES < <(find "$INPUT_FOLDER" -maxdepth 1 -type f -name '*.harpia' | sort)
case ${#HARPIA_FILES[@]} in
    0) echo "error: no .harpia file in $INPUT_FOLDER" >&2; exit 1 ;;
    1) : ;;
    *) echo "error: multiple .harpia files in $INPUT_FOLDER; expected exactly one:" >&2
       printf '  %s\n' "${HARPIA_FILES[@]}" >&2; exit 1 ;;
esac
HARPIA_NAME=$(basename "${HARPIA_FILES[0]}")

# Include folder: use <input_folder>/Include if present, else the input folder itself.
if [ -d "$INPUT_FOLDER/Include" ]; then
    INCLUDE_SUBPATH="Include"
else
    INCLUDE_SUBPATH="."
fi

# Absolute host paths (input/output can be anywhere). -m: output need not exist yet.
INPUT_ABS=$(realpath -m "$INPUT_FOLDER")
OUTPUT_ABS=$(realpath -m "$OUTPUT_FOLDER")
mkdir -p "$OUTPUT_ABS"   # create as the host user before Docker mounts it

# The image is built on first use (same as docker/run.sh).
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "docker image '$IMAGE' not found; building it (first run only)..." >&2
    docker build -t "$IMAGE" "$REPO_ROOT"
fi

# Container paths: repo at /harpia (workdir), input read-only, output read-write.
C_INPUT=/harpia_input
C_OUTPUT=/harpia_output

echo "input   : $INPUT_ABS/$HARPIA_NAME"
echo "include : $INPUT_ABS/$INCLUDE_SUBPATH"
echo "output  : $OUTPUT_ABS"
echo "build   : $([ $BUILD -eq 1 ] && echo 'codegen + cmake + ctest' || echo 'codegen only (--no-build)')"

# Build the in-container command. Codegen always runs; build/ctest is optional.
# The cmake build tree lives in an EPHEMERAL /tmp dir so the output folder stays a
# clean source example (its own third_party/ is vendored in, build artifacts are not).
RUN_CMD='set -e; python3 main.py'
if [ $BUILD -eq 1 ]; then
    RUN_CMD="$RUN_CMD"'
        echo "=== building generated project ==="
        cmake -S '"$C_OUTPUT"' -B /tmp/harpia_cmbuild -DHARPIA_BUILD_TESTS=ON
        cmake --build /tmp/harpia_cmbuild -j "$(nproc)"
        echo "=== running ctest ==="
        ctest --test-dir /tmp/harpia_cmbuild --output-on-failure'
fi

docker run --rm -i \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia -w /harpia \
    -v "$INPUT_ABS":"$C_INPUT":ro \
    -v "$OUTPUT_ABS":"$C_OUTPUT" \
    -e HOME=/tmp \
    -e HARPIA_INPUT_FILE="$C_INPUT/$HARPIA_NAME" \
    -e HARPIA_INCLUDE_FOLDER="$C_INPUT/$INCLUDE_SUBPATH" \
    -e HARPIA_OUTPUT_DIR="$C_OUTPUT" \
    "$IMAGE" bash -c "$RUN_CMD"

# Drop a build guide into the output folder so it's a complete, portable example.
# Written after codegen because main.py cleans the output dir at start.
cat > "$OUTPUT_ABS/HOW_TO_BUILD.md" <<'EOF'
# How to build this generated project

This folder is a self-contained Harpia-generated C++ project. It vendors its own
third-party libraries under `third_party/` (sqlite, tinyxml2, cpp-httplib), so it
builds anywhere you have the toolchain below — no need for the Harpia repo.

## Prerequisites
- CMake >= 3.13
- A C++17 compiler (g++/clang++)
- Protocol Buffers + gRPC: `protoc` and the `grpc_cpp_plugin`, plus the protobuf
  and gRPC development libraries
- pthreads

(The `harpia-build` Docker image already contains all of these.)

## Build + run the generated unit tests
```sh
cmake -S . -B build -DHARPIA_BUILD_TESTS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
```

Omit `-DHARPIA_BUILD_TESTS=ON` to build just the demo client/server without the
generated test suite.
EOF

echo "done."
echo "generated project (portable example): $OUTPUT_ABS"
echo "build instructions: $OUTPUT_ABS/HOW_TO_BUILD.md"
