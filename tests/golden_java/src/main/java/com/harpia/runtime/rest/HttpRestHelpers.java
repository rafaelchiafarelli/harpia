// Ships verbatim into every Java-target build (see JavaRestAdapter.py).
// Hand-written, NOT generated -- the message-agnostic HTTP mechanics every
// generated <name>_rest.java route registration shares: the Stage 5 access-
// credential gate, content negotiation (reusing HarpiaJson/HarpiaXml, both
// already generic over any Message), and a collection-vs-item path split
// substituting for the path-parameter routing a framework like Crow gives
// the C++ target for free -- JDK-builtin com.sun.net.httpserver.HttpServer
// only matches a request to the LONGEST registered context path that
// prefixes it, with no built-in notion of ":id"-style path variables.
package com.harpia.runtime.rest;

import com.google.protobuf.Message;
import com.harpia.runtime.json.HarpiaJson;
import com.harpia.runtime.xml.HarpiaXml;
import com.sun.net.httpserver.HttpExchange;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;

public final class HttpRestHelpers {
    private HttpRestHelpers() {}

    // True iff the request carries the correct credential for a message
    // (Stage 5 access rights: X-User: <name> / X-Pswd: <hash>), mirroring
    // the C++ target's per-message authorized_<name>() -- shared here
    // since Java doesn't need per-message string-literal closures to check
    // this, only the two expected values as parameters.
    public static boolean authorized(HttpExchange exchange, String user, String pswd) {
        return user.equals(header(exchange, "X-User")) && pswd.equals(header(exchange, "X-Pswd"));
    }

    private static String header(HttpExchange exchange, String name) {
        List<String> values = exchange.getRequestHeaders().get(name);
        return (values == null || values.isEmpty()) ? "" : values.get(0);
    }

    // content negotiation: XML when asked for, JSON otherwise (same rule as
    // the C++ target's wants_xml_<name>()/body_xml_<name>()).
    public static boolean wantsXml(HttpExchange exchange) {
        return header(exchange, "Accept").toLowerCase(Locale.ROOT).contains("xml");
    }

    public static boolean isXmlBody(HttpExchange exchange) {
        return header(exchange, "Content-Type").toLowerCase(Locale.ROOT).contains("xml");
    }

    // `collectionPath` is what was registered with HttpServer.createContext
    // (e.g. ".../users"); returns null for the collection path itself
    // (list/create), or the parsed trailing id for an item path
    // (".../users/<id>", read/update/delete) -- null on anything else
    // (a malformed id), which callers treat as "not found" rather than a
    // crash.
    public static Integer trailingId(HttpExchange exchange, String collectionPath) {
        String path = exchange.getRequestURI().getPath();
        String prefix = collectionPath + "/";
        if (!path.startsWith(prefix)) {
            return null;
        }
        String rest = path.substring(prefix.length());
        if (rest.isEmpty()) {
            return null;
        }
        try {
            return Integer.parseInt(rest);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    public static String readBody(HttpExchange exchange) throws IOException {
        try (InputStream in = exchange.getRequestBody()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) != -1) {
                out.write(buf, 0, n);
            }
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }

    // Request body -> `builder`, XML or JSON per Content-Type. False on a
    // parse failure (caller responds 400), never throws for a malformed body.
    public static boolean parseBody(HttpExchange exchange, Message.Builder builder) throws IOException {
        String body = readBody(exchange);
        if (isXmlBody(exchange)) {
            return HarpiaXml.fromXml(body, builder);
        }
        try {
            HarpiaJson.fromJson(body, builder);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public static void sendMessage(HttpExchange exchange, int status, Message msg) throws IOException {
        boolean xml = wantsXml(exchange);
        String body = xml ? HarpiaXml.toXml(msg) : HarpiaJson.toJson(msg);
        sendBody(exchange, status, body, xml ? "application/xml" : "application/json");
    }

    public static void sendBody(HttpExchange exchange, int status, String body, String contentType)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    public static void sendStatus(HttpExchange exchange, int status) throws IOException {
        exchange.sendResponseHeaders(status, -1);
    }
}
