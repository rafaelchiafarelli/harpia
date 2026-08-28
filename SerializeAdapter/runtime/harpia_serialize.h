// harpia Stage 10 unified serialization façade (hand-written, not generated).
//
// Track F / Session F.2 -- "close out the JSON/XML/YAML toString triad through
// one shared path". Before this, a caller picked a format by calling a
// different function in a different namespace with a different signature:
//
//     std::string x = harpia::xml::to_xml(msg);          // returns string
//     std::string y = harpia::yaml::to_yaml(msg);        // returns string
//     std::string j; harpia::json::to_json(msg, &j);     // bool + out-param, typed per message
//
// This header is the single entry point for all three:
//
//     using harpia::serialize::Format;
//     std::string s = harpia::serialize::to_string(msg, Format::JSON);   // or XML / YAML
//     harpia::serialize::from_string(s, &msg, Format::JSON);
//
// Session F.3 wires `phi` redaction into this one hook: when the message (or a
// nested message type) declares a `phi` field and redaction is enabled
// (harpia_redaction.h, default on), `to_string` renders through a
// redaction-aware reflection walk that replaces every `phi` value with
// `[REDACTED]` in JSON, XML and YAML alike -- the three per-format engines
// stay completely untouched, so a message with no `phi` field is byte-for-byte
// what it was before.
#ifndef HARPIA_SERIALIZE_RUNTIME_H
#define HARPIA_SERIALIZE_RUNTIME_H

#include <string>
#include <vector>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>
#include <google/protobuf/util/json_util.h>

#include "xml/harpia_xml.h"
#include "yaml/harpia_yaml.h"
#include "serialize/harpia_redaction.h"

namespace harpia {
namespace serialize {

enum class Format { JSON, XML, YAML };

inline const char* format_name(Format fmt) {
    switch (fmt) {
        case Format::JSON: return "json";
        case Format::XML:  return "xml";
        case Format::YAML: return "yaml";
    }
    return "json";
}

namespace detail {

using FD = ::google::protobuf::FieldDescriptor;

// ---- passthrough engines (unchanged behaviour) ---------------------------

inline std::string to_json_passthrough(const ::google::protobuf::Message& msg) {
    std::string out;
    ::google::protobuf::util::MessageToJsonString(msg, &out);
    return out;
}

inline bool from_json(const std::string& in, ::google::protobuf::Message* msg) {
    ::google::protobuf::util::JsonParseOptions opts;
    opts.ignore_unknown_fields = true;
    return ::google::protobuf::util::JsonStringToMessage(in, msg, opts).ok();
}

// ---- phi detection -------------------------------------------------------

inline bool tree_has_phi(const ::google::protobuf::Descriptor* d,
                         std::vector<const ::google::protobuf::Descriptor*>& seen) {
    for (const auto* s : seen) {
        if (s == d) return false;
    }
    seen.push_back(d);
    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        if (::harpia::serialize::phi::is_phi(d->name(), f->name())) return true;
        if (f->cpp_type() == FD::CPPTYPE_MESSAGE &&
            tree_has_phi(f->message_type(), seen)) {
            return true;
        }
    }
    return false;
}

inline bool tree_has_phi(const ::google::protobuf::Descriptor* d) {
    std::vector<const ::google::protobuf::Descriptor*> seen;
    return tree_has_phi(d, seen);
}

// ---- redaction-aware reflection walk -----------------------------------
// One walker, format-parameterised. `phi` fields become `[REDACTED]` (quoted
// where the format quotes); every non-`phi` value is formatted by type. This
// is the *only* place `phi` redaction happens for serialization (design-rules
// Rule: implemented once, in the adapter that reads the schema modifier).

inline void json_escape(const std::string& in, std::string& out) {
    for (unsigned char c : in) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    static const char* hex = "0123456789abcdef";
                    out += "\\u00";
                    out += hex[(c >> 4) & 0xF];
                    out += hex[c & 0xF];
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
}

inline void xml_escape(const std::string& in, std::string& out) {
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

inline std::string pad(int n) { return std::string(n > 0 ? n : 0, ' '); }

struct Ctx { Format fmt; };

inline void walk_message(const ::google::protobuf::Message& msg, const Ctx& cx,
                         int indent, std::string& out);

// a single scalar/enum value (no key), formatted for `cx.fmt`
inline void scalar_value(const ::google::protobuf::Message& msg,
                         const ::google::protobuf::Reflection* refl,
                         const FD* f, int idx, bool repeated, const Ctx& cx,
                         std::string& out) {
    const bool quote_strings = cx.fmt != Format::XML;
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:
            out += std::to_string(repeated ? refl->GetRepeatedInt32(msg, f, idx)
                                           : refl->GetInt32(msg, f));
            break;
        case FD::CPPTYPE_INT64:
            out += std::to_string(repeated ? refl->GetRepeatedInt64(msg, f, idx)
                                           : refl->GetInt64(msg, f));
            break;
        case FD::CPPTYPE_UINT32:
            out += std::to_string(repeated ? refl->GetRepeatedUInt32(msg, f, idx)
                                           : refl->GetUInt32(msg, f));
            break;
        case FD::CPPTYPE_UINT64:
            out += std::to_string(repeated ? refl->GetRepeatedUInt64(msg, f, idx)
                                           : refl->GetUInt64(msg, f));
            break;
        case FD::CPPTYPE_DOUBLE:
            out += std::to_string(repeated ? refl->GetRepeatedDouble(msg, f, idx)
                                           : refl->GetDouble(msg, f));
            break;
        case FD::CPPTYPE_FLOAT:
            out += std::to_string(repeated ? refl->GetRepeatedFloat(msg, f, idx)
                                           : refl->GetFloat(msg, f));
            break;
        case FD::CPPTYPE_BOOL:
            out += (repeated ? refl->GetRepeatedBool(msg, f, idx)
                             : refl->GetBool(msg, f)) ? "true" : "false";
            break;
        case FD::CPPTYPE_ENUM: {
            const std::string name(
                (repeated ? refl->GetRepeatedEnum(msg, f, idx)
                          : refl->GetEnum(msg, f))->name());
            if (quote_strings) { out += '"'; out += name; out += '"'; }
            else out += name;
            break;
        }
        case FD::CPPTYPE_STRING: {
            const std::string s = repeated ? refl->GetRepeatedString(msg, f, idx)
                                           : refl->GetString(msg, f);
            if (cx.fmt == Format::XML) { xml_escape(s, out); }
            else { out += '"'; json_escape(s, out); out += '"'; }
            break;
        }
        case FD::CPPTYPE_MESSAGE:
            break;  // handled by the caller
    }
}

// the fixed placeholder, quoted for JSON/YAML, bare text for XML
inline void placeholder(const Ctx& cx, std::string& out) {
    if (cx.fmt == Format::XML) out += ::harpia::redaction::kPlaceholder;
    else { out += '"'; out += ::harpia::redaction::kPlaceholder; out += '"'; }
}

// map<K,V> field, formatted for `cx.fmt` (mirrors the per-format engines'
// generic MapEntry handling). Not reached for a `phi`-tagged map field -- the
// caller emits the placeholder for that before getting here.
inline void walk_map(const ::google::protobuf::Message& msg,
                     const ::google::protobuf::Reflection* refl, const FD* f,
                     const std::string& key, const Ctx& cx, int indent,
                     std::string& out) {
    const int n = refl->FieldSize(msg, f);
    if (cx.fmt == Format::JSON) {
        out += '"'; json_escape(key, out); out += "\":{";
        for (int k = 0; k < n; ++k) {
            if (k) out += ',';
            const auto& e = refl->GetRepeatedMessage(msg, f, k);
            const auto* er = e.GetReflection();
            const auto* ed = e.GetDescriptor();
            const auto* kf = ed->FindFieldByName("key");
            const auto* vf = ed->FindFieldByName("value");
            out += '"';
            std::string kbuf;
            scalar_value(e, er, kf, 0, false, cx, kbuf);
            // key is always a JSON string; strip quotes scalar_value added
            if (kf->cpp_type() == FD::CPPTYPE_STRING && kbuf.size() >= 2)
                kbuf = kbuf.substr(1, kbuf.size() - 2);
            json_escape(kbuf, out);
            out += "\":";
            if (vf->cpp_type() == FD::CPPTYPE_MESSAGE)
                walk_message(er->GetMessage(e, vf), cx, indent, out);
            else
                scalar_value(e, er, vf, 0, false, cx, out);
        }
        out += '}';
        return;
    }
    if (cx.fmt == Format::XML) {
        for (int k = 0; k < n; ++k) {
            const auto& e = refl->GetRepeatedMessage(msg, f, k);
            const auto* er = e.GetReflection();
            const auto* ed = e.GetDescriptor();
            out += "<" + key + "><key>";
            scalar_value(e, er, ed->FindFieldByName("key"), 0, false, cx, out);
            out += "</key><value>";
            const auto* vf = ed->FindFieldByName("value");
            if (vf->cpp_type() == FD::CPPTYPE_MESSAGE)
                walk_message(er->GetMessage(e, vf), cx, indent, out);
            else
                scalar_value(e, er, vf, 0, false, cx, out);
            out += "</value></" + key + ">";
        }
        return;
    }
    // YAML
    out += pad(indent) + key + ":";
    if (n == 0) { out += " {}\n"; return; }
    out += "\n";
    for (int k = 0; k < n; ++k) {
        const auto& e = refl->GetRepeatedMessage(msg, f, k);
        const auto* er = e.GetReflection();
        const auto* ed = e.GetDescriptor();
        out += pad(indent + 2);
        scalar_value(e, er, ed->FindFieldByName("key"), 0, false, cx, out);
        out += ":";
        const auto* vf = ed->FindFieldByName("value");
        if (vf->cpp_type() == FD::CPPTYPE_MESSAGE) {
            std::string block;
            walk_message(er->GetMessage(e, vf), cx, indent + 4, block);
            if (block.empty()) out += " {}\n";
            else { out += "\n"; out += block; }
        } else {
            out += " ";
            scalar_value(e, er, vf, 0, false, cx, out);
            out += "\n";
        }
    }
}

inline void walk_field(const ::google::protobuf::Message& msg,
                       const ::google::protobuf::Reflection* refl, const FD* f,
                       const Ctx& cx, int indent, std::string& out) {
    const std::string key(f->name());
    const bool redact =
        ::harpia::redaction::should_redact(msg.GetDescriptor()->name(), key);

    if (f->is_map() && !redact) {
        walk_map(msg, refl, f, key, cx, indent, out);
        return;
    }

    if (cx.fmt == Format::JSON) {
        out += '"'; json_escape(key, out); out += "\":";
        if (redact) { placeholder(cx, out); return; }
        if (f->is_repeated()) {
            const int n = refl->FieldSize(msg, f);
            out += '[';
            for (int k = 0; k < n; ++k) {
                if (k) out += ',';
                if (f->cpp_type() == FD::CPPTYPE_MESSAGE)
                    walk_message(refl->GetRepeatedMessage(msg, f, k), cx, indent, out);
                else
                    scalar_value(msg, refl, f, k, true, cx, out);
            }
            out += ']';
        } else if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
            walk_message(refl->GetMessage(msg, f), cx, indent, out);
        } else {
            scalar_value(msg, refl, f, 0, false, cx, out);
        }
        return;
    }

    if (cx.fmt == Format::XML) {
        if (redact) {
            out += "<" + key + ">";
            placeholder(cx, out);
            out += "</" + key + ">";
            return;
        }
        if (f->is_repeated()) {
            const int n = refl->FieldSize(msg, f);
            for (int k = 0; k < n; ++k) {
                out += "<" + key + ">";
                if (f->cpp_type() == FD::CPPTYPE_MESSAGE)
                    walk_message(refl->GetRepeatedMessage(msg, f, k), cx, indent, out);
                else
                    scalar_value(msg, refl, f, k, true, cx, out);
                out += "</" + key + ">";
            }
        } else {
            out += "<" + key + ">";
            if (f->cpp_type() == FD::CPPTYPE_MESSAGE)
                walk_message(refl->GetMessage(msg, f), cx, indent, out);
            else
                scalar_value(msg, refl, f, 0, false, cx, out);
            out += "</" + key + ">";
        }
        return;
    }

    // YAML
    out += pad(indent) + key + ":";
    if (redact) { out += " "; placeholder(cx, out); out += "\n"; return; }
    if (f->is_repeated()) {
        const int n = refl->FieldSize(msg, f);
        if (n == 0) { out += " []\n"; return; }
        out += "\n";
        for (int k = 0; k < n; ++k) {
            if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
                std::string block;
                walk_message(refl->GetRepeatedMessage(msg, f, k), cx, indent + 4, block);
                if (block.empty()) { out += pad(indent + 2) + "- {}\n"; }
                else {
                    // splice "- " onto the first line, keep the rest aligned
                    out += pad(indent + 2) + "- " +
                           block.substr(std::min<size_t>(
                               block.size(), static_cast<size_t>(indent) + 4));
                }
            } else {
                out += pad(indent + 2) + "- ";
                scalar_value(msg, refl, f, k, true, cx, out);
                out += "\n";
            }
        }
    } else if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
        std::string block;
        walk_message(refl->GetMessage(msg, f), cx, indent + 2, block);
        if (block.empty()) out += " {}\n";
        else { out += "\n"; out += block; }
    } else {
        out += " ";
        scalar_value(msg, refl, f, 0, false, cx, out);
        out += "\n";
    }
}

inline void walk_message(const ::google::protobuf::Message& msg, const Ctx& cx,
                         int indent, std::string& out) {
    const auto* d = msg.GetDescriptor();
    const auto* refl = msg.GetReflection();

    if (cx.fmt == Format::JSON) {
        out += '{';
        bool first = true;
        for (int i = 0; i < d->field_count(); ++i) {
            const auto* f = d->field(i);
            if (!f->is_repeated() && f->has_presence() && !refl->HasField(msg, f))
                continue;
            if (!first) out += ',';
            first = false;
            walk_field(msg, refl, f, cx, indent, out);
        }
        out += '}';
        return;
    }

    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        if (!f->is_repeated() && f->has_presence() && !refl->HasField(msg, f))
            continue;
        walk_field(msg, refl, f, cx, indent, out);
    }
}

inline std::string redacted_to_string(const ::google::protobuf::Message& msg,
                                      Format fmt) {
    Ctx cx{fmt};
    std::string out;
    if (fmt == Format::XML) {
        const std::string root(msg.GetDescriptor()->name());
        out += "<" + root + ">";
        walk_message(msg, cx, 0, out);
        out += "</" + root + ">";
    } else {
        walk_message(msg, cx, 0, out);
        if (fmt == Format::YAML && out.empty()) out = "{}\n";
    }
    return out;
}

}  // namespace detail

// message -> text, in the requested format. `phi` values are replaced with
// `[REDACTED]` when redaction is enabled (the default) and the message tree
// declares a `phi` field; otherwise this is a straight pass-through to the
// unchanged per-format engine. Never throws.
inline std::string to_string(const ::google::protobuf::Message& msg, Format fmt) {
    if (::harpia::redaction::redaction_enabled() &&
        detail::tree_has_phi(msg.GetDescriptor())) {
        return detail::redacted_to_string(msg, fmt);
    }
    switch (fmt) {
        case Format::XML:  return ::harpia::xml::to_xml(msg);
        case Format::YAML: return ::harpia::yaml::to_yaml(msg);
        case Format::JSON: break;
    }
    return detail::to_json_passthrough(msg);
}

// text -> message, in the given format. Returns false when the input does not
// parse as that format. A *redacted* document is not expected to round-trip to
// the original -- `phi` fields come back empty / default (or, for a numeric
// field fed the JSON string placeholder, the parse simply fails).
inline bool from_string(const std::string& in, ::google::protobuf::Message* msg,
                        Format fmt) {
    switch (fmt) {
        case Format::XML:  return ::harpia::xml::from_xml(in, msg);
        case Format::YAML: return ::harpia::yaml::from_yaml(in, msg);
        case Format::JSON: break;
    }
    return detail::from_json(in, msg);
}

}  // namespace serialize
}  // namespace harpia

#endif  // HARPIA_SERIALIZE_RUNTIME_H
