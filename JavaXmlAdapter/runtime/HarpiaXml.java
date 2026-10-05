// Ships verbatim into every Java-target build (see JavaXmlAdapter.py). Hand-
// written, NOT generated -- like the C++ target's harpia_xml.h, this is a
// generic, reflection-based XML runtime: walking any message via protobuf-
// java's Descriptors.FieldDescriptor + Message.getField(fd)/hasField(fd)
// handles nested messages, repeated fields and enums without any
// per-message generated code, no per-field switch to keep in sync. Unlike
// the C++ target, this needs ZERO extra dependency -- javax.xml (DOM) is
// JDK-builtin, where C++ had to vendor tinyxml2 (protobuf has no built-in
// XML support in either language).
//
// Unlike C++'s XmlAdapter (which still emits a thin per-message wrapper
// header "so XML mirrors the JSON adapter shape" -- Database/CLAUDE.md /
// XmlAdapter/CLAUDE.md), there is no per-message Java wrapper here either,
// same reasoning as JavaJsonAdapter: every generated message class already
// implements the common Message interface, so this single class's
// toXml(Message)/fromXml(String, Builder) already work for any message
// type -- a per-message wrapper would be boilerplate with no benefit.
package com.harpia.runtime.xml;

import com.google.protobuf.Descriptors.Descriptor;
import com.google.protobuf.Descriptors.EnumValueDescriptor;
import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.Descriptors.FieldDescriptor.JavaType;
import com.google.protobuf.Message;
import com.google.protobuf.ByteString;
import java.io.StringReader;
import java.math.BigDecimal;
import java.math.RoundingMode;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public final class HarpiaXml {
    private HarpiaXml() {}

    // message -> XML. The root element is the message type name. Written
    // byte for byte like the C++ harpia_xml.h (and the Python runtime):
    // no XML declaration, <x></x> for an empty element, & < > " ' escaped,
    // floats/doubles as std::to_string (%f) -- java-xml-byte-parity-DEFECT
    // (the DOM Transformer wrote <x/>, raw quotes and Float.toString).
    public static String toXml(Message msg) {
        String root = msg.getDescriptorForType().getName();
        StringBuilder out = new StringBuilder();
        out.append('<').append(root).append('>');
        writeMessage(msg, out);
        out.append("</").append(root).append('>');
        return out.toString();
    }

    private static void writeMessage(Message msg, StringBuilder out) {
        for (FieldDescriptor fd : msg.getDescriptorForType().getFields()) {
            String tag = fd.getName();
            if (fd.isRepeated()) {
                int n = msg.getRepeatedFieldCount(fd);
                for (int k = 0; k < n; k++) {
                    out.append('<').append(tag).append('>');
                    writeValue(fd, msg.getRepeatedField(fd, k), out);
                    out.append("</").append(tag).append('>');
                }
            } else {
                // proto3 implicit-presence scalars are emitted with their
                // default (there's no "unset" to distinguish); but any field
                // with REAL presence -- a singular message field (always has
                // presence in proto3), or a scalar explicitly marked
                // `optional` in the .harpia schema (Message/FieldMap.py S4,
                // see ProtoFile/CLAUDE.md) -- is emitted only when actually
                // present, same rule and same reason as the C++ runtime
                // (harpia_xml.h): otherwise an absent field round-trips back
                // as present-with-default (a phantom child message, or the
                // "explicitly 0" vs. "never set" ambiguity presence tracking
                // exists to close).
                if (fd.hasPresence() && !msg.hasField(fd)) {
                    continue;
                }
                out.append('<').append(tag).append('>');
                writeValue(fd, msg.getField(fd), out);
                out.append("</").append(tag).append('>');
            }
        }
    }

    private static void writeValue(FieldDescriptor fd, Object value, StringBuilder out) {
        switch (fd.getJavaType()) {
            case MESSAGE:
                writeMessage((Message) value, out);
                break;
            case ENUM:
                out.append(((EnumValueDescriptor) value).getName());
                break;
            case INT:
                if (isUnsigned(fd)) out.append(Integer.toUnsignedString((Integer) value));
                else out.append((int) (Integer) value);
                break;
            case LONG:
                if (isUnsigned(fd)) out.append(Long.toUnsignedString((Long) value));
                else out.append((long) (Long) value);
                break;
            case FLOAT:
                // std::to_string(float) promotes to double first
                out.append(fixed6((double) (Float) value));
                break;
            case DOUBLE:
                out.append(fixed6((Double) value));
                break;
            case BOOLEAN:
                out.append(((Boolean) value) ? "true" : "false");
                break;
            case BYTE_STRING:
                escape(((ByteString) value).toStringUtf8(), out);
                break;
            default:
                escape(String.valueOf(value), out);
        }
    }

    private static boolean isUnsigned(FieldDescriptor fd) {
        switch (fd.getType()) {
            case UINT32: case FIXED32: case UINT64: case FIXED64: return true;
            default: return false;
        }
    }

    // harpia_xml.h detail::escape
    private static void escape(String in, StringBuilder out) {
        for (int i = 0; i < in.length(); i++) {
            char c = in.charAt(i);
            switch (c) {
                case '&': out.append("&amp;"); break;
                case '<': out.append("&lt;"); break;
                case '>': out.append("&gt;"); break;
                case '"': out.append("&quot;"); break;
                case '\'': out.append("&apos;"); break;
                default: out.append(c);
            }
        }
    }

    // std::to_string(double) == printf("%f"): six decimals of the EXACT
    // binary value, ties to even (glibc), so BigDecimal(v) + HALF_EVEN, not
    // String.format (HALF_UP); "-0.000000", "nan"/"-nan", "inf"/"-inf" as
    // glibc spells them.
    static String fixed6(double v) {
        boolean negative = (Double.doubleToRawLongBits(v) & Long.MIN_VALUE) != 0;
        if (Double.isNaN(v)) return negative ? "-nan" : "nan";
        if (Double.isInfinite(v)) return negative ? "-inf" : "inf";
        String text = new BigDecimal(v).setScale(6, RoundingMode.HALF_EVEN).toPlainString();
        return negative && !text.startsWith("-") ? "-" + text : text;
    }

    // ---- read (XML -> message) ---------------------------------------

    // XML -> message. Returns false if the document does not parse (same
    // boolean-outcome convention as JsonAdapter's is_valid_json / this
    // repo's from_json/from_xml elsewhere -- see JavaXmlAdapter/CLAUDE.md).
    public static boolean fromXml(String xml, Message.Builder builder) {
        try {
            DocumentBuilder db = DocumentBuilderFactory.newInstance().newDocumentBuilder();
            Document doc = db.parse(new InputSource(new StringReader(xml)));
            Element root = doc.getDocumentElement();
            if (root == null) {
                return false;
            }
            readMessage(root, builder);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    // Read a message from an already-parsed XML element (for batch import,
    // where a parent document holds many message elements -- mirrors the
    // C++ runtime's from_xml_element).
    public static void fromXmlElement(Element node, Message.Builder builder) {
        readMessage(node, builder);
    }

    private static void readMessage(Element node, Message.Builder builder) {
        Descriptor d = builder.getDescriptorForType();
        NodeList children = node.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            Node childNode = children.item(i);
            if (!(childNode instanceof Element)) {
                continue;
            }
            Element child = (Element) childNode;
            FieldDescriptor fd = d.findFieldByName(child.getTagName());
            if (fd == null) {
                continue;
            }
            if (fd.getJavaType() == JavaType.MESSAGE) {
                Message.Builder sub = builder.newBuilderForField(fd);
                readMessage(child, sub);
                if (fd.isRepeated()) {
                    builder.addRepeatedField(fd, sub.build());
                } else {
                    builder.setField(fd, sub.build());
                }
            } else {
                Object value = parseScalar(fd, child.getTextContent());
                if (value == null) {
                    continue;
                }
                if (fd.isRepeated()) {
                    builder.addRepeatedField(fd, value);
                } else {
                    builder.setField(fd, value);
                }
            }
        }
    }

    private static Object parseScalar(FieldDescriptor fd, String text) {
        switch (fd.getJavaType()) {
            case INT:
                return Integer.parseInt(text);
            case LONG:
                return Long.parseLong(text);
            case FLOAT:
                return (float) parseDouble(text);
            case DOUBLE:
                return parseDouble(text);
            case BOOLEAN:
                return Boolean.parseBoolean(text);
            case STRING:
                return text;
            case ENUM:
                EnumValueDescriptor evd = fd.getEnumType().findValueByName(text);
                if (evd == null) {
                    try {
                        evd = fd.getEnumType().findValueByNumber(Integer.parseInt(text));
                    } catch (NumberFormatException e) {
                        return null;
                    }
                }
                return evd;
            default:
                throw new IllegalArgumentException(
                    "HarpiaXml: unsupported field type " + fd.getJavaType()
                    + " for field " + fd.getName());
        }
    }

    // Double.parseDouble plus the strtod spellings C++ writes and reads:
    // "nan"/"-nan", "inf"/"-inf" (any case, "infinity" too).
    private static double parseDouble(String text) {
        String t = text.trim().toLowerCase(java.util.Locale.ROOT);
        boolean neg = t.startsWith("-");
        String body = (neg || t.startsWith("+")) ? t.substring(1) : t;
        if (body.equals("nan")) return neg ? -Double.NaN : Double.NaN;
        if (body.equals("inf") || body.equals("infinity")) {
            return neg ? Double.NEGATIVE_INFINITY : Double.POSITIVE_INFINITY;
        }
        return Double.parseDouble(text.trim());
    }
}
