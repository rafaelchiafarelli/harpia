"""Integration test for plans/message-versioning.md S3's "old-schema binary /
new-schema binary exchange messages over the real (de)serialization path"
requirement -- the one piece of S3's test list not covered by
UnitTests/test_fieldmap.py (drives FieldMap.freeze directly) or
UnitTests/test_fieldmap_frontend.py (drives the real front-end, but only
inspects the sidecar -- never actually serializes a byte on the wire).

Runs main.py twice against the SAME root .harpia file (so the same
schema_registry sidecar is read/extended both times), with the second run's
imported file reordering the message's existing fields AND adding a new one.
Without field-number freezing (Message/FieldMap.py), declaration-order
numbering would silently reassign "a"/"b"'s wire numbers between the two
generations -- an old peer would then misread a newer message's bytes as its
own fields, wrong values with no parse error. Compiles gen1's protobuf class
into a small "writer" program and gen2's (differently-ordered, one-field-
larger) protobuf class into a separate "reader" program, and proves a real
serialized message survives the round trip: fields present in both schemas
decode to their original values regardless of the reorder, and the field
absent from the wire (the one only gen2 declares) decodes to its proto3
default rather than colliding with "a" or "b".

Needs protoc + g++ + pkg-config(protobuf) -- run inside the harpia Docker
image:

    Docker/run.sh pytest UnitTests/test_message_versioning_wire.py
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None or shutil.which("g++") is None,
    reason="needs protoc + g++ (run inside the harpia Docker image)",
)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _run_main(root_file, include_folder, output_dir):
    env = dict(os.environ, HARPIA_OUTPUT_DIR=output_dir,
              HARPIA_INPUT_FILE=root_file,
              HARPIA_INCLUDE_FOLDER=include_folder)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _pb_paths(output_dir, name, root_hash):
    base = os.path.join(output_dir, "generated", "cpp", "protofiles",
                        "{}_{}.pb".format(name, root_hash))
    return base + ".h", base + ".cc"


def test_reordered_and_extended_schema_decodes_shared_fields_correctly(tmp_path):
    root = tmp_path / "root.harpia"
    root.write_text('import "inc.harpia";\n', encoding="utf-8")
    inc = tmp_path / "inc.harpia"
    # generation 1: two user fields, declared a, b.
    inc.write_text("message ping {\nint a;\nint b;\n};\n", encoding="utf-8")

    # root.harpia's own text (not inc.harpia's) drives the md5 that qualifies
    # every generated filename -- and stays constant across both runs below,
    # since only inc.harpia changes. schema_registry/ is keyed off root.harpia
    # too (message.file is always the ROOT file -- see Message/CLAUDE.md), so
    # both generations read/write the exact same sidecar.
    root_hash = hashlib.md5(root.read_bytes()).hexdigest()

    out1 = str(tmp_path / "out1")
    _run_main(str(root), str(tmp_path), out1)
    h1, cc1 = _pb_paths(out1, "ping", root_hash)
    assert os.path.exists(h1) and os.path.exists(cc1)

    # generation 2: b declared before a, plus a new field c -- without
    # Message/FieldMap.py's freeze, straight declaration-order numbering
    # would give b/c/a wire numbers 2/3/4 here vs. a/b's 2/3 in generation 1.
    inc.write_text("message ping {\nint b;\nint c;\nint a;\n};\n", encoding="utf-8")

    out2 = str(tmp_path / "out2")
    _run_main(str(root), str(tmp_path), out2)
    h2, cc2 = _pb_paths(out2, "ping", root_hash)
    assert os.path.exists(h2) and os.path.exists(cc2)

    header2 = os.path.basename(h2)

    writer_src = tmp_path / "writer.cc"
    writer_src.write_text(
        '#include "protofiles/{header}"\n'
        "#include <fstream>\n"
        "int main(int argc, char** argv) {{\n"
        "    ::ping m;\n"
        "    m.set_a(42);\n"
        "    m.set_b(7);\n"
        "    std::ofstream out(argv[1], std::ios::binary);\n"
        "    if (!m.SerializeToOstream(&out)) return 1;\n"
        "    return 0;\n"
        "}}\n".format(header=os.path.basename(h1)),
        encoding="utf-8",
    )
    reader_src = tmp_path / "reader.cc"
    reader_src.write_text(
        '#include "protofiles/{header}"\n'
        "#include <fstream>\n"
        "int main(int argc, char** argv) {{\n"
        "    ::ping m;\n"
        "    std::ifstream in(argv[1], std::ios::binary);\n"
        "    if (!m.ParseFromIstream(&in)) return 1;\n"
        "    if (m.a() != 42) return 2;\n"
        "    if (m.b() != 7) return 3;\n"
        # c was never on the wire (gen1 doesn't declare it) -> proto3 default
        "    if (m.c() != 0) return 4;\n"
        "    return 0;\n"
        "}}\n".format(header=header2),
        encoding="utf-8",
    )

    cflags = _pkgconfig("--cflags")
    libs = _pkgconfig("--libs")
    cpp_root1 = os.path.join(out1, "generated", "cpp")
    cpp_root2 = os.path.join(out2, "generated", "cpp")

    writer_bin = str(tmp_path / "writer")
    reader_bin = str(tmp_path / "reader")

    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root1, *cflags,
         str(writer_src), cc1, "-o", writer_bin, *libs],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "writer failed to build:\n" + c.stderr

    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root2, *cflags,
         str(reader_src), cc2, "-o", reader_bin, *libs],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "reader failed to build:\n" + c.stderr

    wire_file = str(tmp_path / "wire.bin")
    r = subprocess.run([writer_bin, wire_file], capture_output=True, text=True)
    assert r.returncode == 0, "writer (gen1 schema) failed to serialize"

    r = subprocess.run([reader_bin, wire_file], capture_output=True, text=True)
    assert r.returncode == 0, (
        "reader (gen2 schema, reordered + extended) failed to decode the "
        "gen1 message correctly -- exit code {} (2=a mismatch, 3=b mismatch, "
        "4=c not default)".format(r.returncode)
    )
