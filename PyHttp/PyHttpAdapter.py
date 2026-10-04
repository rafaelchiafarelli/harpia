"""python-target / py-transports-http -- REST (and later SOAP) over HTTP
(the Python side of ``Database/RestAdapter.py`` / ``SoapAdapter``).

Copies the HTTP runtimes (``harpia_runtime.http.router`` / ``.rest``) and
generates ``harpia_generated/rest/<name>_<hash>_rest.py`` per table-bearing
message plus ``harpia_generated/http/http_server_bringup.py``.
"""
import os

from Database.model import pagination_default
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_REST = loadTemplate(__file__, "rest.py.tmpl")
_BRINGUP = loadTemplate(__file__, "http_server_bringup.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("router.py", "harpia_runtime.http.router"),
    ("rest.py", "harpia_runtime.http.rest"),
)
REST_EXT = "_rest.py"

_FLAT_GATE = '''
#: the flat generated credential (X-User / X-Pswd)
GATE = flat_gate({name_lit}, {hash_lit})
'''


class PyHttpAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
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
        restDir = os.path.join(self.pyRoot, "rest")
        httpDir = os.path.join(self.pyRoot, "http")
        for d, doc in ((restDir, "Generated REST CRUD routes, one module per table."),
                       (httpDir, "Generated HTTP server bring-up.")):
            os.makedirs(d, exist_ok=True)
            write_if_different(os.path.join(d, "__init__.py"), '"""{}"""\n'.format(doc))
        for msg in tables:
            write_if_different(os.path.join(
                restDir, "{}_{}{}".format(msg.name, msg.md5Hash, REST_EXT)),
                self._render_rest(msg))
        write_if_different(os.path.join(httpDir, "http_server_bringup.py"),
                           self._render_bringup(tables))
        self.log.print("generated {} REST binding(s) into {}".format(len(tables), restDir))
        return None

    def _render_rest(self, msg):
        return _REST.format(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName, name_lit=repr(msg.name),
            default_limit=pagination_default(msg) or 0,
            gate_doc="the flat generated credential -- ``X-User: {}`` and "
                     "``X-Pswd: <hash>``, else 401.".format(msg.name),
            gate_import="flat_gate, ",
            gate_def=_FLAT_GATE.format(name_lit=repr(msg.name), hash_lit=repr(msg.md5Hash)))

    def _render_bringup(self, tables):
        imports = "from harpia_generated.rest import (\n{})\n".format("".join(
            "    {},\n".format(mod) for mod in sorted(
                "{}_{}_rest".format(m.name, m.md5Hash) for m in tables)))
        registrations = "".join(
            "        {}_{}_rest.register(self.router, pool, rest_base)\n".format(
                m.name, m.md5Hash) for m in tables).rstrip("\n")
        return _BRINGUP.format(imports=imports.rstrip("\n"), registrations=registrations,
                               rest_names=repr(tuple(m.name for m in tables)))
