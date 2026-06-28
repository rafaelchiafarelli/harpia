"""Stage 13 -- gRPC / socket access functions (C++).

The project's transport is gRPC: FileCreator emits a `<name>_service.proto` per
message defining a service with push / pullByID / streamSrc / heartBeat RPCs
(the push/pull and streaming functions of spec stage 13 / 12.1-12.2 are realized
as these RPC methods). This stage runs protoc with the C++ gRPC plugin over
those service protos to generate the client stubs and server skeletons:

    <name>_service.grpc.pb.h / .grpc.pb.cc      (spec stage 13 / 12.3)

Output lands next to the Stage 7 message code under <dest>/generated/cpp/, so the
generated `.grpc.pb.h` resolves its `#include "protofiles/<name>_service.pb.h"`
through the same include root (-I <dest>/proto at generation, -I generated/cpp
when compiling).

Requires both protoc and grpc_cpp_plugin (provided by the harpia Docker image).
If either is missing this stage logs and returns an error rather than raising, so
the earlier stages still complete on a bare host.
"""
import glob
import os
import shutil
import subprocess

from Logger.logger import logger
from Errors.Error import Error, Types, Classes


class GrpcCompiler:
    def __init__(self, dest) -> None:
        self.dest = dest
        self.protoRoot = os.path.join(dest, "proto")
        self.protoFilesDir = os.path.join(self.protoRoot, "protofiles")
        self.cppOut = os.path.join(dest, "generated", "cpp")
        self.log = logger(outFile=None, moduleName="GrpcCompiler")

    def protocPath(self):
        return shutil.which("protoc")

    def pluginPath(self):
        return shutil.which("grpc_cpp_plugin")

    def Process(self):
        protoc = self.protocPath()
        if protoc is None:
            self.log.print(
                "protoc not found on PATH; skipping Stage 13 gRPC generation. "
                "Run inside the harpia Docker image (see docker/run.sh)."
            )
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.PROTOC_NOT_FOUND,
                         FileName=self.protoFilesDir)

        plugin = self.pluginPath()
        if plugin is None:
            self.log.print(
                "grpc_cpp_plugin not found on PATH; skipping Stage 13 gRPC "
                "generation. Run inside the harpia Docker image."
            )
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.GRPC_PLUGIN_NOT_FOUND,
                         FileName=self.protoFilesDir)

        services = sorted(glob.glob(
            os.path.join(self.protoFilesDir, "*_service.proto")))
        if not services:
            self.log.print("no *_service.proto files found in {}".format(
                self.protoFilesDir))
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.NO_SERVICE_FILES_TO_COMPILE,
                         FileName=self.protoFilesDir)

        os.makedirs(self.cppOut, exist_ok=True)
        cmd = [protoc, "-I", self.protoRoot, "--grpc_out", self.cppOut,
               "--plugin=protoc-gen-grpc={}".format(plugin)] + services
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log.print("grpc generation failed:\n{}".format(
                result.stderr.strip()))
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.GRPC_COMPILATION_ERROR,
                         FileName=self.protoFilesDir,
                         FileLine=result.stderr.strip())

        self.log.print("grpc_cpp_plugin generated stubs for {} service(s) "
                       "into {}".format(len(services), self.cppOut))
        return None
