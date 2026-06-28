// harpia Stage 10 XML runtime (hand-written, not generated).
//
// Generic, reflection-based XML serialization for any protobuf message. The
// per-message <name>_xml.h wrappers include this; callers use:
//
//     std::string xml = harpia::xml::to_xml(msg);
//     harpia::xml::from_xml(xml, &msg);          // (added in read step)
//     std::string xsd = harpia::xml::xsd(T::descriptor());  // (added later)
//
// Walking the message via the protobuf descriptor/reflection API means this
// handles nested messages, repeated fields, enums and maps without any
// per-field generated code.
#ifndef HARPIA_XML_RUNTIME_H
#define HARPIA_XML_RUNTIME_H

#include <cstdlib>
#include <string>
#include <vector>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>

#include "tinyxml2.h"

namespace harpia {
namespace xml {
namespace detail {

inline void escape(const std::string& in, std::string& out) {
    for (char c : in) {
        switch (c) {
            case '&': out += "&amp;"; break;
            case '<': out += "&lt;"; break;
            case '>': out += "&gt;"; break;
            case '"': out += "&quot;"; break;
            case '\'': out += "&apos;"; break;
            default: out += c;
        }
    }
}

// mutual recursion: a field value may itself be a message
inline void write_message(const ::google::protobuf::Message& msg, std::string& out);

// emit the value of a singular field (no surrounding tag)
inline void write_singular(const ::google::protobuf::Message& msg,
                           const ::google::protobuf::Reflection* refl,
                           const ::google::protobuf::FieldDescriptor* f,
                           std::string& out) {
    using FD = ::google::protobuf::FieldDescriptor;
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:  out += std::to_string(refl->GetInt32(msg, f)); break;
        case FD::CPPTYPE_INT64:  out += std::to_string(refl->GetInt64(msg, f)); break;
        case FD::CPPTYPE_UINT32: out += std::to_string(refl->GetUInt32(msg, f)); break;
        case FD::CPPTYPE_UINT64: out += std::to_string(refl->GetUInt64(msg, f)); break;
        case FD::CPPTYPE_DOUBLE: out += std::to_string(refl->GetDouble(msg, f)); break;
        case FD::CPPTYPE_FLOAT:  out += std::to_string(refl->GetFloat(msg, f)); break;
        case FD::CPPTYPE_BOOL:   out += refl->GetBool(msg, f) ? "true" : "false"; break;
        case FD::CPPTYPE_ENUM:   out += refl->GetEnum(msg, f)->name(); break;
        case FD::CPPTYPE_STRING: escape(refl->GetString(msg, f), out); break;
        case FD::CPPTYPE_MESSAGE: write_message(refl->GetMessage(msg, f), out); break;
    }
}

// emit the value of the k-th element of a repeated field (no surrounding tag)
inline void write_repeated(const ::google::protobuf::Message& msg,
                           const ::google::protobuf::Reflection* refl,
                           const ::google::protobuf::FieldDescriptor* f,
                           int k, std::string& out) {
    using FD = ::google::protobuf::FieldDescriptor;
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:  out += std::to_string(refl->GetRepeatedInt32(msg, f, k)); break;
        case FD::CPPTYPE_INT64:  out += std::to_string(refl->GetRepeatedInt64(msg, f, k)); break;
        case FD::CPPTYPE_UINT32: out += std::to_string(refl->GetRepeatedUInt32(msg, f, k)); break;
        case FD::CPPTYPE_UINT64: out += std::to_string(refl->GetRepeatedUInt64(msg, f, k)); break;
        case FD::CPPTYPE_DOUBLE: out += std::to_string(refl->GetRepeatedDouble(msg, f, k)); break;
        case FD::CPPTYPE_FLOAT:  out += std::to_string(refl->GetRepeatedFloat(msg, f, k)); break;
        case FD::CPPTYPE_BOOL:   out += refl->GetRepeatedBool(msg, f, k) ? "true" : "false"; break;
        case FD::CPPTYPE_ENUM:   out += refl->GetRepeatedEnum(msg, f, k)->name(); break;
        case FD::CPPTYPE_STRING: escape(refl->GetRepeatedString(msg, f, k), out); break;
        case FD::CPPTYPE_MESSAGE: write_message(refl->GetRepeatedMessage(msg, f, k), out); break;
    }
}

inline void write_message(const ::google::protobuf::Message& msg, std::string& out) {
    const auto* d = msg.GetDescriptor();
    const auto* refl = msg.GetReflection();
    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        const std::string& tag = f->name();
        if (f->is_repeated()) {
            const int n = refl->FieldSize(msg, f);
            for (int k = 0; k < n; ++k) {
                out += "<" + tag + ">";
                write_repeated(msg, refl, f, k, out);
                out += "</" + tag + ">";
            }
        } else {
            // proto3: singular fields are always emitted (defaults included)
            out += "<" + tag + ">";
            write_singular(msg, refl, f, out);
            out += "</" + tag + ">";
        }
    }
}

// ---- read (XML -> message) ------------------------------------------------

inline long long to_ll(const char* t) { return t ? std::strtoll(t, nullptr, 10) : 0; }
inline unsigned long long to_ull(const char* t) { return t ? std::strtoull(t, nullptr, 10) : 0; }
inline double to_d(const char* t) { return t ? std::strtod(t, nullptr) : 0.0; }
inline bool to_b(const char* t) { return t && (std::string(t) == "true" || std::string(t) == "1"); }

inline void set_enum(::google::protobuf::Message* msg,
                     const ::google::protobuf::Reflection* refl,
                     const ::google::protobuf::FieldDescriptor* f,
                     const char* text, bool repeated) {
    if (!text) return;
    const auto* ev = f->enum_type()->FindValueByName(text);
    if (!ev) ev = f->enum_type()->FindValueByNumber(static_cast<int>(to_ll(text)));
    if (!ev) return;
    if (repeated) refl->AddEnum(msg, f, ev);
    else refl->SetEnum(msg, f, ev);
}

inline bool read_message(const ::tinyxml2::XMLElement* node,
                         ::google::protobuf::Message* msg) {
    using FD = ::google::protobuf::FieldDescriptor;
    const auto* d = msg->GetDescriptor();
    const auto* refl = msg->GetReflection();
    for (const auto* child = node->FirstChildElement(); child;
         child = child->NextSiblingElement()) {
        const auto* f = d->FindFieldByName(child->Name());
        if (!f) continue;
        const char* t = child->GetText();
        const std::string s = t ? t : "";
        if (f->is_repeated()) {
            switch (f->cpp_type()) {
                case FD::CPPTYPE_INT32:  refl->AddInt32(msg, f, static_cast<int32_t>(to_ll(t))); break;
                case FD::CPPTYPE_INT64:  refl->AddInt64(msg, f, to_ll(t)); break;
                case FD::CPPTYPE_UINT32: refl->AddUInt32(msg, f, static_cast<uint32_t>(to_ull(t))); break;
                case FD::CPPTYPE_UINT64: refl->AddUInt64(msg, f, to_ull(t)); break;
                case FD::CPPTYPE_DOUBLE: refl->AddDouble(msg, f, to_d(t)); break;
                case FD::CPPTYPE_FLOAT:  refl->AddFloat(msg, f, static_cast<float>(to_d(t))); break;
                case FD::CPPTYPE_BOOL:   refl->AddBool(msg, f, to_b(t)); break;
                case FD::CPPTYPE_ENUM:   set_enum(msg, refl, f, t, true); break;
                case FD::CPPTYPE_STRING: refl->AddString(msg, f, s); break;
                case FD::CPPTYPE_MESSAGE: read_message(child, refl->AddMessage(msg, f)); break;
            }
        } else {
            switch (f->cpp_type()) {
                case FD::CPPTYPE_INT32:  refl->SetInt32(msg, f, static_cast<int32_t>(to_ll(t))); break;
                case FD::CPPTYPE_INT64:  refl->SetInt64(msg, f, to_ll(t)); break;
                case FD::CPPTYPE_UINT32: refl->SetUInt32(msg, f, static_cast<uint32_t>(to_ull(t))); break;
                case FD::CPPTYPE_UINT64: refl->SetUInt64(msg, f, to_ull(t)); break;
                case FD::CPPTYPE_DOUBLE: refl->SetDouble(msg, f, to_d(t)); break;
                case FD::CPPTYPE_FLOAT:  refl->SetFloat(msg, f, static_cast<float>(to_d(t))); break;
                case FD::CPPTYPE_BOOL:   refl->SetBool(msg, f, to_b(t)); break;
                case FD::CPPTYPE_ENUM:   set_enum(msg, refl, f, t, false); break;
                case FD::CPPTYPE_STRING: refl->SetString(msg, f, s); break;
                case FD::CPPTYPE_MESSAGE: read_message(child, refl->MutableMessage(msg, f)); break;
            }
        }
    }
    return true;
}

}  // namespace detail

// message -> XML. The root element is the message type name.
inline std::string to_xml(const ::google::protobuf::Message& msg) {
    const std::string& root = msg.GetDescriptor()->name();
    std::string out = "<" + root + ">";
    detail::write_message(msg, out);
    out += "</" + root + ">";
    return out;
}

// XML -> message. Returns false if the document does not parse.
inline bool from_xml(const std::string& xml, ::google::protobuf::Message* msg) {
    ::tinyxml2::XMLDocument doc;
    if (doc.Parse(xml.c_str()) != ::tinyxml2::XML_SUCCESS) return false;
    const auto* root = doc.RootElement();
    if (!root) return false;
    return detail::read_message(root, msg);
}

// ---- XSD schema -----------------------------------------------------------
namespace detail {

inline const char* xsd_scalar(::google::protobuf::FieldDescriptor::CppType t) {
    using FD = ::google::protobuf::FieldDescriptor;
    switch (t) {
        case FD::CPPTYPE_INT32:  return "xs:int";
        case FD::CPPTYPE_INT64:  return "xs:long";
        case FD::CPPTYPE_UINT32: return "xs:unsignedInt";
        case FD::CPPTYPE_UINT64: return "xs:unsignedLong";
        case FD::CPPTYPE_DOUBLE: return "xs:double";
        case FD::CPPTYPE_FLOAT:  return "xs:float";
        case FD::CPPTYPE_BOOL:   return "xs:boolean";
        default:                 return "xs:string";  // enum + string
    }
}

// reachable message types from root (depth-first, cycle-safe), root first
inline void collect(const ::google::protobuf::Descriptor* d,
                    std::vector<const ::google::protobuf::Descriptor*>& order) {
    for (const auto* x : order)
        if (x == d) return;
    order.push_back(d);
    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        if (f->cpp_type() == ::google::protobuf::FieldDescriptor::CPPTYPE_MESSAGE)
            collect(f->message_type(), order);
    }
}

inline void write_complex_type(const ::google::protobuf::Descriptor* d,
                               std::string& out) {
    out += "  <xs:complexType name=\"" + d->name() + "\">\n    <xs:sequence>\n";
    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        const std::string type =
            (f->cpp_type() == ::google::protobuf::FieldDescriptor::CPPTYPE_MESSAGE)
                ? f->message_type()->name()
                : std::string(xsd_scalar(f->cpp_type()));
        out += "      <xs:element name=\"" + f->name() + "\" type=\"" + type +
               "\" minOccurs=\"0\"";
        if (f->is_repeated()) out += " maxOccurs=\"unbounded\"";
        out += "/>\n";
    }
    out += "    </xs:sequence>\n  </xs:complexType>\n";
}

}  // namespace detail

// XSD schema describing the message (and the nested message types it uses).
inline std::string xsd(const ::google::protobuf::Descriptor* root) {
    std::vector<const ::google::protobuf::Descriptor*> order;
    detail::collect(root, order);
    std::string out =
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\">\n";
    out += "  <xs:element name=\"" + root->name() + "\" type=\"" +
           root->name() + "\"/>\n";
    for (const auto* d : order)
        detail::write_complex_type(d, out);
    out += "</xs:schema>\n";
    return out;
}

}  // namespace xml
}  // namespace harpia

#endif  // HARPIA_XML_RUNTIME_H
