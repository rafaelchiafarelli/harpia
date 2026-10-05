"""python-target / py-transports-http -- REST (and later SOAP) over HTTP
(the Python side of ``Database/RestAdapter.py`` / ``SoapAdapter``).

Copies the HTTP runtimes (``harpia_runtime.http.router`` / ``.rest``) and
generates ``harpia_generated/rest/<name>_<hash>_rest.py`` per table-bearing
message plus ``harpia_generated/http/http_server_bringup.py``.
"""
import os

from Database.model import pagination_default
from Crypto.backend import transport_hardening_required
from Compliance.rbac_common import PY_RBAC_MODULE, PY_RBAC_RUNTIME_DEPS, PY_RBAC_RUNTIME_SRC
from Compliance.session_common import (
    PY_SESSION_MODULE, PY_SESSION_RUNTIME_DEPS, PY_SESSION_RUNTIME_SRC)
from Database.auth_gate import effective_rbac, transport_mode
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from PyCapability.PyCapabilityAdapter import http_module
from Util.util import loadTemplate, write_if_different

_REST = loadTemplate(__file__, "rest.py.tmpl")
_BRINGUP = loadTemplate(__file__, "http_server_bringup.py.tmpl")
_SOAP = loadTemplate(__file__, "soap.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("router.py", "harpia_runtime.http.router"),
    ("rest.py", "harpia_runtime.http.rest"),
    ("tls.py", "harpia_runtime.tls"),
    ("soap.py", "harpia_runtime.soap"),
    ("soap_endpoint.py", "harpia_runtime.http.soap_endpoint"),
)
#: copied (with harpia_runtime.rbac) only when some message is RBAC-gated
RBAC_GATES_MODULE = "harpia_runtime.rbac_gates"
RBAC_GATES_SRC = os.path.join(_RUNTIME_DIR, "rbac_gates.py")
SESSION_CLIENT_MODULE = "harpia_runtime.session_client"
SESSION_CLIENT_SRC = os.path.join(_RUNTIME_DIR, "session_client.py")
REST_EXT = "_rest.py"
SOAP_EXT = "_soap.py"

_FLAT_SOAP_GATE = '''
#: the flat generated credential (SOAP Header <credentials>)
EARLY_GATE = flat_soap_gate({name_lit}, {hash_lit})
'''

_RBAC_SOAP_GATE = '''
#: RBAC on the verified client-certificate CN, checked after the operation
#: is parsed (harpia_runtime.rbac_gates)
OP_GATE = soap_rbac_gate({name_lit})
'''

_RBAC_GATE = '''
#: RBAC on the verified client-certificate CN (harpia_runtime.rbac_gates)
GATE = rest_rbac_gate({name_lit})
'''

_FLAT_GATE = '''
#: the flat generated credential (X-User / X-Pswd)
GATE = flat_gate({name_lit}, {hash_lit})
'''


_RBAC_IMPORT = "\nfrom harpia_runtime.rbac_gates import {}"
_RBAC_DOC = ("RBAC (``protected``, or hardened and not ``open``) -- a valid "
             "``Authorization: Bearer`` session token's CN, else the verified "
             "client-certificate CN, mapped to a role by ``HARPIA_RBAC_MAP`` "
             "(:mod:`harpia_runtime.rbac`); a presented but invalid token is a 401; "
             "{deny}.")


def copy_rbac_runtimes(dest):
    """Copy ``harpia_runtime.rbac`` + ``.session`` (+ their audit sink),
    ``.rbac_gates`` and ``.session_client`` (C++ copies ``harpia_rbac.h`` /
    ``harpia_session.h`` only when a message gets the RBAC gate, likewise)."""
    for module, src in ((PY_RBAC_MODULE, PY_RBAC_RUNTIME_SRC),
                        (PY_SESSION_MODULE, PY_SESSION_RUNTIME_SRC),
                        *PY_RBAC_RUNTIME_DEPS, *PY_SESSION_RUNTIME_DEPS,
                        (RBAC_GATES_MODULE, RBAC_GATES_SRC),
                        (SESSION_CLIENT_MODULE, SESSION_CLIENT_SRC)):
        copy_runtime_module(dest, src, module)


class PyHttpAdapter:
    def __init__(self, messages, dest, compliance=None, rootHash=None) -> None:
        self.compliance = compliance
        # py-versioning task 2: with the root hash HttpServer also registers
        # GET <rest_base>/capabilities
        self.rootHash = rootHash
        self.messages = messages
        self.dest = dest
        self.pyRoot = os.path.join(dest, "python", "harpia_generated")
        self.log = logger(outFile=None, moduleName="PyHttpAdapter")

    def _tables(self):
        return [m for m in self.messages
                if not getattr(m, "isEnum", False) and m.tableName]

    def Process(self):
        tables = self._tables()
        if not tables:
            return None
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        if any(self._rbac(m) for m in tables):
            copy_rbac_runtimes(self.dest)
        restDir = os.path.join(self.pyRoot, "rest")
        soapDir = os.path.join(self.pyRoot, "soap")
        httpDir = os.path.join(self.pyRoot, "http")
        for d, doc in ((restDir, "Generated REST CRUD routes, one module per table."),
                       (soapDir, "Generated SOAP endpoints, one module per table."),
                       (httpDir, "Generated HTTP server bring-up.")):
            os.makedirs(d, exist_ok=True)
            write_if_different(os.path.join(d, "__init__.py"), '"""{}"""\n'.format(doc))
        for msg in tables:
            write_if_different(os.path.join(
                restDir, "{}_{}{}".format(msg.name, msg.md5Hash, REST_EXT)),
                self._render_rest(msg))
            write_if_different(os.path.join(
                soapDir, "{}_{}{}".format(msg.name, msg.md5Hash, SOAP_EXT)),
                self._render_soap(msg))
        write_if_different(os.path.join(httpDir, "http_server_bringup.py"),
                           self._render_bringup(tables))
        self.log.print("generated {} REST binding(s) into {}".format(len(tables), restDir))
        return None

    def _rbac(self, msg):
        """The per-message gate choice, shared with C++
        (``Database.auth_gate.effective_rbac``)."""
        return effective_rbac(msg, transport_hardening_required(self.compliance))

    def _render_rest(self, msg):
        if self._rbac(msg):
            return _REST.format(
                name=msg.name, hash=msg.md5Hash, table=msg.tableName,
                name_lit=repr(msg.name), default_limit=pagination_default(msg) or 0,
                gate_doc=_RBAC_DOC.format(deny="401 without an identity, 403 when "
                                               "its role may not perform the operation"),
                gate_import="", rbac_import=_RBAC_IMPORT.format("rest_rbac_gate"),
                gate_def=_RBAC_GATE.format(name_lit=repr(msg.name)))
        return _REST.format(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName, name_lit=repr(msg.name),
            default_limit=pagination_default(msg) or 0,
            gate_doc="the flat generated credential -- ``X-User: {}`` and "
                     "``X-Pswd: <hash>``, else 401.".format(msg.name),
            gate_import="flat_gate, ", rbac_import="",
            gate_def=_FLAT_GATE.format(name_lit=repr(msg.name), hash_lit=repr(msg.md5Hash)))

    def _render_soap(self, msg):
        if self._rbac(msg):
            return _SOAP.format(
                name=msg.name, hash=msg.md5Hash, table=msg.tableName,
                name_lit=repr(msg.name),
                wsdl_lit=repr("wsdl/{}_{}.wsdl".format(msg.name, msg.md5Hash)),
                gate_doc=_RBAC_DOC.format(deny="checked once the operation is parsed; "
                                               "a 401 / 403 ``Client.Authentication`` "
                                               "Fault"),
                gate_import="", rbac_import=_RBAC_IMPORT.format("soap_rbac_gate"),
                gate_def=_RBAC_SOAP_GATE.format(name_lit=repr(msg.name)),
                gate_args="op_gate=OP_GATE")
        return _SOAP.format(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName, name_lit=repr(msg.name),
            wsdl_lit=repr("wsdl/{}_{}.wsdl".format(msg.name, msg.md5Hash)),
            gate_doc="the flat generated credential -- ``<credentials><user>{}</user>"
                     "<pswd>hash</pswd></credentials>`` in the SOAP Header, else a "
                     "401 Fault.".format(msg.name),
            gate_import="flat_soap_gate, ", rbac_import="",
            gate_def=_FLAT_SOAP_GATE.format(name_lit=repr(msg.name),
                                            hash_lit=repr(msg.md5Hash)),
            gate_args="early_gate=EARLY_GATE")

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
        imports = "".join("from harpia_generated.{0} import (\n{1})\n".format(kind, "".join(
            "    {},\n".format(mod) for mod in sorted(
                "{}_{}_{}".format(m.name, m.md5Hash, kind) for m in tables)))
            for kind in ("rest", "soap"))
        registrations = "".join(
            "        {0}_{1}_rest.register(self.router, pool, rest_base)\n"
            "        {0}_{1}_soap.register(self.router, pool, soap_base)\n".format(
                m.name, m.md5Hash) for m in tables).rstrip("\n")
        if self.rootHash:
            cap = http_module(self.rootHash)
            imports = "from harpia_generated.capability import (\n    {},\n)\n{}".format(
                cap, imports)
            registrations += ("\n        # capability handshake (ungated, like heartBeat)\n"
                              "        {}.register_capabilities(self.router, rest_base)".format(
                                  cap))
        if any(self._rbac(m) for m in tables):
            registrations += ("\n        # bearer-session issuance (RBAC-gated messages exist)\n"
                              "        register_session_routes(self.router, rest_base, soap_base)")
            session_import = "\nfrom harpia_runtime.rbac_gates import register_session_routes"
        else:
            session_import = ""
        hardening, mode_consts, tls_args = self._transport()
        return _BRINGUP.format(hardening=hardening, mode_consts=mode_consts, tls_args=tls_args,
                               session_import=session_import,
                               imports=imports.rstrip("\n"), registrations=registrations,
                               rest_names=repr(tuple(m.name for m in tables)))
