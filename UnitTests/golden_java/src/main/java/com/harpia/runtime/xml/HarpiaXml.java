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
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public final class HarpiaXml {
    private HarpiaXml() {}

    // message -> XML. The root element is the message type name.
    public static String toXml(Message msg) {
        try {
            Document doc = newDocument();
            Element root = doc.createElement(msg.getDescriptorForType().getName());
            doc.appendChild(root);
            writeMessage(doc, root, msg);
            return serialize(doc);
        } catch (Exception e) {
            throw new IllegalStateException("HarpiaXml.toXml failed", e);
        }
    }

    private static void writeMessage(Document doc, Element parent, Message msg) {
        for (FieldDescriptor fd : msg.getDescriptorForType().getFields()) {
            String tag = fd.getName();
            if (fd.isRepeated()) {
                int n = msg.getRepeatedFieldCount(fd);
                for (int k = 0; k < n; k++) {
                    Element el = doc.createElement(tag);
                    parent.appendChild(el);
                    writeValue(doc, el, fd, msg.getRepeatedField(fd, k));
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
                Element el = doc.createElement(tag);
                parent.appendChild(el);
                writeValue(doc, el, fd, msg.getField(fd));
            }
        }
    }

    private static void writeValue(Document doc, Element el, FieldDescriptor fd, Object value) {
        if (fd.getJavaType() == JavaType.MESSAGE) {
            writeMessage(doc, el, (Message) value);
        } else if (fd.getJavaType() == JavaType.ENUM) {
            el.setTextContent(((EnumValueDescriptor) value).getName());
        } else {
            el.setTextContent(String.valueOf(value));
        }
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
                return Float.parseFloat(text);
            case DOUBLE:
                return Double.parseDouble(text);
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

    static Document newDocument() throws Exception {
        DocumentBuilder db = DocumentBuilderFactory.newInstance().newDocumentBuilder();
        return db.newDocument();
    }

    static String serialize(Document doc) throws Exception {
        Transformer t = TransformerFactory.newInstance().newTransformer();
        t.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
        StringWriter sw = new StringWriter();
        t.transform(new DOMSource(doc), new StreamResult(sw));
        return sw.toString();
    }
}
