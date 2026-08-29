"""Declared runtime-dependency manifest for the generated project's SBOM.

The `ComplianceReport/` SBOM enumerates what a device built with Harpia
actually links against, not the generator's own toolchain. That set is
*declared* here rather than scraped out of the generated CMake — the same
standing rule the rest of the initiative follows: anything that should be an
explicit declaration is not inferred.

Two kinds of component:
  - **vendored** — checked in under `third_party/<dir>/`, each with a
    `VENDORED.md` carrying `- **Version:** X`, `- **Source:** <url>` and
    `- **License:** <name>` lines. Those files are the source of truth.
  - **environment** — provided by the build toolchain (protobuf, gRPC,
    ZeroMQ come from the system / Docker image, not `third_party/`).
    Resolved by asking the toolchain; `"unknown"` when it can't be asked.

Every resolver falls back to the string ``UNKNOWN`` — a component is never
dropped from the SBOM and a resolver never raises.
"""
import os
import re
import subprocess

UNKNOWN = "unknown"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_THIRD_PARTY = os.path.join(_REPO_ROOT, "third_party")

# (component name, third_party/<dir>, purl type, description)
VENDORED = [
    ("asio", "asio", "github",
     "standalone Asio (no Boost) -- transport library Crow is built on"),
    ("crow", "crow", "github",
     "Crow header-only HTTP server framework -- REST (Stage 12) / SOAP (Stage 11)"),
    ("sqlite", "sqlite", "generic",
     "SQLite amalgamation -- generated persistence / CRUDL layer (Stage 8)"),
    ("tinyxml2", "tinyxml2", "github",
     "TinyXML-2 -- XML adapter (Stage 10)"),
    ("cyclonedds", "cyclonedds", "github",
     "Eclipse Cyclone DDS -- DDS transport for the dds-transport epic "
     "(ASTM F2761 / OpenICE-class bedside bus); built in the toolchain "
     "image from this vendored snapshot"),
    ("cyclonedds-cxx", "cyclonedds-cxx", "github",
     "Eclipse Cyclone DDS ddscxx -- the ISO C++ DDS binding layered over "
     "cyclonedds"),
]

# (component name, purl type, description, [ [cmd, ...], ... ] tried in order)
ENVIRONMENT = [
    ("protobuf", "generic",
     "Protocol Buffers runtime + protoc -- every generated message",
     [["protoc", "--version"],
      ["pkg-config", "--modversion", "protobuf"]]),
    ("grpc", "generic",
     "gRPC C++ runtime -- generated service stubs (Stage 13)",
     [["pkg-config", "--modversion", "grpc++"],
      ["pkg-config", "--modversion", "grpc"]]),
    ("libzmq", "generic",
     "ZeroMQ -- generated ZMQ transport adapters (Stage 13 zmq)",
     [["pkg-config", "--modversion", "libzmq"]]),
]

_VER_RE = re.compile(r"(\d+(?:\.\d+){1,3})")


def _vendored_md(sub):
    path = os.path.join(_THIRD_PARTY, sub, "VENDORED.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return ""


def _field(md_text, label):
    """Value of a `- **<label>:** <value>` line in a VENDORED.md, truncated
    at the first ``(`` or ``;`` -- the VENDORED.md lines carry a short value
    then a parenthetical / semicolon aside ("3.46.1 (amalgamation)",
    "BSD-3-Clause (see LICENSE; ...)"), sometimes wrapping onto the next
    line, which the single-line match already drops."""
    m = re.search(r"^- \*\*{}:\*\*\s*(.+)$".format(re.escape(label)),
                  md_text, re.MULTILINE)
    if not m:
        return ""
    return re.split(r"[(;]", m.group(1))[0].strip()


def vendored_version(sub):
    v = _field(_vendored_md(sub), "Version")
    return v or UNKNOWN


def vendored_license(sub):
    # "Boost Software License 1.0 (see LICENSE)" -> "Boost Software License 1.0"
    return _field(_vendored_md(sub), "License")


def vendored_source(sub):
    raw = _field(_vendored_md(sub), "Source")
    m = re.search(r"https?://\S+", raw)
    return m.group(0).rstrip(").,") if m else ""


def environment_version(cmd_list):
    for cmd in cmd_list:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0:
            continue
        m = _VER_RE.search((out.stdout or "") + " " + (out.stderr or ""))
        if m:
            return m.group(1)
    return UNKNOWN
