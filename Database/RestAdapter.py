"""Stage 12 -- RESTful HTTP bindings.

For each table-bearing message, emit a header (<name>_<hash>_rest.h) that
registers CRUD routes on a Crow server (crow::SimpleApp), backed by the CRUDL
DAO (spec stage 12 / 11.1):

  GET  <base>/<name>      list      GET    <base>/<name>/:id   read
  POST <base>/<name>      create    PUT    <base>/<name>/:id   update
                                    DELETE <base>/<name>/:id   delete

GET list is paginated (?limit=&offset=) when the request supplies a limit or
the message declares a "pagination[size]" field (that size becomes the
default limit); with no limit in play it returns everything, unchanged from
before pagination support existed.

Content negotiation (spec stage 12): a request body is parsed as XML when its
Content-Type contains "xml" (else JSON), and a response is serialized as XML when
the Accept header asks for "xml" (else JSON), reusing the JSON and XML adapters.

Every route enforces the generated access credential (Stage 5 access rights): the
request must carry X-User: <name> and X-Pswd: <hash> headers, or it is rejected
with HTTP 401 (mirrors the SOAP endpoint, which gates on <credentials>).

**transport-authn epic, task 3 (mtls-rest-soap):** whenever any <name>_rest.h is
emitted this also drops a shared REST+SOAP server bring-up into
generated/cpp/http/ (REST and SOAP ride one crow::SimpleApp, so one bring-up):

  http/harpia_http_mtls.h          hand-written mTLS context helper, copied
                                   verbatim (harpia::http_transport::{MtlsFiles,
                                   SecurityRefused, make_server_context} --
                                   builds an asio::ssl::context with client-cert
                                   verify required; fail-safe, never plaintext)
  http/http_server_bringup.h       rendered: #includes every <name>_rest.h +
                                   <name>_soap.h, registers every route on one
                                   crow::SimpleApp, bakes kHardeningRequired
                                   from transport_hardening_required(compliance)
                                   and (when hardened) wires app.ssl(...)
  http/http_server_selection.json  the F5 CryptoBackend choice + hardening flag
                                   (same field set as dds_security_selection.json)

The per-route credential checks are untouched -- mTLS sits under them.
"""
import json
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different, copy_if_different
from Database.model import pagination_default
from Compliance.http_common import (
    HTTP_MTLS_RUNTIME, HTTP_MTLS_RUNTIME_SRC,
    HTTP_SERVER_BRINGUP, HTTP_SERVER_SELECTION, HTTP_OUT_SUBDIR)
from Compliance.rbac_common import (
    RBAC_RUNTIME, RBAC_RUNTIME_SRC, RBAC_RUNTIME_DEPS)
from Database.auth_gate import rest_auth_fills
from Crypto.backend import get_backend as get_crypto_backend, \
    transport_hardening_required

REST_EXT = "_rest.h"
SOAP_EXT = "_soap.h"

_REST = loadTemplate(__file__, "rest.h.tmpl")
_BRINGUP = loadTemplate(__file__, "http_server_bringup.h.tmpl")


class RestAdapter:
    def __init__(self, messages, dest, compliance=None,
                 crypto_backend=None) -> None:
        self.compliance = compliance
        # F5 seam: main.py / run_pipeline.py resolve the CryptoBackend once and
        # hand it in (same as DdsAdapter / GrpcServiceAdapter); fall back to
        # resolving it here so a direct-drive caller still works.
        self.crypto_backend = crypto_backend or get_crypto_backend(
            compliance=compliance)
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "rest")
        self.httpDir = os.path.join(dest, "generated", "cpp", HTTP_OUT_SUBDIR)
        self.log = logger(outFile=None, moduleName="RestAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # transport-authn task 4: the per-route gate is a three-role RBAC check
        # when the compliance profile mandates hardened transport (same
        # predicate that turns on mTLS), else the flat X-User/X-Pswd credential.
        rbac = transport_hardening_required(self.compliance)
        table_msgs = []
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            default_limit = pagination_default(msg) or 0
            header = _REST.format(
                guard="HARPIA_REST_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
                default_limit=default_limit,
                **rest_auth_fills(msg.name, msg.md5Hash, rbac),
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, REST_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            table_msgs.append((msg.name, msg.md5Hash))

        if table_msgs:
            self._write_http_bringup(table_msgs, rbac)

        self.log.print("generated {} REST binding(s) into {}".format(
            len(table_msgs), self.outDir))
        return None

    def _write_http_bringup(self, table_msgs, rbac):
        """The shared REST+SOAP server bring-up + mTLS selection
        (transport-authn task 3), emitted whenever the schema has at least one
        table-bearing message -- same "only when there's transport output"
        condition as GrpcServiceAdapter's gRPC bring-up. SoapAdapter emits the
        matching <name>_soap.h for the same message set in the same run."""
        os.makedirs(self.httpDir, exist_ok=True)
        copy_if_different(HTTP_MTLS_RUNTIME_SRC,
                          os.path.join(self.httpDir, HTTP_MTLS_RUNTIME))

        # transport-authn task 4: the RBAC gate runtime (+ its AuditSink
        # dependency) rides next to the transport headers, same pattern as
        # harpia_http_mtls.h -- but only when the RBAC variant is compiled in.
        if rbac:
            copy_if_different(RBAC_RUNTIME_SRC,
                              os.path.join(self.httpDir, RBAC_RUNTIME))
            for dep_name, dep_src in RBAC_RUNTIME_DEPS:
                copy_if_different(dep_src,
                                  os.path.join(self.httpDir, dep_name))

        rest_includes = "\n".join(
            '#include "rest/{}_{}{}"'.format(name, h, REST_EXT)
            for name, h in table_msgs)
        soap_includes = "\n".join(
            '#include "soap/{}_{}{}"'.format(name, h, SOAP_EXT)
            for name, h in table_msgs)
        registrations = "\n".join(
            "        ::harpia::rest::register_{n}(app_, db, rest_base);\n"
            "        ::harpia::soap::register_{n}_soap(app_, db, soap_base);".format(
                n=name)
            for name, _ in table_msgs)
        backend = self.crypto_backend
        hardening = transport_hardening_required(self.compliance)
        write_if_different(
            os.path.join(self.httpDir, HTTP_SERVER_BRINGUP),
            _BRINGUP.format(
                rest_includes=rest_includes,
                soap_includes=soap_includes,
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
            os.path.join(self.httpDir, HTTP_SERVER_SELECTION),
            json.dumps(selection, indent=2, sort_keys=True) + "\n")
