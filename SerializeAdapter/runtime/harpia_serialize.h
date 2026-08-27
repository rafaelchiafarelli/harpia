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
// The per-format engines are unchanged (protobuf's JSON util for JSON,
// harpia_xml.h / harpia_yaml.h reflection walkers for XML / YAML) -- this is a
// dispatch layer over them, so JSON and XML output stay byte-for-byte what
// they already were. `phi` redaction (F.3) hooks in here, once, instead of in
// three places.
#ifndef HARPIA_SERIALIZE_RUNTIME_H
#define HARPIA_SERIALIZE_RUNTIME_H

#include <string>

#include <google/protobuf/message.h>
#include <google/protobuf/util/json_util.h>

#include "xml/harpia_xml.h"
#include "yaml/harpia_yaml.h"

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

// JSON via protobuf's own util -- identical to what json/<name>_json.h does
// (default MessageToJsonString settings: camelCase keys, defaults omitted).
inline std::string to_json(const ::google::protobuf::Message& msg) {
    std::string out;
    ::google::protobuf::util::MessageToJsonString(msg, &out);
    return out;
}

// same unknown-field tolerance json/<name>_json.h uses (a newer peer's added
// field must not hard-fail the parse -- see JsonAdapter/CLAUDE.md).
inline bool from_json(const std::string& in, ::google::protobuf::Message* msg) {
    ::google::protobuf::util::JsonParseOptions opts;
    opts.ignore_unknown_fields = true;
    return ::google::protobuf::util::JsonStringToMessage(in, msg, opts).ok();
}

}  // namespace detail

// message -> text, in the requested format. Never throws; on an unknown enum
// value falls back to JSON. The structure/keys the underlying engine would
// emit are always emitted (the reflection walkers never drop a field; protobuf
// JSON omits proto3 defaults, exactly as it does today).
inline std::string to_string(const ::google::protobuf::Message& msg, Format fmt) {
    switch (fmt) {
        case Format::XML:  return ::harpia::xml::to_xml(msg);
        case Format::YAML: return ::harpia::yaml::to_yaml(msg);
        case Format::JSON: break;
    }
    return detail::to_json(msg);
}

// text -> message, in the given format. Returns false when the input does not
// parse as that format (mirrors each engine's own failure signal).
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
