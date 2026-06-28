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

#include <string>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>

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

}  // namespace detail

// message -> XML. The root element is the message type name.
inline std::string to_xml(const ::google::protobuf::Message& msg) {
    const std::string& root = msg.GetDescriptor()->name();
    std::string out = "<" + root + ">";
    detail::write_message(msg, out);
    out += "</" + root + ">";
    return out;
}

}  // namespace xml
}  // namespace harpia

#endif  // HARPIA_XML_RUNTIME_H
