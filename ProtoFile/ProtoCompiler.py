"""Stage 7 -- invoke protoc on the emitted .proto files and produce C++.

The front-end stages emit a clean proto tree under <dest>/proto/protofiles/.
This stage runs the protobuf compiler over that tree to generate the C++
message/service code (.pb.h / .pb.cc) under <dest>/generated/cpp/.

The generated protos import each other as "protofiles/<name>.proto", so protoc
is invoked with the include root at <dest>/proto and that relative layout is
preserved in the output.

protoc is provided by the harpia Docker image (see docker/run.sh). If it is not
on PATH this stage logs a clear message and returns a PROTOC_NOT_FOUND error
rather than raising, so running the pipeline on a host without protoc still
completes the earlier stages.
"""
import glob
import os
import shutil
import subprocess

from Logger.logger import logger
from Errors.Error import Error, Types, Classes


class ProtoCompiler:
    def __init__(self, dest) -> None:
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
                "Run inside the harpia Docker image (see docker/run.sh)."
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
        cmd = [protoc, "-I", self.protoRoot, "--cpp_out", self.cppOut] + protos
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log.print("protoc failed:\n{}".format(result.stderr.strip()))
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.PROTOC_COMPILATION_ERROR,
                         FileName=self.protoFilesDir,
                         FileLine=result.stderr.strip())

        self.log.print("protoc generated C++ for {} proto files into {}".format(
            len(protos), self.cppOut))
        return None
