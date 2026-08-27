"""Stage 7 -- invoke protoc on the emitted .proto files and produce C++.

The front-end stages emit a clean proto tree under <dest>/proto/protofiles/.
This stage runs the protobuf compiler over that tree to generate the C++
message/service code (.pb.h / .pb.cc) under <dest>/generated/cpp/.

The generated protos import each other as "protofiles/<name>.proto", so protoc
is invoked with the include root at <dest>/proto and that relative layout is
preserved in the output.

protoc is provided by the harpia Docker image (see Docker/run.sh). If it is not
on PATH this stage logs a clear message and returns a PROTOC_NOT_FOUND error
rather than raising, so running the pipeline on a host without protoc still
completes the earlier stages.
"""
import glob
import os
import shutil
import subprocess
import tempfile

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import copy_tree_if_different


class ProtoCompiler:
    def __init__(self, dest, compliance=None) -> None:
        self.compliance = compliance
        self.dest = dest
        self.protoRoot = os.path.join(dest, "proto")
        self.protoFilesDir = os.path.join(self.protoRoot, "protofiles")
        self.cppOut = os.path.join(dest, "generated", "cpp")
        self.log = logger(outFile=None, moduleName="ProtoCompiler")

    def protocPath(self):
        return shutil.which("protoc")

    def Process(self):
        protoc = self.protocPath()
        if protoc is None:
            self.log.print(
                "protoc not found on PATH; skipping Stage 7 C++ generation. "
                "Run inside the harpia Docker image (see Docker/run.sh)."
            )
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.PROTOC_NOT_FOUND,
                         FileName=self.protoFilesDir)

        protos = sorted(glob.glob(os.path.join(self.protoFilesDir, "*.proto")))
        if not protos:
            self.log.print("no .proto files found in {}".format(self.protoFilesDir))
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.NO_PROTO_FILES_TO_COMPILE,
                         FileName=self.protoFilesDir)

        os.makedirs(self.cppOut, exist_ok=True)
        # protoc always rewrites its output unconditionally, which would give
        # every .pb.h/.pb.cc a fresh mtime on every regenerate regardless of
        # content. Run it into a scratch dir and diff-copy the result into
        # place so an unchanged file keeps its mtime, same as every other
        # adapter's write_if_different (see Util.util).
        with tempfile.TemporaryDirectory() as scratchOut:
            cmd = [protoc, "-I", self.protoRoot, "--cpp_out", scratchOut] + protos
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log.print("protoc failed:\n{}".format(result.stderr.strip()))
                return Error(errCl=Classes.PROTO_COMPILATION,
                             errTp=Types.PROTOC_COMPILATION_ERROR,
                             FileName=self.protoFilesDir,
                             FileLine=result.stderr.strip())
            copy_tree_if_different(scratchOut, self.cppOut)

        self.log.print("protoc generated C++ for {} proto files into {}".format(
            len(protos), self.cppOut))
        return None
