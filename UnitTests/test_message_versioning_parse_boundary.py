"""Integration tests for plans/message-versioning.md S4 "Parse-boundary
hardening":

  - an unrecognized field must never be a parse error (proto3 binary/XML
    already did this; JSON adapter's from_json/is_valid_json did NOT --
    google::protobuf::util::JsonStringToMessage defaults
    ignore_unknown_fields to false, so a plain single-arg call rejected any
    JSON carrying a key the schema doesn't know -- see
    JsonAdapter/templates/adapter.h.tmpl).
  - a proto3 default value (0, "", false) is ambiguous between "explicitly
    set to that" and "field absent from the sender's schema"; DSL `optional`
    fields need this distinguishable via a real has_<field>() accessor, not
    just the raw (always-tolerant) zero value -- this requires FileCreator.py
    to actually emit proto3's `optional` keyword (it previously didn't: the
    DSL's OPTIONAL modifier was parsed and then silently dropped past the
    lexer, see Message/CLAUDE.md), and the XML runtime's write path to gate
    on real field presence (any field with FieldDescriptor::has_presence()),
    not only composed-message fields, so presence survives an XML round trip
    too.

Complements UnitTests/test_message_versioning_wire.py (S3's old/new-schema wire
round-trip): this covers the DIFFERENT direction (a newer schema's extra
field reaching an older-schema reader) plus the presence-tracking half of S4
that S3 doesn't touch at all.

Needs protoc + g++ + pkg-config(protobuf) -- run inside the harpia Docker
image:

    Docker/run.sh pytest UnitTests/test_message_versioning_parse_boundary.py
"""
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "pkg-config")),
    reason="needs protoc + g++ + protobuf (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Front-end + Stage 7 against HarpiaTest/test.harpia, which already
    declares `optional string name;` on `vip_users` (test.harpia:65)."""
    out = tmp_path_factory.mktemp("harpia_parseboundary")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "json_dir": os.path.join(cpp_root, "json"),
        "xml_dir": os.path.join(cpp_root, "xml"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _pb_cc(built, name):
    return os.path.join(built["proto_dir"], "{}_{}.pb.cc".format(name, HASH))


def _build_and_run(tmp_path, sources, extra_includes, extra_libs, name):
    cflags = _pkgconfig("--cflags")
    libs = _pkgconfig("--libs")
    binary = str(tmp_path / name)
    cmd = (["g++", "-std=c++17"]
           + [x for inc in extra_includes for x in ("-I", inc)]
           + cflags + list(sources) + ["-o", binary]
           + list(extra_libs) + libs)
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    r = subprocess.run([binary], capture_output=True, text=True)
    return r


def test_unknown_json_field_is_ignored(built, tmp_path):
    """A JSON payload with a key vip_users doesn't declare (a newer peer's
    added field) must still parse -- ignore_unknown_fields must be on."""
    json_header = "vip_users_{}_json.h".format(HASH)
    assert os.path.exists(os.path.join(built["json_dir"], json_header))

    prog = tmp_path / "unknown_field.cc"
    prog.write_text(
        '#include "json/{header}"\n'
        "#include <string>\n"
        "int main() {{\n"
        '    const std::string in = "{{\\"family\\":\\"smith\\",'
        '\\"totallyUnknownField\\":42}}";\n'
        "    ::vip_users m;\n"
        "    if (!harpia::json::from_json(in, &m)) return 1;\n"
        '    if (m.family() != "smith") return 2;\n'
        "    if (!harpia::json::is_valid_json(in)) return 3;\n"
        "    return 0;\n"
        "}}\n".format(header=json_header),
        encoding="utf-8",
    )
    r = _build_and_run(tmp_path, [str(prog), _pb_cc(built, "vip_users")],
                       [built["cpp_root"]], [], "unknown_field")
    assert r.returncode == 0, (
        "exit {} (1/3=from_json/is_valid_json rejected the unknown field, "
        "2=known field 'family' didn't survive)".format(r.returncode))


def test_optional_field_presence_survives_binary_round_trip(built, tmp_path):
    """`optional string name` must expose a real has_name() distinct from
    the zero value -- absent vs. explicitly set to the empty string."""
    prog = tmp_path / "presence.cc"
    prog.write_text(
        '#include "protofiles/vip_users_{h}.pb.h"\n'
        "#include <string>\n"
        "int main() {{\n"
        "    ::vip_users a;\n"
        '    a.set_family("smith");\n'  # name left unset
        "    std::string bytes;\n"
        "    if (!a.SerializeToString(&bytes)) return 1;\n"
        "    ::vip_users b;\n"
        "    if (!b.ParseFromString(bytes)) return 2;\n"
        "    if (b.has_name()) return 3;\n"  # never set -> no presence
        '    if (b.name() != "") return 4;\n'  # still reads as the default
        "\n"
        "    ::vip_users c;\n"
        '    c.set_name("");\n'  # explicitly set to the zero value
        '    c.set_family("smith");\n'
        "    if (!c.SerializeToString(&bytes)) return 5;\n"
        "    ::vip_users d;\n"
        "    if (!d.ParseFromString(bytes)) return 6;\n"
        "    if (!d.has_name()) return 7;\n"  # explicit -> presence survives
        "    return 0;\n"
        "}}\n".format(h=HASH),
        encoding="utf-8",
    )
    r = _build_and_run(tmp_path, [str(prog), _pb_cc(built, "vip_users")],
                       [built["cpp_root"]], [], "presence")
    assert r.returncode == 0, "exit code {}".format(r.returncode)


def test_optional_field_presence_survives_xml_round_trip(built, tmp_path):
    """Same absent-vs-explicit-default distinction, through to_xml/from_xml
    (harpia_xml.h's hand-rolled reflection walk, not protobuf's own JSON
    machinery) -- proves the has_presence() write-side fix actually closes
    the gap, not just the binary path protobuf already handled for free."""
    tinyxml = os.path.join(REPO_ROOT, "third_party", "tinyxml2", "tinyxml2.cpp")
    tinyxml_inc = os.path.join(REPO_ROOT, "third_party", "tinyxml2")

    prog = tmp_path / "xml_presence.cc"
    prog.write_text(
        '#include "xml/vip_users_{h}_xml.h"\n'
        "#include <string>\n"
        "int main() {{\n"
        "    ::vip_users a;\n"
        '    a.set_family("smith");\n'  # name left unset
        "    std::string xml = harpia::xml::to_xml(a);\n"
        '    if (xml.find("<name>") != std::string::npos) return 1;\n'
        "    ::vip_users b;\n"
        "    if (!harpia::xml::from_xml(xml, &b)) return 2;\n"
        "    if (b.has_name()) return 3;\n"
        "\n"
        "    ::vip_users c;\n"
        '    c.set_name("");\n'
        '    c.set_family("smith");\n'
        "    xml = harpia::xml::to_xml(c);\n"
        '    if (xml.find("<name>") == std::string::npos) return 4;\n'
        "    ::vip_users d;\n"
        "    if (!harpia::xml::from_xml(xml, &d)) return 5;\n"
        "    if (!d.has_name()) return 6;\n"
        "    return 0;\n"
        "}}\n".format(h=HASH),
        encoding="utf-8",
    )
    r = _build_and_run(
        tmp_path, [str(prog), _pb_cc(built, "vip_users"), tinyxml],
        [built["cpp_root"], tinyxml_inc], [], "xml_presence")
    assert r.returncode == 0, "exit code {}".format(r.returncode)


def _run_main(root_file, include_folder, output_dir):
    env = dict(os.environ, HARPIA_OUTPUT_DIR=output_dir,
              HARPIA_INPUT_FILE=root_file,
              HARPIA_INCLUDE_FOLDER=include_folder)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr


def _pb_paths(output_dir, name, root_hash):
    base = os.path.join(output_dir, "generated", "cpp", "protofiles",
                        "{}_{}.pb".format(name, root_hash))
    return base + ".h", base + ".cc"


def test_newer_schemas_extra_field_ignored_by_older_reader(tmp_path):
    """The inverse direction of test_message_versioning_wire.py: a NEWER
    schema's writer emits a field an OLDER schema's reader has never heard
    of. Proto3 binary parsing must silently ignore it, not error."""
    root = tmp_path / "root.harpia"
    root.write_text('import "inc.harpia";\n', encoding="utf-8")
    inc = tmp_path / "inc.harpia"
    inc.write_text("message pong {\nint a;\n};\n", encoding="utf-8")
    root_hash = hashlib.md5(root.read_bytes()).hexdigest()

    outOld = str(tmp_path / "out_old")
    _run_main(str(root), str(tmp_path), outOld)
    hOld, ccOld = _pb_paths(outOld, "pong", root_hash)

    # newer generation: adds field "b" (schema_registry keeps "a"'s number
    # stable, "b" gets a fresh one -- unrelated to this test's own concern,
    # already covered by UnitTests/test_fieldmap*.py and test_message_versioning_wire.py).
    inc.write_text("message pong {\nint a;\nint b;\n};\n", encoding="utf-8")
    outNew = str(tmp_path / "out_new")
    _run_main(str(root), str(tmp_path), outNew)
    hNew, ccNew = _pb_paths(outNew, "pong", root_hash)

    writer_src = tmp_path / "writer_new.cc"
    writer_src.write_text(
        '#include "protofiles/{header}"\n'
        "#include <fstream>\n"
        "int main(int argc, char** argv) {{\n"
        "    ::pong m;\n"
        "    m.set_a(11);\n"
        "    m.set_b(22);\n"  # the field the OLD schema has never heard of
        "    std::ofstream out(argv[1], std::ios::binary);\n"
        "    return m.SerializeToOstream(&out) ? 0 : 1;\n"
        "}}\n".format(header=os.path.basename(hNew)),
        encoding="utf-8",
    )
    reader_src = tmp_path / "reader_old.cc"
    reader_src.write_text(
        '#include "protofiles/{header}"\n'
        "#include <fstream>\n"
        "int main(int argc, char** argv) {{\n"
        "    ::pong m;\n"
        "    std::ifstream in(argv[1], std::ios::binary);\n"
        "    if (!m.ParseFromIstream(&in)) return 1;\n"
        "    if (m.a() != 11) return 2;\n"
        "    return 0;\n"
        "}}\n".format(header=os.path.basename(hOld)),
        encoding="utf-8",
    )

    cflags = _pkgconfig("--cflags")
    libs = _pkgconfig("--libs")
    writer_bin = str(tmp_path / "writer_new")
    reader_bin = str(tmp_path / "reader_old")

    c = subprocess.run(
        ["g++", "-std=c++17", "-I", os.path.join(outNew, "generated", "cpp"),
         *cflags, str(writer_src), ccNew, "-o", writer_bin, *libs],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "writer (new schema) failed to build:\n" + c.stderr

    c = subprocess.run(
        ["g++", "-std=c++17", "-I", os.path.join(outOld, "generated", "cpp"),
         *cflags, str(reader_src), ccOld, "-o", reader_bin, *libs],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "reader (old schema) failed to build:\n" + c.stderr

    wire_file = str(tmp_path / "wire.bin")
    r = subprocess.run([writer_bin, wire_file], capture_output=True, text=True)
    assert r.returncode == 0, "writer (new schema) failed to serialize"

    r = subprocess.run([reader_bin, wire_file], capture_output=True, text=True)
    assert r.returncode == 0, (
        "reader (old schema) failed on a message carrying an unrecognized "
        "trailing field -- exit code {} (2=known field 'a' corrupted)"
        .format(r.returncode)
    )
