// Ships verbatim into every Java-target build (see JavaSoapAdapter.py).
// Hand-written, NOT generated -- the message-agnostic envelope parsing
// every generated <name>_soap.java shares, a direct port of
// Database/SoapAdapter.py's C++ `detail::` namespace (local_name/
// find_child/child_text) onto org.w3c.dom, the same DOM type
// com.harpia.runtime.xml.HarpiaXml already uses. Like the C++ target,
// this is NOT a real SOAP/WS-* stack -- hand-rolled envelope get/set/
// update/delete parsing, same as Database/SoapAdapter.py's own framing
// (see Database/CLAUDE.md). Java's own SOAP story (JAX-WS removed from
// the JDK since 11) doesn't matter here for exactly that reason.
package com.harpia.runtime.soap;

import java.io.StringReader;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public final class SoapHelpers {
    private SoapHelpers() {}

    // Parses `xml`, or returns null on a malformed document (caller
    // responds 400) rather than throwing.
    public static Document parse(String xml) {
        try {
            return DocumentBuilderFactory.newInstance().newDocumentBuilder()
                .parse(new InputSource(new StringReader(xml)));
        } catch (Exception e) {
            return null;
        }
    }

    // Element local name, stripping a namespace prefix ("soap:Body" -> "Body").
    public static String localName(Element e) {
        String n = e.getTagName();
        int pos = n.indexOf(':');
        return pos == -1 ? n : n.substring(pos + 1);
    }

    // First child element whose local (prefix-stripped) name matches.
    public static Element findChild(Element parent, String local) {
        if (parent == null) {
            return null;
        }
        NodeList children = parent.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            Node n = children.item(i);
            if (n instanceof Element && localName((Element) n).equals(local)) {
                return (Element) n;
            }
        }
        return null;
    }

    // First child element regardless of name (the operation element inside
    // Body, or the message element inside <set>/<update>).
    public static Element firstChildElement(Element parent) {
        if (parent == null) {
            return null;
        }
        NodeList children = parent.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            Node n = children.item(i);
            if (n instanceof Element) {
                return (Element) n;
            }
        }
        return null;
    }

    public static String childText(Element parent, String local) {
        Element c = findChild(parent, local);
        return c == null ? "" : c.getTextContent();
    }

    // Same graceful-degradation-on-missing/malformed as the C++ target's
    // `idEl && idEl->GetText() ? atoll(...) : 0` -- a missing/unparseable
    // <id> is 0, never an exception a caller has to guard against.
    public static int childInt(Element parent, String local) {
        try {
            return Integer.parseInt(childText(parent, local));
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    public static String envelope(String body) {
        return "<?xml version=\"1.0\"?>"
            + "<soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\">"
            + "<soap:Body>" + body + "</soap:Body></soap:Envelope>";
    }

    // True iff the parsed envelope carries the correct credential
    // (Stage 5 access rights, SOAP Header <credentials>), mirroring the
    // C++ target's per-message authorized_<name>() -- parameterized here
    // instead of a generated per-message closure, same reasoning as
    // JavaRestAdapter's own authorized().
    public static boolean authorized(Document doc, String user, String pswd) {
        if (doc == null) {
            return false;
        }
        Element env = doc.getDocumentElement();
        Element header = findChild(env, "Header");
        Element cred = findChild(header, "credentials");
        if (cred == null) {
            return false;
        }
        return childText(cred, "user").equals(user) && childText(cred, "pswd").equals(pswd);
    }
}
