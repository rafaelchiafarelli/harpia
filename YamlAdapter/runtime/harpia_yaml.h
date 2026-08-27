// harpia Stage 10 YAML runtime (hand-written, not generated).
//
// Generic, reflection-based YAML serialization for any protobuf message. The
// per-message <name>_yaml.h wrappers include this; callers use:
//
//     std::string yaml = harpia::yaml::to_yaml(msg);   // msg  -> YAML
//     harpia::yaml::from_yaml(yaml, &msg);             // YAML -> msg
//
// Walking the message via the protobuf descriptor/reflection API means this
// handles nested messages, repeated fields, enums and maps without any
// per-field generated code -- the same approach as XmlAdapter/runtime/harpia_xml.h
// (protobuf has no built-in YAML any more than it has XML).
//
// Emitted YAML is block style, two-space indent, mapping at the top level (no
// wrapper key -- mirrors the JSON adapter's shape, not XML's type-name root).
// Strings are always double-quoted; scalars/enums are bare. Absent fields with
// real presence (singular message fields, `optional` scalars) are omitted, the
// same rule harpia_xml.h uses. The reader accepts exactly this subset.
#ifndef HARPIA_YAML_RUNTIME_H
#define HARPIA_YAML_RUNTIME_H

#include <cstdint>
#include <cstdlib>
#include <sstream>
#include <string>
#include <vector>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>

// windows.h (pulled in transitively via Crow/asio on Windows) defines
// GetMessage as a macro that would otherwise rewrite Reflection::GetMessage()
// below -- same guard as harpia_xml.h.
#ifdef GetMessage
#undef GetMessage
#endif

namespace harpia {
namespace yaml {
namespace detail {

using FD = ::google::protobuf::FieldDescriptor;

inline std::string pad(int n) { return std::string(n > 0 ? n : 0, ' '); }

inline void quote(const std::string& in, std::string& out) {
    out += '"';
    for (char c : in) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"':  out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\t': out += "\\t"; break;
            default:   out += c;
        }
    }
    out += '"';
}

inline void write_message(const ::google::protobuf::Message& msg, int indent,
                          std::string& out);

// a singular scalar/enum/string value, no key, no newline
inline void write_singular_inline(const ::google::protobuf::Message& msg,
                                  const ::google::protobuf::Reflection* refl,
                                  const FD* f, std::string& out) {
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:  out += std::to_string(refl->GetInt32(msg, f)); break;
        case FD::CPPTYPE_INT64:  out += std::to_string(refl->GetInt64(msg, f)); break;
        case FD::CPPTYPE_UINT32: out += std::to_string(refl->GetUInt32(msg, f)); break;
        case FD::CPPTYPE_UINT64: out += std::to_string(refl->GetUInt64(msg, f)); break;
        case FD::CPPTYPE_DOUBLE: out += std::to_string(refl->GetDouble(msg, f)); break;
        case FD::CPPTYPE_FLOAT:  out += std::to_string(refl->GetFloat(msg, f)); break;
        case FD::CPPTYPE_BOOL:   out += refl->GetBool(msg, f) ? "true" : "false"; break;
        case FD::CPPTYPE_ENUM:   out += refl->GetEnum(msg, f)->name(); break;
        case FD::CPPTYPE_STRING: quote(refl->GetString(msg, f), out); break;
        case FD::CPPTYPE_MESSAGE: break;  // handled as a block by the caller
    }
}

inline void write_repeated_inline(const ::google::protobuf::Message& msg,
                                  const ::google::protobuf::Reflection* refl,
                                  const FD* f, int k, std::string& out) {
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:  out += std::to_string(refl->GetRepeatedInt32(msg, f, k)); break;
        case FD::CPPTYPE_INT64:  out += std::to_string(refl->GetRepeatedInt64(msg, f, k)); break;
        case FD::CPPTYPE_UINT32: out += std::to_string(refl->GetRepeatedUInt32(msg, f, k)); break;
        case FD::CPPTYPE_UINT64: out += std::to_string(refl->GetRepeatedUInt64(msg, f, k)); break;
        case FD::CPPTYPE_DOUBLE: out += std::to_string(refl->GetRepeatedDouble(msg, f, k)); break;
        case FD::CPPTYPE_FLOAT:  out += std::to_string(refl->GetRepeatedFloat(msg, f, k)); break;
        case FD::CPPTYPE_BOOL:   out += refl->GetRepeatedBool(msg, f, k) ? "true" : "false"; break;
        case FD::CPPTYPE_ENUM:   out += refl->GetRepeatedEnum(msg, f, k)->name(); break;
        case FD::CPPTYPE_STRING: quote(refl->GetRepeatedString(msg, f, k), out); break;
        case FD::CPPTYPE_MESSAGE: break;
    }
}

// turn a rendered block (lines at column dashIndent+2) into a "- " list item:
// the first line's leading indent becomes `pad(dashIndent) + "- "`, the rest
// stay put (already aligned, since "- " is exactly two columns).
inline std::string splice_dash(const std::string& block, int dashIndent) {
    std::string out;
    size_t pos = 0;
    bool first = true;
    while (pos <= block.size()) {
        size_t nl = block.find('\n', pos);
        bool last = (nl == std::string::npos);
        std::string line = block.substr(pos, last ? std::string::npos : nl - pos);
        if (line.empty() && last) break;
        if (first) {
            size_t strip = std::min<size_t>(line.size(),
                                            static_cast<size_t>(dashIndent) + 2);
            out += pad(dashIndent) + "- " + line.substr(strip);
            first = false;
        } else {
            out += line;
        }
        if (last) break;
        out += '\n';
        pos = nl + 1;
    }
    return out;
}

inline void write_map(const ::google::protobuf::Message& msg,
                      const ::google::protobuf::Reflection* refl,
                      const FD* f, const std::string& key, int indent,
                      std::string& out) {
    const int n = refl->FieldSize(msg, f);
    out += pad(indent) + key + ":";
    if (n == 0) { out += " {}\n"; return; }
    out += "\n";
    for (int k = 0; k < n; ++k) {
        const auto& entry = refl->GetRepeatedMessage(msg, f, k);
        const auto* ed = entry.GetDescriptor();
        const auto* er = entry.GetReflection();
        const auto* kf = ed->FindFieldByName("key");
        const auto* vf = ed->FindFieldByName("value");
        out += pad(indent + 2);
        write_singular_inline(entry, er, kf, out);
        out += ":";
        if (vf->cpp_type() == FD::CPPTYPE_MESSAGE) {
            std::string block;
            write_message(er->GetMessage(entry, vf), indent + 4, block);
            if (block.empty()) out += " {}\n";
            else { out += "\n"; out += block; }
        } else {
            out += " ";
            write_singular_inline(entry, er, vf, out);
            out += "\n";
        }
    }
}

inline void write_message(const ::google::protobuf::Message& msg, int indent,
                          std::string& out) {
    const auto* d = msg.GetDescriptor();
    const auto* refl = msg.GetReflection();
    for (int i = 0; i < d->field_count(); ++i) {
        const auto* f = d->field(i);
        // direct-init by value: FieldDescriptor::name() is const std::string&
        // in older protobuf, std::string_view in newer -- see harpia_xml.h.
        const std::string key(f->name());

        if (f->is_map()) {
            write_map(msg, refl, f, key, indent, out);
            continue;
        }
        if (f->is_repeated()) {
            const int n = refl->FieldSize(msg, f);
            out += pad(indent) + key + ":";
            if (n == 0) { out += " []\n"; continue; }
            out += "\n";
            for (int k = 0; k < n; ++k) {
                if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
                    std::string block;
                    write_message(refl->GetRepeatedMessage(msg, f, k),
                                  indent + 4, block);
                    if (block.empty()) out += pad(indent + 2) + "- {}\n";
                    else out += splice_dash(block, indent + 2);
                } else {
                    out += pad(indent + 2) + "- ";
                    write_repeated_inline(msg, refl, f, k, out);
                    out += "\n";
                }
            }
            continue;
        }
        // singular
        if (f->has_presence() && !refl->HasField(msg, f)) continue;
        if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
            std::string block;
            write_message(refl->GetMessage(msg, f), indent + 2, block);
            out += pad(indent) + key + ":";
            if (block.empty()) out += " {}\n";
            else { out += "\n"; out += block; }
        } else {
            out += pad(indent) + key + ": ";
            write_singular_inline(msg, refl, f, out);
            out += "\n";
        }
    }
}

// ---- read (YAML -> message) --------------------------------------------------

struct Ln { int indent; std::string s; };  // s: no leading indent, right-trimmed

inline std::vector<Ln> tokenize(const std::string& y) {
    std::vector<Ln> v;
    std::stringstream ss(y);
    std::string line;
    while (std::getline(ss, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t ind = 0;
        while (ind < line.size() && line[ind] == ' ') ++ind;
        std::string content = line.substr(ind);
        while (!content.empty() &&
               (content.back() == ' ' || content.back() == '\t'))
            content.pop_back();
        if (content.empty() || content == "---" || content == "...") continue;
        v.push_back({static_cast<int>(ind), content});
    }
    return v;
}

inline std::string unquote(const std::string& in) {
    if (in.size() >= 2 && in.front() == '"' && in.back() == '"') {
        std::string o;
        for (size_t k = 1; k + 1 < in.size(); ++k) {
            char c = in[k];
            if (c == '\\' && k + 2 < in.size()) {
                char nx = in[++k];
                o += (nx == 'n') ? '\n' : (nx == 't') ? '\t' : nx;
            } else {
                o += c;
            }
        }
        return o;
    }
    return in;
}

inline long long to_ll(const std::string& t) {
    return t.empty() ? 0 : std::strtoll(t.c_str(), nullptr, 10);
}
inline unsigned long long to_ull(const std::string& t) {
    return t.empty() ? 0 : std::strtoull(t.c_str(), nullptr, 10);
}
inline double to_d(const std::string& t) {
    return t.empty() ? 0.0 : std::strtod(t.c_str(), nullptr);
}

// split "key: value" / "key:" / quoted-key forms. key keeps its quotes (if any).
inline void split_kv(const std::string& s, std::string& key, std::string& val,
                     bool& hasVal) {
    size_t p;
    if (!s.empty() && s[0] == '"') {
        size_t q = 1;
        while (q < s.size()) {
            if (s[q] == '\\') q += 2;
            else if (s[q] == '"') break;
            else ++q;
        }
        key = s.substr(0, std::min(q + 1, s.size()));
        p = s.find(':', std::min(q + 1, s.size()));
    } else {
        p = s.find(':');
        key = (p == std::string::npos) ? s : s.substr(0, p);
    }
    if (p == std::string::npos) { val.clear(); hasVal = false; return; }
    val = s.substr(p + 1);
    size_t b = val.find_first_not_of(' ');
    val = (b == std::string::npos) ? std::string() : val.substr(b);
    hasVal = !val.empty();
}

inline void set_scalar(::google::protobuf::Message* msg,
                       const ::google::protobuf::Reflection* refl, const FD* f,
                       const std::string& raw, bool repeated, int& hits) {
    if (!f) return;
    const std::string v = unquote(raw);
    switch (f->cpp_type()) {
        case FD::CPPTYPE_INT32:
            repeated ? refl->AddInt32(msg, f, static_cast<int32_t>(to_ll(v)))
                     : refl->SetInt32(msg, f, static_cast<int32_t>(to_ll(v)));
            break;
        case FD::CPPTYPE_INT64:
            repeated ? refl->AddInt64(msg, f, to_ll(v))
                     : refl->SetInt64(msg, f, to_ll(v));
            break;
        case FD::CPPTYPE_UINT32:
            repeated ? refl->AddUInt32(msg, f, static_cast<uint32_t>(to_ull(v)))
                     : refl->SetUInt32(msg, f, static_cast<uint32_t>(to_ull(v)));
            break;
        case FD::CPPTYPE_UINT64:
            repeated ? refl->AddUInt64(msg, f, to_ull(v))
                     : refl->SetUInt64(msg, f, to_ull(v));
            break;
        case FD::CPPTYPE_DOUBLE:
            repeated ? refl->AddDouble(msg, f, to_d(v))
                     : refl->SetDouble(msg, f, to_d(v));
            break;
        case FD::CPPTYPE_FLOAT:
            repeated ? refl->AddFloat(msg, f, static_cast<float>(to_d(v)))
                     : refl->SetFloat(msg, f, static_cast<float>(to_d(v)));
            break;
        case FD::CPPTYPE_BOOL: {
            const bool b = (v == "true" || v == "1");
            repeated ? refl->AddBool(msg, f, b) : refl->SetBool(msg, f, b);
            break;
        }
        case FD::CPPTYPE_ENUM: {
            const auto* et = f->enum_type();
            const auto* ev = et->FindValueByName(v);
            if (!ev) ev = et->FindValueByNumber(static_cast<int>(to_ll(v)));
            if (!ev) return;
            repeated ? refl->AddEnum(msg, f, ev) : refl->SetEnum(msg, f, ev);
            break;
        }
        case FD::CPPTYPE_STRING:
            repeated ? refl->AddString(msg, f, v) : refl->SetString(msg, f, v);
            break;
        case FD::CPPTYPE_MESSAGE:
            return;  // never inline
    }
    ++hits;
}

inline void read_mapping(const std::vector<Ln>& L, size_t& i, int indent,
                         ::google::protobuf::Message* msg, int& hits);

inline void skip_block(const std::vector<Ln>& L, size_t& i, int indent) {
    while (i < L.size() && L[i].indent > indent) ++i;
}

inline void read_sequence(const std::vector<Ln>& L, size_t& i, int indent,
                          ::google::protobuf::Message* msg, const FD* f,
                          int& hits) {
    const auto* refl = msg->GetReflection();
    while (i < L.size() && L[i].indent == indent && !L[i].s.empty() &&
           L[i].s[0] == '-') {
        std::string rest = L[i].s.substr(1);
        size_t b = rest.find_first_not_of(' ');
        rest = (b == std::string::npos) ? std::string() : rest.substr(b);
        ++i;
        if (f->cpp_type() == FD::CPPTYPE_MESSAGE) {
            auto* item = refl->AddMessage(msg, f);
            ++hits;
            if (!rest.empty() && rest != "{}") {
                // `rest` is this item's first "key: ..." line, at column indent+2
                std::string key, val;
                bool hasVal;
                split_kv(rest, key, val, hasVal);
                const auto* itf =
                    item->GetDescriptor()->FindFieldByName(unquote(key));
                if (itf && hasVal && val != "{}" && val != "[]") {
                    set_scalar(item, item->GetReflection(), itf, val,
                               itf->is_repeated(), hits);
                } else if (itf && !hasVal && i < L.size() &&
                           L[i].indent > indent + 2) {
                    int ci = L[i].indent;
                    if (!L[i].s.empty() && L[i].s[0] == '-')
                        read_sequence(L, i, ci, item, itf, hits);
                    else if (itf->cpp_type() == FD::CPPTYPE_MESSAGE)
                        read_mapping(L, i, ci,
                                     item->GetReflection()->MutableMessage(item, itf),
                                     hits);
                    else
                        skip_block(L, i, indent + 2);
                }
            }
            // remaining fields of this item (column indent+2)
            read_mapping(L, i, indent + 2, item, hits);
        } else {
            if (!rest.empty() && rest != "[]")
                set_scalar(msg, refl, f, rest, /*repeated=*/true, hits);
        }
    }
}

inline void read_map(const std::vector<Ln>& L, size_t& i, int indent,
                     ::google::protobuf::Message* msg, const FD* f, int& hits) {
    const auto* refl = msg->GetReflection();
    while (i < L.size() && L[i].indent == indent && !L[i].s.empty() &&
           L[i].s[0] != '-') {
        std::string key, val;
        bool hasVal;
        split_kv(L[i].s, key, val, hasVal);
        ++i;
        auto* entry = refl->AddMessage(msg, f);
        ++hits;
        const auto* ed = entry->GetDescriptor();
        auto* er = entry->GetReflection();
        int sink = 0;
        set_scalar(entry, er, ed->FindFieldByName("key"), key, false, sink);
        const auto* vf = ed->FindFieldByName("value");
        if (hasVal) {
            if (val != "{}" && val != "[]")
                set_scalar(entry, er, vf, val, false, sink);
        } else if (i < L.size() && L[i].indent > indent && vf &&
                   vf->cpp_type() == FD::CPPTYPE_MESSAGE) {
            read_mapping(L, i, L[i].indent, er->MutableMessage(entry, vf), hits);
        }
    }
}

// process one mapping entry `s` (sitting at column `indent`); `i` already points
// past `s` and may be advanced over the entry's block children.
inline void apply_entry(const std::vector<Ln>& L, size_t& i, int indent,
                        const std::string& s,
                        ::google::protobuf::Message* msg, int& hits) {
    const auto* d = msg->GetDescriptor();
    const auto* refl = msg->GetReflection();
    std::string key, val;
    bool hasVal;
    split_kv(s, key, val, hasVal);
    const auto* f = d->FindFieldByName(unquote(key));
    if (!f) {
        if (!hasVal) skip_block(L, i, indent);
        return;
    }
    if (hasVal) {
        if (val != "[]" && val != "{}")
            set_scalar(msg, refl, f, val, f->is_repeated(), hits);
        return;
    }
    if (i >= L.size() || L[i].indent <= indent) return;  // empty block
    const int childIndent = L[i].indent;
    if (!L[i].s.empty() && L[i].s[0] == '-') {
        read_sequence(L, i, childIndent, msg, f, hits);
    } else if (f->is_map()) {
        read_map(L, i, childIndent, msg, f, hits);
    } else if (f->cpp_type() == FD::CPPTYPE_MESSAGE && !f->is_repeated()) {
        read_mapping(L, i, childIndent, refl->MutableMessage(msg, f), hits);
    } else {
        skip_block(L, i, childIndent);
    }
}

inline void read_mapping(const std::vector<Ln>& L, size_t& i, int indent,
                         ::google::protobuf::Message* msg, int& hits) {
    while (i < L.size() && L[i].indent == indent && !L[i].s.empty() &&
           L[i].s[0] != '-') {
        const std::string s = L[i].s;
        ++i;
        apply_entry(L, i, indent, s, msg, hits);
    }
}

}  // namespace detail

// message -> YAML (block style, two-space indent, top-level mapping).
inline std::string to_yaml(const ::google::protobuf::Message& msg) {
    std::string out;
    detail::write_message(msg, 0, out);
    if (out.empty()) out = "{}\n";
    return out;
}

// YAML -> message. Returns false when nothing in the text matched a field of
// `msg` (the "this isn't our format" signal, mirroring from_xml's parse-fail
// false); an empty document or "{}" is a valid empty message and returns true.
inline bool from_yaml(const std::string& yaml, ::google::protobuf::Message* msg) {
    const auto lines = detail::tokenize(yaml);
    size_t i = 0;
    int hits = 0;
    detail::read_mapping(lines, i, 0, msg, hits);
    if (!lines.empty() && hits == 0) return false;
    return true;
}

}  // namespace yaml
}  // namespace harpia

#endif  // HARPIA_YAML_RUNTIME_H
