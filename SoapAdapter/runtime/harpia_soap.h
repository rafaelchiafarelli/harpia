// harpia SOAP runtime -- the pure envelope-parse seam (hand-written, not
// generated; copied verbatim into a generated project's generated/cpp/soap/
// by Database/SoapAdapter.py -- the same convention as XmlAdapter/harpia_xml.h).
//
// The generated <name>_soap.h endpoint (Database/templates/soap.h.tmpl) is a
// crow HTTP handler: it authenticates, parses the SOAP envelope, dispatches on
// the operation name, and calls the CRUDL DAO. This header carries ONLY the
// transport-free, DB-free, auth-free part -- string in, operation + message
// out -- so it can be unit-tested and fuzzed directly (UnitTests/
// test_fuzz_parsers.py, static-fuzz-ci tasks 4a/4b) instead of through a
// socket. The generated handler is a thin caller of these functions, so the
// fuzzer exercises the real parse path, not a copy.
#ifndef HARPIA_SOAP_RUNTIME_H
#define HARPIA_SOAP_RUNTIME_H

#include <string>

#include <google/protobuf/message.h>

#include "tinyxml2.h"
#include "xml/harpia_xml.h"   // harpia::xml::from_xml_element

namespace harpia {
namespace soap {

// Shared XML helpers, namespace-prefix aware. Previously emitted inline into
// every generated *_soap.h under `#ifndef HARPIA_SOAP_DETAIL`; moved here
// verbatim so there is one definition.
namespace detail {

// element name without its namespace prefix ("soap:Body" -> "Body")
inline std::string local_name(const ::tinyxml2::XMLElement* e) {
    if (!e) return std::string();
    std::string n = e->Name();
    const auto pos = n.find(':');
    return pos == std::string::npos ? n : n.substr(pos + 1);
}

// first child element whose local (prefix-stripped) name matches
inline const ::tinyxml2::XMLElement* find_child(
        const ::tinyxml2::XMLElement* parent, const char* local) {
    if (!parent) return nullptr;
    for (auto* c = parent->FirstChildElement(); c; c = c->NextSiblingElement())
        if (local_name(c) == local) return c;
    return nullptr;
}

inline std::string child_text(const ::tinyxml2::XMLElement* parent,
                              const char* local) {
    const auto* c = find_child(parent, local);
    return (c && c->GetText()) ? c->GetText() : std::string();
}

}  // namespace detail

// The parsed shape of a SOAP request envelope, independent of transport, auth
// and CRUDL:  <Envelope> <Body> <OP> <payload/> </OP> </Body> </Envelope>
struct Request {
    // OP's local (namespace-prefix-stripped) name: "get" / "set" / "update" /
    // "delete", or whatever the sender put there.
    std::string operation;
    // the operation element itself; the per-operation handler code reads its
    // children (`<id>` for get/delete, the `<name>` message element for
    // set/update). Points into the parsed document -- valid only while that
    // document lives.
    const ::tinyxml2::XMLElement* op = nullptr;
};

// Step 1: is the body a well-formed XML document? (The generated handler
// answers HTTP 400 when this is false -- and, in the non-hardened variant,
// runs its credential check between this step and find_operation, which is
// why the two are separate calls.)
inline bool parse_envelope(const std::string& envelope,
                           ::tinyxml2::XMLDocument* doc) {
    return doc->Parse(envelope.c_str()) == ::tinyxml2::XML_SUCCESS;
}

// Step 2: locate <Body> and its operation element. Returns false when there
// is no <Body> carrying a child element (HTTP 400 in the handler). `doc` must
// outlive any use of `out->op`.
inline bool find_operation(const ::tinyxml2::XMLDocument& doc, Request* out) {
    const auto* env = doc.RootElement();                   // soap:Envelope
    const auto* body = detail::find_child(env, "Body");
    const auto* op = body ? body->FirstChildElement() : nullptr;
    if (!op) return false;
    out->operation = detail::local_name(op);
    out->op = op;
    return true;
}

// The pure set/update decode path: parse the envelope, find the operation,
// then decode its payload element (OP's first child -- the `<name>` message
// element) through the XML adapter. Returns false on a malformed envelope, a
// missing <Body>/operation, a payload-less operation element, or an
// XML-adapter decode failure. This is static-fuzz-ci task 4b's fuzz target.
inline bool message_from_request(const std::string& envelope,
                                 ::google::protobuf::Message* msg) {
    ::tinyxml2::XMLDocument doc;
    if (!parse_envelope(envelope, &doc)) return false;
    Request req;
    if (!find_operation(doc, &req)) return false;
    const auto* payload = req.op->FirstChildElement();
    if (!payload) return false;
    return ::harpia::xml::from_xml_element(payload, msg);
}

}  // namespace soap
}  // namespace harpia

#endif  // HARPIA_SOAP_RUNTIME_H
