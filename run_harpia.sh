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
#   <output_folder>  where the generated project is written (write-if-different;
#                    safe to point at the same folder across runs, not wiped).
#                    Both folders may live ANYWHERE on the filesystem.
#
#   --no-build       generate only; skip the cmake build + ctest run.
#
# The generated output folder is self-contained: it vendors its own copy of the
# third-party C++ libs (sqlite/tinyxml2/crow/asio), so you can copy it to any
# machine with a C++17 toolchain + protoc/grpc and build it — see the
# HOW_TO_BUILD.md this script drops into the output folder.
#
# Everything runs inside the `harpia-build` Docker image (non-TTY-safe, so this
# works in CI/agent shells too).
#
set -euo pipefail

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

# Per-Dockerfile image ref + per-clone Gradle cache volume, so several clones
# can run this concurrently. Sets HARPIA_IMAGE / HARPIA_GRADLE_VOLUME /
# harpia_ensure_image (override the two vars in the environment if needed).
. "$REPO_ROOT/Docker/_env.sh"

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

# The image is built on first use (same as Docker/run.sh).
harpia_ensure_image

# Container paths: repo at /harpia (workdir), input read-only, output read-write.
C_INPUT=/harpia_input
C_OUTPUT=/harpia_output

# The input folder is mounted READ-ONLY: codegen must never mutate its source.
# The one exception is the very first generation of a brand-new project. The
# pipeline freezes each message's wire numbers into a local sidecar
# (schema_registry/<stem>/<msg>.fieldmap) written NEXT TO the .harpia file, i.e.
# inside the input folder (Message/FieldMap.py::registry_path). That write only
# happens when the sidecar does not exist yet; every later run only reads it. The
# sidecar is git-ignored (repo .gitignore: schema_registry/) and regenerated per
# checkout, not committed. So if the input folder has no schema_registry/
# anywhere, mount it read-write for this single run to let that first freeze
# land; once it exists, go back to read-only.
if [ -n "$(find "$INPUT_ABS" -type d -name schema_registry -print -quit)" ]; then
    INPUT_MOUNT="$INPUT_ABS:$C_INPUT:ro"
    INPUT_MOUNT_NOTE="read-only"
else
    INPUT_MOUNT="$INPUT_ABS:$C_INPUT"
    INPUT_MOUNT_NOTE="READ-WRITE (first generation: local schema_registry/ sidecars will be written into the input folder -- git-ignored, no need to commit)"
fi

echo "input   : $INPUT_ABS/$HARPIA_NAME"
echo "include : $INPUT_ABS/$INCLUDE_SUBPATH"
echo "output  : $OUTPUT_ABS"
echo "mount   : input mounted $INPUT_MOUNT_NOTE"
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
    -v "$INPUT_MOUNT" \
    -v "$OUTPUT_ABS":"$C_OUTPUT" \
    -v "$HARPIA_GRADLE_VOLUME":/tmp/.gradle \
    -e HOME=/tmp \
    -e GRADLE_USER_HOME=/tmp/.gradle \
    -e HARPIA_INPUT_FILE="$C_INPUT/$HARPIA_NAME" \
    -e HARPIA_INCLUDE_FOLDER="$C_INPUT/$INCLUDE_SUBPATH" \
    -e HARPIA_OUTPUT_DIR="$C_OUTPUT" \
    "$HARPIA_IMAGE" bash -c "$RUN_CMD"

# Drop a build guide into the output folder so it's a complete, portable example.
# Written after codegen (not before) simply because it documents that run's output.
cat > "$OUTPUT_ABS/HOW_TO_BUILD.md" <<'EOF'
# How to build this generated project

This folder is a self-contained Harpia-generated C++ project. It vendors its own
third-party libraries under `third_party/` (sqlite, tinyxml2, crow, asio), so it
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
