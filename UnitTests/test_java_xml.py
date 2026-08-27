"""Sessions J.10/J.11 (Initiatives/multi-language-targets/thread-1-java-
target/histories/XML-runtime/) -- XML write path (J.10) + read path (J.11)
for the Java target. Landed together -- J.11 extends the same runtime file
J.10 introduces (com.harpia.runtime.xml.HarpiaXml), same file, same class,
a natural single unit.

Single hand-written reflection-based runtime class, no per-message
generation -- see JavaXmlAdapter/CLAUDE.md.

  - Structural (pure Python, always run): the runtime class is wired in.
  - Integration (gradle+JDK-gated): serialize `shipment` (a scalar field
    plus `repeteable parcel cargo`, HarpiaTest/test.harpia) to XML,
    confirming nested + repeated fields both walk correctly; serialize
    `patient_vitals` with its `optional string device_note` left unset,
    confirming presence-gated emission (no <device_note> tag at all) --
    the literal J.10 test bar. J.11: round-trip `shipment` and both
    `patient_vitals` variants (device_note set / unset) through
    to_xml -> from_xml, confirming values AND presence survive -- the
    literal J.11 test bar (not just values, which a naive round trip could
    get right while still turning "never set" into "present as empty").
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


# -- structural -------------------------------------------------------------

def test_xml_runtime_is_wired_into_the_gradle_project(tmp_path):
    out = generate(tmp_path, lang="java")
    runtime_path = os.path.join(out, "java", "src", "main", "java", "com",
                                "harpia", "runtime", "xml", "HarpiaXml.java")
    assert os.path.isfile(runtime_path)
    text = open(runtime_path).read()
    assert "package com.harpia.runtime.xml;" in text
    assert "toXml" in text


# -- integration: a real gradle+JDK build ------------------------------------

@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_nested_and_repeated_fields_serialize(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/XmlWrite.java":
            "package smoke;\n"
            "import com.harpia.generated.shipment;\n"
            "import com.harpia.generated.parcel;\n"
            "import com.harpia.generated.patient_vitals;\n"
            "import com.harpia.runtime.xml.HarpiaXml;\n"
            "public class XmlWrite {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        shipment s = shipment.newBuilder()\n"
            "            .setTag(\"crate-1\")\n"
            "            .addCargo(parcel.newBuilder().setLabel(\"books\").setWeight(4).build())\n"
            "            .addCargo(parcel.newBuilder().setLabel(\"tools\").setWeight(9).build())\n"
            "            .build();\n"
            "        String xml = HarpiaXml.toXml(s);\n"
            "        if (!xml.contains(\"<tag>crate-1</tag>\")) { System.out.println(xml); System.exit(1); }\n"
            "        if (!xml.contains(\"<label>books</label>\")) { System.out.println(xml); System.exit(2); }\n"
            "        if (!xml.contains(\"<weight>4</weight>\")) { System.out.println(xml); System.exit(3); }\n"
            "        if (!xml.contains(\"<label>tools</label>\")) { System.out.println(xml); System.exit(4); }\n"
            "        if (!xml.contains(\"<weight>9</weight>\")) { System.out.println(xml); System.exit(5); }\n"
            "        long cargoTags = xml.split(\"<cargo>\", -1).length - 1;\n"
            "        if (cargoTags != 2) { System.out.println(xml); System.exit(6); }\n"
            "\n"
            "        patient_vitals p = patient_vitals.newBuilder()\n"
            "            .setPatientId(\"p-1\").setHeartRate(60.0f).build();\n"
            "        String pxml = HarpiaXml.toXml(p);\n"
            "        if (pxml.contains(\"device_note\")) { System.out.println(pxml); System.exit(7); }\n"
            "        if (!pxml.contains(\"<patient_id>p-1</patient_id>\")) { System.out.println(pxml); System.exit(8); }\n"
            "\n"
            "        patient_vitals p2 = patient_vitals.newBuilder()\n"
            "            .setPatientId(\"p-2\").setHeartRate(61.0f).setDeviceNote(\"note\").build();\n"
            "        String pxml2 = HarpiaXml.toXml(p2);\n"
            "        if (!pxml2.contains(\"<device_note>note</device_note>\")) { System.out.println(pxml2); System.exit(9); }\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.XmlWrite"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "XML write path failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout


@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_nested_repeated_and_presence_roundtrip(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    classpath = build_and_classpath(java_root, {
        "smoke/XmlRoundTrip.java":
            "package smoke;\n"
            "import com.harpia.generated.shipment;\n"
            "import com.harpia.generated.parcel;\n"
            "import com.harpia.generated.patient_vitals;\n"
            "import com.harpia.runtime.xml.HarpiaXml;\n"
            "public class XmlRoundTrip {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        shipment s = shipment.newBuilder()\n"
            "            .setTag(\"crate-1\")\n"
            "            .addCargo(parcel.newBuilder().setLabel(\"books\").setWeight(4).build())\n"
            "            .addCargo(parcel.newBuilder().setLabel(\"tools\").setWeight(9).build())\n"
            "            .build();\n"
            "        shipment.Builder sb = shipment.newBuilder();\n"
            "        if (!HarpiaXml.fromXml(HarpiaXml.toXml(s), sb)) System.exit(1);\n"
            "        shipment sBack = sb.build();\n"
            "        if (!sBack.getTag().equals(\"crate-1\")) System.exit(2);\n"
            "        if (sBack.getCargoCount() != 2) System.exit(3);\n"
            "        if (!sBack.getCargo(0).getLabel().equals(\"books\") || sBack.getCargo(0).getWeight() != 4) System.exit(4);\n"
            "        if (!sBack.getCargo(1).getLabel().equals(\"tools\") || sBack.getCargo(1).getWeight() != 9) System.exit(5);\n"
            "\n"
            "        // presence, not just values: an unset optional field must come\n"
            "        // back unset, not \"present with the empty-string default\".\n"
            "        patient_vitals unset = patient_vitals.newBuilder()\n"
            "            .setPatientId(\"p-1\").setHeartRate(60.0f).build();\n"
            "        patient_vitals.Builder ub = patient_vitals.newBuilder();\n"
            "        if (!HarpiaXml.fromXml(HarpiaXml.toXml(unset), ub)) System.exit(6);\n"
            "        if (ub.hasDeviceNote()) System.exit(7);\n"
            "\n"
            "        patient_vitals set = patient_vitals.newBuilder()\n"
            "            .setPatientId(\"p-2\").setHeartRate(61.0f).setDeviceNote(\"note\").build();\n"
            "        patient_vitals.Builder sb2 = patient_vitals.newBuilder();\n"
            "        if (!HarpiaXml.fromXml(HarpiaXml.toXml(set), sb2)) System.exit(8);\n"
            "        if (!sb2.hasDeviceNote() || !sb2.getDeviceNote().equals(\"note\")) System.exit(9);\n"
            "        System.out.println(\"OK\");\n"
            "    }\n"
            "}\n",
    })

    run = subprocess.run(["java", "-cp", classpath, "smoke.XmlRoundTrip"],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, "XML round trip failed:\n" + run.stdout + run.stderr
    assert "OK" in run.stdout
