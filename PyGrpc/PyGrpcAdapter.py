"""python-target / py-transports-http -- gRPC servicers (the Python side of
``Database/GrpcServiceAdapter``).

Copies ``runtime/grpc_service.py`` as ``harpia_runtime.grpc_service`` and
generates ``harpia_generated/grpc/<name>_<hash>_grpc.py`` per table-bearing
message (the C++ ``grpc/*_grpc.h`` set) plus
``harpia_generated/grpc/grpc_server_bringup.py``.
"""
import os

from Crypto.backend import transport_hardening_required
from Database.auth_gate import effective_rbac, transport_mode
from Logger.logger import logger
from PyHttp.PyHttpAdapter import copy_rbac_runtimes
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_SERVICE = loadTemplate(__file__, "grpc.py.tmpl")
_BRINGUP = loadTemplate(__file__, "grpc_server_bringup.py.tmpl")
_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime",
                        "grpc_service.py")
GRPC_MODULE = "harpia_runtime.grpc_service"
TLS_MODULE = "harpia_runtime.tls"
_TLS_RUNTIME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "PyHttp", "runtime", "tls.py")
GRPC_EXT = "_grpc.py"


class PyGrpcAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "grpc")
        self.log = logger(outFile=None, moduleName="PyGrpcAdapter")

    def _tables(self):
        return [m for m in self.messages
                if not getattr(m, "isEnum", False) and m.tableName]

    def Process(self):
        tables = self._tables()
        if not tables:
            return None
        copy_runtime_module(self.dest, _RUNTIME, GRPC_MODULE)
        copy_runtime_module(self.dest, _TLS_RUNTIME, TLS_MODULE)
        if any(self._rbac(m) for m in tables):
            copy_rbac_runtimes(self.dest)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated gRPC servicers, one module per table."""\n')
        for msg in tables:
            write_if_different(os.path.join(
                self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, GRPC_EXT)),
                self._render(msg))
        write_if_different(os.path.join(self.outDir, "grpc_server_bringup.py"),
                           self._render_bringup(tables))
        self.log.print("generated {} gRPC servicer(s) into {}".format(len(tables), self.outDir))
        return None

    def _rbac(self, msg):
        """The per-message gate choice, shared with C++
        (``Database.auth_gate.effective_rbac``)."""
        return effective_rbac(msg, transport_hardening_required(self.compliance))

    def _render(self, msg):
        if self._rbac(msg):
            return _SERVICE.format(
                name=msg.name, hash=msg.md5Hash,
                gate_doc="RBAC (``protected``, or hardened and not ``open``) -- the "
                         "verified client-certificate CN mapped to a role by "
                         "``HARPIA_RBAC_MAP`` (:mod:`harpia_runtime.rbac`); "
                         "``UNAUTHENTICATED`` without an identity, "
                         "``PERMISSION_DENIED`` when its role may not perform the "
                         "RPC. Needs a server that requires client certificates "
                         "(see :mod:`harpia_runtime.rbac_gates`).",
                gate_import="",
                rbac_import="\nfrom harpia_runtime.rbac_gates import grpc_rbac_gate",
                gate_expr="grpc_rbac_gate({!r})".format(msg.name))
        return _SERVICE.format(
            name=msg.name, hash=msg.md5Hash,
            gate_doc="the flat generated credential -- ``x-user: {}`` and "
                     "``x-pswd: <hash>`` call metadata, else "
                     "``UNAUTHENTICATED``.".format(msg.name),
            gate_import=", flat_gate", rbac_import="",
            gate_expr="flat_gate({!r}, {!r})".format(msg.name, msg.md5Hash))

    def _transport(self):
        """``(hardening, mode_consts, tls_args)`` for a bring-up: C++'s rule --
        EMIT_TLS / CLIENT_CERT_REQUIRED only when a protected/open message
        makes ``transport_mode`` diverge from the project default."""
        hardening = transport_hardening_required(self.compliance)
        emit_tls, cert_required = transport_mode(self.messages, hardening)
        if (emit_tls, cert_required) == (hardening, hardening):
            return hardening, "", "HARDENING_REQUIRED, mtls"
        consts = ("#: protected/open messages diverge from the project default\n"
                  "#: (Database.auth_gate.transport_mode)\n"
                  "EMIT_TLS = {}\nCLIENT_CERT_REQUIRED = {}\n".format(emit_tls, cert_required))
        return hardening, consts, "EMIT_TLS, mtls, CLIENT_CERT_REQUIRED"

    def _render_bringup(self, tables):
        mods = sorted("{}_{}_grpc".format(m.name, m.md5Hash) for m in tables)
        imports = "from harpia_generated.grpc import (\n{})".format(
            "".join("    {},\n".format(m) for m in mods))
        registrations = "\n".join(
            "        {0}_{1}_grpc.add_to_server({0}_{1}_grpc.{0}_Service(pool), "
            "self.server)".format(m.name, m.md5Hash) for m in tables)
        hardening, mode_consts, tls_args = self._transport()
        return _BRINGUP.format(hardening=hardening, mode_consts=mode_consts, tls_args=tls_args,
                               imports=imports, registrations=registrations,
                               names=repr(tuple(m.name for m in tables)))
