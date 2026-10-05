"""python-target / tri-language-interop task 4: serialization byte-parity
across C++, Java and Python.

Every fixture message (``_py_cpp_parity.fixture_messages``: table messages,
service wrappers, enums' carriers...) in three variants -- populated (stress
strings, int64 > 2^53), empty, sparse (``test_py_xml._variants``) --
serialized by the three runtimes:

- **XML / YAML**: C++ == Python byte for byte (the ``py-serialization`` bar
  over the whole fixture). Java XML (``HarpiaXml``) == C++ byte for byte too
  (java-xml-byte-parity-DEFECT; ``JAVA_XML_DIFFERENCES`` is empty and the
  three former classes -- ``<x/>`` empties, unescaped quotes, float
  spelling -- each have a focused test). Each language's
  XML also parses back to the original in the other two. Java has no YAML.
- **JSON**: every language's JSON parses to the original message in the
  other two (all six directions); C++ == Python byte for byte; the Java
  byte differences are classed in ``JSON_BYTE_DIFFERENCES`` (whitespace only:
  the parsed objects are equal, and so are their compact re-serializations).
- **redacted ``to_string``** for the phi messages (the generated
  ``phi_registry``), all three formats, redaction on: C++ == Python.

C++ through ``_py_cpp_parity.probe``; Java through a batch probe over a
java-target generation of the same schema (``xlang.SerProbe``). Gated on g++
+ protobuf, gradle + JDK and the Python toolchain.
"""
import importlib
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests._java_gradle_helpers import build_and_classpath, generate  # noqa: E402
from UnitTests.test_py_serialize import _lab  # noqa: E402
from UnitTests.test_py_xml import _variants  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (P.HAVE_CPP and shutil.which("gradle") and shutil.which("java")),
    reason=P.SKIP_CPP + " + gradle+JDK")

VARIANTS = ("populated", "empty", "sparse")

# Java XML is byte-identical to C++ (and Python) since java-xml-byte-parity-
# DEFECT; the three former difference classes (<x/> empties, unescaped
# quotes, Float.toString floats) each have a focused test at the end of this
# file. xml_difference_classes stays as the diagnostic for a regression.
JAVA_XML_DIFFERENCES = {}

# Every C++/Java JSON byte difference falls in these classes (the parsed
# objects are equal in every case; C++ == Python byte for byte).
JSON_BYTE_DIFFERENCES = {
    "whitespace": "Java's JsonFormat printer pretty-prints (newlines, indent, "
                  "\": \"); C++ / Python are compact",
}


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("ser_x3"))


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


_JAVA = r'''
package xlang;

import com.google.protobuf.Message;
import com.harpia.runtime.json.HarpiaJson;
import com.harpia.runtime.xml.HarpiaXml;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

// stdin: <op>\t<simple type name>\t<hex>; stdout: OK <hex> | FAIL <why>
public class SerProbe {
    static byte[] unhex(String h) {
        byte[] b = new byte[h.length() / 2];
        for (int i = 0; i < b.length; i++)
            b[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return b;
    }

    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x & 0xff));
        return s.toString();
    }

    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            String[] p = line.split("\t", -1);
            String out;
            try {
                Class<?> cls = Class.forName("com.harpia.generated." + p[1]);
                byte[] arg = unhex(p[2]);
                Message.Builder b = (Message.Builder) cls.getMethod("newBuilder").invoke(null);
                switch (p[0]) {
                    case "to_xml": case "to_json": {
                        Message m = b.mergeFrom(arg).build();
                        String text = p[0].equals("to_xml") ? HarpiaXml.toXml(m)
                                                            : HarpiaJson.toJson(m);
                        out = "OK " + hex(text.getBytes(StandardCharsets.UTF_8));
                        break;
                    }
                    case "from_xml": {
                        String text = new String(arg, StandardCharsets.UTF_8);
                        out = HarpiaXml.fromXml(text, b) ? "OK " + hex(b.build().toByteArray())
                                                         : "FAIL parse";
                        break;
                    }
                    default: {
                        String text = new String(arg, StandardCharsets.UTF_8);
                        out = "OK " + hex(HarpiaJson.fromJson(text, b).build().toByteArray());
                    }
                }
            } catch (ClassNotFoundException e) {
                out = "FAIL notype";
            } catch (Throwable e) {
                out = "FAIL " + e.toString().replace('\n', ' ');
            }
            System.out.println(out);
            System.out.flush();
        }
    }
}
'''


@pytest.fixture(scope="module")
def java(tmp_path_factory):
    g = generate(tmp_path_factory.mktemp("ser_x3_java"), lang="java")
    return build_and_classpath(os.path.join(g, "java"), {"xlang/SerProbe.java": _JAVA})


def java_run(cp, requests):
    """[(op, full type name, bytes)] -> [(ok, bytes | reason)]"""
    lines = "".join("{}\t{}\t{}\n".format(op, typ.rsplit(".", 1)[-1], payload.hex())
                    for op, typ, payload in requests)
    r = subprocess.run(["java", "-cp", cp, "xlang.SerProbe"], input=lines, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    out = []
    for line in r.stdout.splitlines():
        status, _, rest = line.partition(" ")
        out.append((True, bytes.fromhex(rest)) if status == "OK" else (False, rest))
    assert len(out) == len(requests), r.stdout[-2000:] + r.stderr[-2000:]
    return out


@pytest.fixture(scope="module")
def cases(msgs, java):
    """[(name, variant, message)] over every fixture message Java has a class
    for; the rest (``capabilities_service``'s, not copied into java/) is
    asserted to be exactly that."""
    out = [(n, v, m) for n, ms in _variants(msgs).items() for v, m in zip(VARIANTS, ms)]
    res = java_run(java, [("to_json", n, m.SerializeToString()) for n, v, m in out
                          if v == "empty"])
    missing = {n for (n, v, _), (ok, why) in zip([c for c in out if c[1] == "empty"], res)
               if not ok and why == "notype"}
    assert missing and all("capabilities" in n for n in missing), missing
    return [c for c in out if c[0] not in missing]


def _is_float(text):
    try:
        float(text)
        return "." in text
    except (TypeError, ValueError):
        return False


def _tree_diff(a, b, floats):
    """Where two parsed XML trees differ, ignoring float spelling (recorded
    in ``floats``); None if equal."""
    if a.tag != b.tag or len(a) != len(b):
        return "{} / {}".format(a.tag, b.tag)
    ta, tb = a.text or "", b.text or ""
    if ta != tb:
        if _is_float(ta) and _is_float(tb) and float(ta) == float(tb):
            floats.append(a.tag)
        else:
            return "{}: {!r} / {!r}".format(a.tag, ta, tb)
    for x, y in zip(a, b):
        d = _tree_diff(x, y, floats)
        if d:
            return d
    return None


def xml_difference_classes(cpp, java):
    """The JAVA_XML_DIFFERENCES classes explaining ``cpp`` != ``java``, or
    ``{"other: ..."}``."""
    import re
    import xml.etree.ElementTree as ET
    floats = []
    other = _tree_diff(ET.fromstring(cpp), ET.fromstring(java), floats)
    if other:
        return {"other: " + other}
    out = set()
    if re.search(r"<[^<>/]+/>", java) and not re.search(r"<[^<>/]+/>", cpp):
        out.add("empty element")
    if ("&quot;" in cpp or "&apos;" in cpp) and "&quot;" not in java and "&apos;" not in java:
        out.add("quotes")
    if floats:
        out.add("float text")
    return out or {"other: unexplained byte difference"}


def json_difference_classes(cpp, java):
    import json
    if json.loads(cpp) != json.loads(java):
        return {"other: objects differ"}
    compact = json.dumps(json.loads(java), separators=(",", ":"))
    return {"whitespace"} if compact == json.dumps(json.loads(cpp), separators=(",", ":")) \
        and "\n" in java else {"other: token text"}


# -- XML ------------------------------------------------------------------------

def test_xml(gen, msgs, java, cases):
    x = importlib.import_module("harpia_runtime.xml")
    reqs = [("to_xml", n, m.SerializeToString()) for n, _, m in cases]
    cpp, jv = P.run(gen, reqs), java_run(java, reqs)
    seen = set()
    for (name, variant, m), (cok, ctext), (jok, jtext) in zip(cases, cpp, jv):
        assert cok and jok, (name, variant, jtext)
        ctext, jtext = ctext.decode(), jtext.decode()
        assert x.to_xml(m) == ctext, (name, variant)
        if jtext != ctext:
            seen |= xml_difference_classes(ctext, jtext)
    assert seen == set(JAVA_XML_DIFFERENCES), seen  # Java == C++ byte for byte

    # each language's XML parses back to the original in the other two
    populated = [(n, m) for n, v, m in cases if v == "populated"]
    texts = {"cpp": [t for (n, v, _), (_, t) in zip(cases, cpp) if v == "populated"],
             "java": [t for (n, v, _), (_, t) in zip(cases, jv) if v == "populated"],
             "python": [x.to_xml(m).encode() for _, m in populated]}
    for src, blobs in texts.items():
        reqs = [("from_xml", n, t) for (n, _), t in zip(populated, blobs)]
        for reader in {"cpp", "java", "python"} - {src}:
            if reader == "python":
                got = []
                for (n, _), t in zip(populated, blobs):
                    back = msgs[n]()
                    got.append((x.from_xml(t.decode(), back), back.SerializeToString()))
            else:
                got = P.run(gen, reqs) if reader == "cpp" else java_run(java, reqs)
            for (n, m), (ok, data) in zip(populated, got):
                assert ok and msgs[n].FromString(data) == m, (src, reader, n)


# -- YAML -----------------------------------------------------------------------

def test_yaml_cpp_equals_python(gen, cases):
    y = importlib.import_module("harpia_runtime.yaml")
    res = P.run(gen, [("to_yaml", n, m.SerializeToString()) for n, _, m in cases])
    for (name, variant, m), (ok, text) in zip(cases, res):
        assert ok and text.decode() == y.to_yaml(m), (name, variant)


# -- JSON -----------------------------------------------------------------------

def test_json_cross_parse_and_byte_differences(gen, msgs, java, cases):
    js = importlib.import_module("harpia_runtime.json")
    reqs = [("to_json", n, m.SerializeToString()) for n, _, m in cases]
    texts = {"cpp": [t for _, t in P.run(gen, reqs)],
             "java": [t for _, t in java_run(java, reqs)],
             "python": [js.to_json(m).encode() for _, _, m in cases]}
    seen = set()
    for i, (name, variant, _) in enumerate(cases):
        assert texts["cpp"][i] == texts["python"][i], (name, variant)
        if texts["java"][i] != texts["cpp"][i]:
            classes = json_difference_classes(texts["cpp"][i].decode(),
                                              texts["java"][i].decode())
            assert classes <= set(JSON_BYTE_DIFFERENCES), (name, variant, classes)
            seen |= classes
    assert seen == set(JSON_BYTE_DIFFERENCES)

    for src, blobs in texts.items():
        reqs = [("from_json", n, t) for (n, _, _), t in zip(cases, blobs)]
        for reader in {"cpp", "java", "python"} - {src}:
            if reader == "python":
                got = []
                for (n, _, _), t in zip(cases, blobs):
                    back = msgs[n]()
                    got.append((js.from_json(t.decode(), back), back.SerializeToString()))
            else:
                got = P.run(gen, reqs) if reader == "cpp" else java_run(java, reqs)
            for (n, v, m), (ok, data) in zip(cases, got):
                assert ok and msgs[n].FromString(data) == m, (src, reader, n, v)


# -- redacted to_string ---------------------------------------------------------------

def test_redacted_to_string_cpp_equals_python(gen, msgs, cases):
    ser = importlib.import_module("harpia_runtime.serialize")
    red = importlib.import_module("harpia_runtime.redaction")
    reg = importlib.import_module("harpia_generated.serialize.phi_registry")
    red.set_redaction_enabled(True)
    phi = {name for name, _ in reg.PHI_FIELDS}
    assert phi == {"patient_vitals", "alarm_event", "lab_result", "vitals_publication"}
    chosen = [(n, v, m) for n, v, m in cases if n in phi] + \
        [("lab_result", "secret", _lab(msgs))]
    fmts = (("ser_json", ser.Format.JSON), ("ser_xml", ser.Format.XML),
            ("ser_yaml", ser.Format.YAML))
    reqs = [(op, n, m.SerializeToString()) for op, _ in fmts for n, _, m in chosen]
    res = P.run(gen, [("redact_on", None, None)] + reqs)[1:]
    for ((op, fmt), (n, v, m)), (ok, text) in zip(
            [(f, c) for f in fmts for c in chosen], res):
        assert ok and text.decode() == ser.to_string(m, fmt), (n, v, op)
        if v in ("populated", "secret"):
            assert "[REDACTED]" in text.decode(), (n, v, op)


# -- java-xml-byte-parity-DEFECT: one focused case per former difference class --

def _cpp_java_xml(gen, java, typ, messages):
    reqs = [("to_xml", typ, m.SerializeToString()) for m in messages]
    cpp, jv = P.run(gen, reqs), java_run(java, reqs)
    out = []
    for (cok, ctext), (jok, jtext) in zip(cpp, jv):
        assert cok and jok, jtext
        out.append((ctext.decode(), jtext.decode()))
    return out


def test_java_xml_empty_element_matches_cpp(gen, msgs, java):
    """An empty string field is <name></name> in C++ and Java (Java's DOM
    Transformer wrote <name/>)."""
    m = msgs["users"]()
    m.address = "somewhere"
    for cpp, jv in _cpp_java_xml(gen, java, "users", [m]):
        assert "<name></name>" in cpp and jv == cpp, (cpp, jv)


def test_java_xml_quotes_escaped_like_cpp(gen, msgs, java):
    """& < > " ' are escaped exactly as harpia_xml.h does (Java wrote the
    quotes raw)."""
    m = msgs["users"]()
    m.name, m.address = "a \"quoted\" 'name'", "x & y <z>"
    for cpp, jv in _cpp_java_xml(gen, java, "users", [m]):
        assert "&quot;" in cpp and "&apos;" in cpp and jv == cpp, (cpp, jv)


def test_java_xml_float_text_matches_cpp(gen, msgs, java):
    """Floats print like std::to_string (%f, round-half-even on the exact
    binary value): 0.000000, 15.250000, 0.007812 (a %f tie), -0.000000,
    big values, nan / inf (Java wrote Float.toString: 0.0, 15.25, ...)."""
    values = [0.0, 15.25, 0.0078125, -0.0, -1.5, 1e10, 3.4e38, 1.17549435e-38,
              123456.789, float("nan"), float("inf"), float("-inf")]
    ms = []
    for v in values:
        m = msgs["patient_vitals"]()
        m.heart_rate = v
        ms.append(m)
    x = importlib.import_module("harpia_runtime.xml")
    for v, m, (cpp, jv) in zip(values, ms, _cpp_java_xml(gen, java, "patient_vitals", ms)):
        assert jv == cpp == x.to_xml(m), (v, cpp, jv, x.to_xml(m))
