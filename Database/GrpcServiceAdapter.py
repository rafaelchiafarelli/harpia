"""Stage 13 -- gRPC service implementation (wires the generated service to CRUDL).

GrpcCompiler emits the client stubs and abstract server skeletons from each
<name>_service.proto. This adapter closes the loop for every table-bearing
message: it emits a concrete service implementation
(<name>_<hash>_grpc.h) whose RPCs call the CRUDL DAO --

  push      -> dao.create      pullByID -> dao.read
  streamSrc -> dao.list        heartBeat -> echo

so the gRPC transport becomes a real end-to-end path over SQLite (like the ZMQ
transport already is). Header-only C++; compiles once Stage 7 + Stage 13
(GrpcCompiler) have produced the message and service code. Non-table messages get
no implementation (there is no DAO to back them). The data operations enforce the
generated access credential via x-user/x-pswd call metadata (UNAUTHENTICATED on
mismatch), mirroring SOAP/REST; heartBeat stays open.

**transport-authn epic, task 2 (mtls-grpc):** whenever any <name>_grpc.h is
emitted this also drops a project-wide gRPC server bring-up into the same
generated/cpp/grpc/ dir:

  harpia_grpc_mtls.h          hand-written credentials mechanism, copied verbatim
                              (harpia::grpc_transport::{MtlsFiles, SecurityRefused,
                              server_credentials, channel_credentials})
  grpc_server_bringup.h       rendered: #includes every <name>_grpc.h, bakes in
                              kHardeningRequired from
                              transport_hardening_required(compliance), and
                              defines the harpia::grpc_transport::GrpcServer
                              bring-up class (ServerBuilder + all services +
                              mTLS-or-insecure credentials)
  grpc_server_selection.json  the F5 CryptoBackend choice + whether the
                              compliance profile mandates hardened transport
                              (same field set as dds_security_selection.json)

The per-RPC credential-metadata check is untouched -- mTLS sits under it.
"""
import json
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different, copy_if_different
from Compliance.grpc_common import (
    GRPC_MTLS_RUNTIME, GRPC_MTLS_RUNTIME_SRC,
    GRPC_SERVER_BRINGUP, GRPC_SERVER_SELECTION)
from Compliance.rbac_common import (
    RBAC_RUNTIME, RBAC_RUNTIME_SRC, RBAC_RUNTIME_DEPS)
from Database.auth_gate import grpc_auth_fills
from Crypto.backend import get_backend as get_crypto_backend, \
    transport_hardening_required

GRPC_EXT = "_grpc.h"

_GRPC = loadTemplate(__file__, "grpc_service.h.tmpl")
_BRINGUP = loadTemplate(__file__, "grpc_server_bringup.h.tmpl")


class GrpcServiceAdapter:
    def __init__(self, messages, dest, compliance=None,
                 crypto_backend=None) -> None:
        self.compliance = compliance
        # F5 seam: `main.py` / `run_pipeline.py` resolve the CryptoBackend once
        # and hand it in (same as DdsAdapter); fall back to resolving it here so
        # a direct-drive caller still works.
        self.crypto_backend = crypto_backend or get_crypto_backend(
            compliance=compliance)
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "grpc")
        self.log = logger(outFile=None, moduleName="GrpcServiceAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # transport-authn task 4: RBAC role check vs the flat x-user/x-pswd
        # metadata credential, chosen by the same predicate that turns on mTLS.
        rbac = transport_hardening_required(self.compliance)
        table_msgs = []
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _GRPC.format(
                guard="HARPIA_GRPC_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
                **grpc_auth_fills(msg.name, msg.md5Hash, rbac),
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, GRPC_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            table_msgs.append((msg.name, msg.md5Hash))

        if table_msgs:
            self._write_server_bringup(table_msgs)
            if rbac:
                copy_if_different(
                    RBAC_RUNTIME_SRC, os.path.join(self.outDir, RBAC_RUNTIME))
                for dep_name, dep_src in RBAC_RUNTIME_DEPS:
                    copy_if_different(
                        dep_src, os.path.join(self.outDir, dep_name))

        self.log.print("generated {} gRPC service impl(s) into {}".format(
            len(table_msgs), self.outDir))
        return None

    def _write_server_bringup(self, table_msgs):
        """The project-wide gRPC server bring-up + mTLS credentials selection
        (transport-authn task 2), emitted whenever the schema has at least one
        table-bearing message -- same "only when there's transport output"
        condition as DdsAdapter's DDS-Security scaffolding."""
        copy_if_different(GRPC_MTLS_RUNTIME_SRC,
                          os.path.join(self.outDir, GRPC_MTLS_RUNTIME))

        includes = "\n".join(
            '#include "grpc/{}_{}{}"'.format(name, h, GRPC_EXT)
            for name, h in table_msgs)
        registrations = "\n".join(
            "        add< ::harpia::grpc_svc::{}_service>(db, builder);".format(
                name)
            for name, _ in table_msgs)
        backend = self.crypto_backend
        hardening = transport_hardening_required(self.compliance)
        write_if_different(
            os.path.join(self.outDir, GRPC_SERVER_BRINGUP),
            _BRINGUP.format(
                includes=includes,
                registrations=registrations,
                hardening="true" if hardening else "false",
                crypto_backend=backend.name,
                openssl_provider=backend.openssl_provider,
            ))

        selection = {
            "hardening_required": hardening,
            "crypto_backend": backend.name,
            "cmake_package": backend.cmake_package,
            "openssl_provider": backend.openssl_provider,
            "fips": backend.fips,
        }
        write_if_different(
            os.path.join(self.outDir, GRPC_SERVER_SELECTION),
            json.dumps(selection, indent=2, sort_keys=True) + "\n")
