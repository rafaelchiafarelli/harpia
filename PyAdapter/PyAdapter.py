"""python-target / py-foundation task 2 -- the Python target's project layout
and generation-time protobuf/gRPC codegen.

Emits one installable project under ``<dest>/python/``:

- ``pyproject.toml`` (project ``harpia-generated``, Python >= 3.10).
- ``harpia_runtime/`` and ``harpia_generated/`` -- the two top-level packages,
  copied verbatim from ``PyAdapter/runtime/`` (later epics add runtime
  modules there).
- ``proto/harpia_generated/protofiles/`` -- a copy of every per-message
  ``.proto`` and ``_service.proto`` plus the framework protos (``errorCode``,
  ``heartBeat``, ``capabilities_service``), with every
  ``import "protofiles/..."`` rewritten to
  ``import "harpia_generated/protofiles/..."``.
- ``harpia_generated/protofiles/*_pb2.py`` + ``*_pb2.pyi`` (and
  ``*_pb2_grpc.py`` for the protos that declare a service), compiled at
  generation time by the **system** protoc + ``grpc_python_plugin``.

Import path (decision, py-foundation task 2, option (b)): protoc derives Python
imports from ``.proto`` import paths, so the protos are re-rooted under
``harpia_generated/protofiles/`` and the modules import as
``from harpia_generated.protofiles import x_pb2`` -- no generic top-level
``protofiles`` package to collide in a consumer's environment. Only the
descriptor-pool *file* names differ from C++/Java; proto packages and message
names are unchanged, so the wire bytes are identical.

protoc or ``grpc_python_plugin`` missing is a non-fatal ``Error``, same as
``ProtoFile/ProtoCompiler.py``: the layout is still written.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile

from Logger.logger import logger
from PyAdapter.dependencies import pyproject_fills
from Errors.Error import Error, Types, Classes
from Util.util import (loadTemplate, write_if_different, copy_if_different,
                       copy_tree_if_different)

_PYPROJECT_TEMPLATE = loadTemplate(__file__, "pyproject.toml.tmpl")
_RUNTIME_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "runtime")

_FRAMEWORK_PROTOS = ("errorCode.proto", "heartBeat.proto",
                     "capabilities_service.proto")

#: where the protos live inside <dest>/python/proto/ (and so the Python
#: package path protoc derives for the compiled modules)
PROTO_PACKAGE_DIR = ("harpia_generated", "protofiles")

_IMPORT_RE = re.compile(r'^(\s*import\s+(?:public\s+|weak\s+)?")protofiles/',
                        re.MULTILINE)
_SERVICE_RE = re.compile(r'^\s*service\s+\w+', re.MULTILINE)


def rewrite_proto_imports(text):
    """Re-root ``import "protofiles/x.proto"`` under ``harpia_generated/``."""
    return _IMPORT_RE.sub(r'\1' + "/".join(PROTO_PACKAGE_DIR) + "/", text)


def _copy_runtime(src, dst):
    """copy_if_different every file under ``src`` (skipping bytecode caches)."""
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            s = os.path.join(root, fn)
            d = os.path.join(dst, os.path.relpath(s, src))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            copy_if_different(s, d)


class PyAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.pyRoot = os.path.join(dest, "python")
        self.protoRoot = os.path.join(self.pyRoot, "proto")
        self.protoDir = os.path.join(self.protoRoot, *PROTO_PACKAGE_DIR)
        self.sourceProtoDir = os.path.join(dest, "proto", "protofiles")
        self.log = logger(outFile=None, moduleName="PyAdapter")

    def _copy_proto(self, fileName):
        srcPath = os.path.join(self.sourceProtoDir, fileName)
        if not os.path.exists(srcPath):
            return False
        with open(srcPath, "r") as f:
            text = f.read()
        write_if_different(os.path.join(self.protoDir, fileName),
                           rewrite_proto_imports(text))
        return True

    def Process(self):
        os.makedirs(self.protoDir, exist_ok=True)
        write_if_different(os.path.join(self.pyRoot, "pyproject.toml"),
                           _PYPROJECT_TEMPLATE.format(**pyproject_fills()))
        _copy_runtime(_RUNTIME_SRC_DIR, self.pyRoot)

        copied = 0
        for msg in self.messages:
            for suffix in (".proto", "_service.proto"):
                if self._copy_proto("{}_{}{}".format(msg.name, msg.md5Hash, suffix)):
                    copied += 1
        for fileName in _FRAMEWORK_PROTOS:
            if self._copy_proto(fileName):
                copied += 1

        if copied == 0:
            self.log.print("no .proto files to compile for the Python target")
            return Error(errCl=Classes.MESSAGES, errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.protoDir)
        return self._compile()

    def _compile(self):
        protoc = shutil.which("protoc")
        plugin = shutil.which("grpc_python_plugin")
        if protoc is None or plugin is None:
            self.log.print(
                "protoc / grpc_python_plugin not found on PATH; the Python "
                "layout was written but no _pb2 modules were compiled. Run "
                "inside the harpia Docker image (see Docker/run.sh).")
            return Error(errCl=Classes.PROTO_COMPILATION,
                         errTp=Types.PROTOC_NOT_FOUND, FileName=self.protoDir)

        protos = sorted(glob.glob(os.path.join(self.protoDir, "*.proto")))
        rel = [os.path.relpath(p, self.protoRoot) for p in protos]
        # protoc rewrites every output unconditionally; compile into a scratch
        # dir and diff-copy so an unchanged module keeps its mtime.
        with tempfile.TemporaryDirectory() as scratch:
            cmd = [protoc, "-I", self.protoRoot,
                   "--python_out", scratch, "--pyi_out", scratch,
                   "--grpc_python_out", scratch,
                   "--plugin=protoc-gen-grpc_python=" + plugin] + rel
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log.print("protoc (python) failed:\n{}".format(
                    result.stderr.strip()))
                return Error(errCl=Classes.PROTO_COMPILATION,
                             errTp=Types.PROTOC_COMPILATION_ERROR,
                             FileName=self.protoDir,
                             FileLine=result.stderr.strip())
            # grpc_python_plugin writes a *_pb2_grpc.py for every input; keep
            # only those of protos that actually declare a service.
            for proto in protos:
                with open(proto, "r") as f:
                    has_service = _SERVICE_RE.search(f.read()) is not None
                if not has_service:
                    stem = os.path.splitext(os.path.basename(proto))[0]
                    os.remove(os.path.join(scratch, *PROTO_PACKAGE_DIR,
                                           stem + "_pb2_grpc.py"))
            copy_tree_if_different(scratch, self.pyRoot)

        self.log.print("protoc generated Python for {} proto files into {}".format(
            len(protos), os.path.join(self.pyRoot, *PROTO_PACKAGE_DIR)))
        return None
