"""python-target / py-tests -- generated per-message unit tests (the Python
side of ``TestAdapter``'s per-message ``tests/<name>_<hash>_test.cpp``).

Emits ``<dest>/python/tests/test_<name>_<hash>.py`` per table-bearing message
(field access; JSON / XML / YAML round trips; the ``to_string`` façade -- a
round trip, or for a message whose tree carries ``phi`` the redaction
placeholder; a full CRUDL round trip on a temp-file
SQLite) plus ``tests/conftest.py``, and copies the reflective helpers as
``harpia_runtime.testing``. Run from ``<dest>/python``: ``pytest``.
"""
import os

from Crypto.backend import transport_hardening_required
from Database.auth_gate import effective_rbac
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from TestAdapter.TestAdapter import TestAdapter
from Util.util import loadTemplate, write_if_different

_TEST = loadTemplate(__file__, "test_message.py.tmpl")
_HTTP_FLAT = loadTemplate(__file__, "http_flat.py.tmpl")
_HTTP_RBAC = loadTemplate(__file__, "http_rbac.py.tmpl")
_APP = loadTemplate(__file__, "test_app.py.tmpl")
_APP_FLAT = loadTemplate(__file__, "app_flat.py.tmpl")
_APP_RBAC = loadTemplate(__file__, "app_rbac.py.tmpl")
_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "testing.py")
TESTING_MODULE = "harpia_runtime.testing"

_CONFTEST = '''"""pytest configuration for the generated suite: import the project from
this checkout (``harpia_generated`` / ``harpia_runtime`` next to ``tests/``)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
'''



class PyTestAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "tests")
        self.log = logger(outFile=None, moduleName="PyTestAdapter")

    def Process(self):
        tables = [m for m in self.messages
                  if not getattr(m, "isEnum", False) and m.tableName]
        if not tables:
            return None
        copy_runtime_module(self.dest, _RUNTIME, TESTING_MODULE)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "conftest.py"), _CONFTEST)
        for msg in tables:
            write_if_different(
                os.path.join(self.outDir, "test_{}_{}.py".format(msg.name, msg.md5Hash)),
                self._render(msg))
        # the app-level suite on the representative message (C++ 14.11-14.14),
        # picked by TestAdapter's own rule
        rep = TestAdapter(self.messages, self.dest, self.compliance)._pick_rep(tables)
        write_if_different(os.path.join(self.outDir, "test_app_{}.py".format(rep.md5Hash)),
                           self._render_app(rep))
        self.log.print("generated {} Python test module(s) into {}".format(
            len(tables), self.outDir))
        return None

    def _rbac(self, msg):
        """The per-message gate choice (``Database.auth_gate.effective_rbac``)."""
        return effective_rbac(msg, transport_hardening_required(self.compliance))

    def _fills(self, msg):
        rbac = self._rbac(msg)
        return dict(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName,
            name_lit=repr(msg.name), hash_lit=repr(msg.md5Hash),
            gate_doc=("RBAC -- the matrix, and an anonymous caller is fail-closed "
                      "(401) on every route." if rbac else
                      "the flat credential -- full credentialed REST / SOAP round trips."),
            rbac_import=("from harpia_runtime.rbac import Decision, Operation, Role, "
                         "decide, permitted\n" if rbac else ""),
            soap_import="" if rbac else "from harpia_runtime.soap import parse_envelope\n")

    def _render(self, msg):
        fills = self._fills(msg)
        http = (_HTTP_RBAC if self._rbac(msg) else _HTTP_FLAT).format(**fills)
        return _TEST.format(http_tests=http, **fills)

    def _render_app(self, msg):
        fills = self._fills(msg)
        rbac = self._rbac(msg)
        body = (_APP_RBAC if rbac else _APP_FLAT).format(**fills)
        if rbac:
            # the gate refuses the anonymous caller before the backend / parser
            crash = ('        assert testing.request(port, "POST", "/api/v1/{}", body,\n'
                     '                               {{"Content-Type": "application/json"}})'
                     '[0] == 401').format(msg.name)
            creds = ("#: no credential: an RBAC caller is identified by its certificate\n"
                     "CRED: dict[str, str] = {}\n")
        else:
            crash = ('        hdr = {{"Content-Type": "application/json", **CRED}}\n'
                     '        assert testing.request(port, "POST", "/api/v1/{0}", body, hdr)'
                     '[0] == 500\n'
                     '        assert testing.request(port, "GET", "/api/v1/{0}", headers=CRED)'
                     '[0] == 500').format(msg.name)
            creds = ('#: the flat generated credential\nCRED = {{"X-User": {0!r}, '
                     '"X-Pswd": {1!r}}}\nSOAP_CRED = "<credentials><user>{0}</user><pswd>{1}'
                     '</pswd></credentials>"\n').format(msg.name, msg.md5Hash)
        return _APP.format(app_tests=body, crash_http=crash, app_creds=creds,
                           bad_json=401 if rbac else 400, **fills)
