"""Tests for session J.1 (initiatives/multi-language-targets/thread-1-java-
target/histories/gRPC-wiring/codegen-timing-decision.md): `.proto` option
emission for the future Java target.

Java's protoc plugin packs every message declared in one .proto file into a
single outer wrapper class by default. harpia's convention is one message per
.proto (hash-qualified filename), so `FileCreator.py` now emits `option
java_multiple_files = true;` + `option java_package = "...";` on every
message .proto -- unconditionally, since both are standard descriptor.proto
FileOptions that every non-Java protoc backend (i.e. today's C++ target)
ignores.

  - Unit: the emitted .proto for a multi-message file carries the new
    options.
  - Integration (protoc-gated): the emitted .proto is still valid protobuf
    syntax -- protoc parses it without error.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from protoFile.FileCreator import JAVA_PACKAGE  # noqa: E402
RUNNER = os.path.join(HERE, "run_phi_check.py")


def _run(tmp_path, contents):
    src = tmp_path / "case.harpia"
    src.write_text(contents, encoding="utf-8")
    dest = tmp_path / "dest"
    r = subprocess.run(
        [sys.executable, RUNNER, str(src), str(dest)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, "run_phi_check.py crashed:\n" + r.stdout + r.stderr
    lines = [ln[len("PHI_CHECK_RESULT "):] for ln in r.stdout.splitlines()
             if ln.startswith("PHI_CHECK_RESULT ")]
    assert len(lines) == 1, "expected one PHI_CHECK_RESULT line, got:\n" + r.stdout
    return json.loads(lines[0])


_MULTI_MESSAGE = "message m1 {\nint a;\n};\nmessage m2 {\nstring b;\n};\n"


def test_every_message_proto_carries_java_options(tmp_path):
    result = _run(tmp_path, _MULTI_MESSAGE)
    assert result["error"] is None
    proto_text = result["proto"]
    assert proto_text.count("option java_multiple_files = true;") == 2
    assert proto_text.count(
        'option java_package = "{}";'.format(JAVA_PACKAGE)) == 2


def test_options_precede_message_body(tmp_path):
    result = _run(tmp_path, "message m {\nint a;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert proto.index("option java_multiple_files") < proto.index("message m {")
    assert proto.index("option java_package") < proto.index("message m {")


@pytest.mark.skipif(shutil.which("protoc") is None,
                     reason="protoc not on PATH (run inside the harpia Docker image)")
def test_emitted_proto_is_valid_protobuf_syntax(tmp_path):
    result = _run(tmp_path, _MULTI_MESSAGE)
    assert result["error"] is None
    # run_phi_check.py's "proto" field is every message's OWN complete .proto
    # text concatenated (documented in tests/CLAUDE.md) -- harpia emits one
    # message per real .proto file, each carrying its own `syntax = ...;`
    # header, so a naive single-file write duplicates that header and protoc
    # correctly rejects it. Split back into per-message chunks (each starts
    # with its own `syntax = ` line) and validate each as its own file,
    # matching how these are actually consumed.
    chunks = ["syntax = " + c for c in result["proto"].split("syntax = ") if c.strip()]
    assert len(chunks) >= 2, "expected at least 2 messages in the concatenated proto"
    for i, chunk in enumerate(chunks):
        proto_path = tmp_path / "multi_{}.proto".format(i)
        proto_path.write_text(chunk, encoding="utf-8")
        r = subprocess.run(
            ["protoc", "-I", str(tmp_path), "--descriptor_set_out",
             str(tmp_path / "out_{}.pb".format(i)), str(proto_path)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "protoc rejected {}:\n{}".format(proto_path.name, r.stderr)
