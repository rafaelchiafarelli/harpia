"""The generated Python project's runtime dependencies -- declared once.

Single source of truth for both the ``pyproject.toml`` ``PyAdapter`` renders
(``dependencies`` / ``[project.optional-dependencies]``) and the Python
components ``ComplianceReport`` lists in ``bom.json`` (python-target /
py-artifacts task 1) -- the "declare, don't infer" rule: nothing is scraped
back out of the rendered file.
"""
from collections import namedtuple

#: one PyPI distribution: its name, the version specifier the generated
#: project declares, the optional extra it sits in (``None`` = always
#: installed) and what it is for
PyDependency = namedtuple("PyDependency", "name specifier extra description")

RUNTIME_DEPENDENCIES = (
    PyDependency("protobuf", ">=4.21.12,<5", None,
                 "Protocol Buffers Python runtime -- every generated message"),
    PyDependency("grpcio", ">=1.51.1,<2", None,
                 "gRPC Python runtime -- generated servicers, capability "
                 "handshake, mTLS"),
    PyDependency("pyzmq", ">=24.0.1,<27", "zmq",
                 "ZeroMQ Python binding -- ZMQ transports, CURVE + ZAP"),
    PyDependency("psycopg", ">=3.1.17,<4", "postgres",
                 "PostgreSQL driver -- the postgresql DAO dialect"),
    PyDependency("cyclonedds", "==0.10.5", "dds",
                 "Eclipse Cyclone DDS Python binding -- DDS transport + "
                 "DDS-Security"),
)

#: the generated test suite's tooling (an extra, not a runtime dependency)
TEST_DEPENDENCIES = (
    PyDependency("pytest", ">=7", "test",
                 "the generated per-message suite under tests/"),
)


def pyproject_fills():
    """``{dependencies}`` / ``{extras}`` for ``pyproject.toml.tmpl``."""
    deps = "".join('    "{}{}",\n'.format(d.name, d.specifier)
                   for d in RUNTIME_DEPENDENCIES if d.extra is None)
    extras = []
    for d in RUNTIME_DEPENDENCIES + TEST_DEPENDENCIES:
        if d.extra is None:
            continue
        if d in TEST_DEPENDENCIES:
            extras.append("# the generated per-message suite under tests/ (py-tests)")
        extras.append('{} = ["{}{}"]'.format(d.extra, d.name, d.specifier))
    return {"dependencies": deps.rstrip("\n"), "extras": "\n".join(extras)}
