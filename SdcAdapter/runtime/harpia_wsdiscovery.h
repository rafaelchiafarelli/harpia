// Generated project runtime -- copied verbatim by harpia SdcAdapter. Do not edit.
#ifndef HARPIA_WSDISCOVERY_H
#define HARPIA_WSDISCOVERY_H

/// \file
/// \brief Minimal WS-Discovery (OASIS WS-DD 2009) probe/resolve responder.
///
/// Answers multicast \c Probe and unicast \c Resolve messages on
/// 239.255.255.250:3702 so an IEEE 11073 SDC / DPWS-aware client can locate
/// this project's existing Stage 11 SOAP endpoint with zero configuration.
///
/// **Additive.** It neither replaces nor modifies the SOAP endpoint; a
/// ProbeMatch just carries the SOAP URL in its \c XAddrs so a client knows
/// where to connect.
///
/// **Threading.** Not thread-safe. Register every endpoint with
/// harpia::wsdiscovery::Responder::add() before calling
/// harpia::wsdiscovery::Responder::start(); start() runs a single background
/// listener thread and stop() joins it. Same caller-synchronised contract as
/// the rest of the generated runtime.
///
/// **Portability.** The message core (parse_request(), build_response(),
/// Responder::handle_datagram()) is plain C++17. The UDP-multicast listener
/// (start()/stop()) is POSIX-only for now; on Windows start() returns false
/// and the responder is inert (native Windows discovery is a separate
/// follow-on, mirroring how ZMQ CURVE handled its Windows build).

#include <cstddef>
#include <cstring>
#include <string>
#include <vector>

#include "tinyxml2.h"

#ifndef _WIN32
#  include <atomic>
#  include <thread>
#  include <arpa/inet.h>
#  include <netinet/in.h>
#  include <sys/socket.h>
#  include <unistd.h>
#endif

namespace harpia {
namespace wsdiscovery {

/// Standard WS-Discovery IPv4 multicast group.
inline const char* multicast_group() { return "239.255.255.250"; }
/// Standard WS-Discovery UDP port.
inline unsigned short port() { return 3702; }

inline const char* action_probe() {
    return "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/Probe";
}
inline const char* action_probe_matches() {
    return "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/ProbeMatches";
}
inline const char* action_resolve() {
    return "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/Resolve";
}
inline const char* action_resolve_matches() {
    return "http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01/ResolveMatches";
}

/// One advertised endpoint -- the SOAP service one generated message exposes.
struct Endpoint {
    std::string endpoint_reference;       ///< stable urn:uuid: reference
    std::vector<std::string> types;       ///< QNames, e.g. {"dpws:Device"}
    std::vector<std::string> scopes;      ///< scope URIs
    std::string xaddrs;                   ///< transport address (SOAP URL)
};

namespace detail {

inline std::string local_name(const char* raw) {
    std::string s = raw ? raw : "";
    const std::string::size_type pos = s.find(':');
    return pos == std::string::npos ? s : s.substr(pos + 1);
}

/// Depth-first search for the first element with the given local (prefix-
/// stripped) name, \p el included.
inline const tinyxml2::XMLElement* first_by_local(
        const tinyxml2::XMLElement* el, const char* want) {
    if (!el) return nullptr;
    if (local_name(el->Name()) == want) return el;
    for (const tinyxml2::XMLElement* c = el->FirstChildElement();
         c; c = c->NextSiblingElement()) {
        const tinyxml2::XMLElement* hit = first_by_local(c, want);
        if (hit) return hit;
    }
    return nullptr;
}

inline std::string element_text(const tinyxml2::XMLElement* el) {
    return (el && el->GetText()) ? std::string(el->GetText()) : std::string();
}

inline std::vector<std::string> split_ws(const std::string& s) {
    std::vector<std::string> out;
    std::string cur;
    for (char ch : s) {
        if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r') {
            if (!cur.empty()) { out.push_back(cur); cur.clear(); }
        } else {
            cur.push_back(ch);
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

inline std::string join_ws(const std::vector<std::string>& v) {
    std::string out;
    for (std::size_t i = 0; i < v.size(); ++i) {
        if (i) out.push_back(' ');
        out += v[i];
    }
    return out;
}

inline std::string xml_escape(const std::string& in) {
    std::string out;
    out.reserve(in.size());
    for (char c : in) {
        switch (c) {
            case '&': out += "&amp;"; break;
            case '<': out += "&lt;"; break;
            case '>': out += "&gt;"; break;
            case '"': out += "&quot;"; break;
            default: out.push_back(c);
        }
    }
    return out;
}

}  // namespace detail

/// A parsed inbound Probe or Resolve.
struct Request {
    enum Kind { kNone, kProbe, kResolve };
    Kind kind = kNone;
    std::string message_id;                ///< wsa:MessageID, echoed as RelatesTo
    std::vector<std::string> types;        ///< Probe selector
    std::vector<std::string> scopes;       ///< Probe selector
    std::string target_epr;                ///< Resolve target endpoint reference
};

/// Parse one datagram. An unparsable payload or an unrecognised wsa:Action
/// yields Request::kNone.
inline Request parse_request(const std::string& datagram) {
    Request r;
    tinyxml2::XMLDocument doc;
    if (doc.Parse(datagram.c_str(), datagram.size()) != tinyxml2::XML_SUCCESS)
        return r;
    const tinyxml2::XMLElement* root = doc.RootElement();
    if (!root) return r;

    const std::string act =
        detail::element_text(detail::first_by_local(root, "Action"));
    r.message_id = detail::element_text(detail::first_by_local(root, "MessageID"));

    if (act == action_probe()) {
        r.kind = Request::kProbe;
        const tinyxml2::XMLElement* probe = detail::first_by_local(root, "Probe");
        if (probe) {
            r.types = detail::split_ws(
                detail::element_text(detail::first_by_local(probe, "Types")));
            r.scopes = detail::split_ws(
                detail::element_text(detail::first_by_local(probe, "Scopes")));
        }
    } else if (act == action_resolve()) {
        r.kind = Request::kResolve;
        const tinyxml2::XMLElement* rs = detail::first_by_local(root, "Resolve");
        if (rs) {
            r.target_epr =
                detail::element_text(detail::first_by_local(rs, "Address"));
        }
    }
    return r;
}

/// WS-Discovery default matching: every requested type must be present in the
/// endpoint's types, and every requested scope must be a prefix of one of the
/// endpoint's scopes. An empty selector matches everything.
inline bool endpoint_matches(const Endpoint& ep, const Request& req) {
    for (const std::string& t : req.types) {
        bool found = false;
        for (const std::string& et : ep.types)
            if (et == t) { found = true; break; }
        if (!found) return false;
    }
    for (const std::string& s : req.scopes) {
        bool found = false;
        for (const std::string& es : ep.scopes)
            if (es.size() >= s.size() && es.compare(0, s.size(), s) == 0) {
                found = true; break;
            }
        if (!found) return false;
    }
    return true;
}

inline std::string build_match(const Endpoint& ep, bool resolve) {
    const char* wrap = resolve ? "ResolveMatch" : "ProbeMatch";
    std::string b = "<wsd:";
    b += wrap;
    b += "><wsa:EndpointReference><wsa:Address>";
    b += detail::xml_escape(ep.endpoint_reference);
    b += "</wsa:Address></wsa:EndpointReference>";
    b += "<wsd:Types xmlns:dpws=\"http://docs.oasis-open.org/ws-dd/ns/dpws/2009/01\">";
    b += detail::xml_escape(detail::join_ws(ep.types));
    b += "</wsd:Types><wsd:Scopes>";
    b += detail::xml_escape(detail::join_ws(ep.scopes));
    b += "</wsd:Scopes><wsd:XAddrs>";
    b += detail::xml_escape(ep.xaddrs);
    b += "</wsd:XAddrs><wsd:MetadataVersion>1</wsd:MetadataVersion></wsd:";
    b += wrap;
    b += ">";
    return b;
}

/// Assemble a full ProbeMatches / ResolveMatches SOAP 1.2 envelope.
inline std::string build_response(const std::vector<const Endpoint*>& matches,
                                  const std::string& relates_to, bool resolve) {
    const char* action = resolve ? action_resolve_matches()
                                 : action_probe_matches();
    const char* wrap = resolve ? "ResolveMatches" : "ProbeMatches";
    std::string m = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>";
    m += "<soap:Envelope xmlns:soap=\"http://www.w3.org/2003/05/soap-envelope\""
         " xmlns:wsa=\"http://www.w3.org/2005/08/addressing\""
         " xmlns:wsd=\"http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01\">";
    m += "<soap:Header><wsa:Action>";
    m += action;
    m += "</wsa:Action>";
    if (!relates_to.empty()) {
        m += "<wsa:RelatesTo>";
        m += detail::xml_escape(relates_to);
        m += "</wsa:RelatesTo>";
    }
    m += "</soap:Header><soap:Body><wsd:";
    m += wrap;
    m += ">";
    for (const Endpoint* ep : matches) m += build_match(*ep, resolve);
    m += "</wsd:";
    m += wrap;
    m += "></soap:Body></soap:Envelope>";
    return m;
}

/// The WS-Discovery responder: holds the advertised endpoints, answers probes.
class Responder {
public:
    Responder() = default;
    ~Responder() { stop(); }
    Responder(const Responder&) = delete;
    Responder& operator=(const Responder&) = delete;

    /// Register an endpoint to advertise. Call before start().
    void add(Endpoint ep) { endpoints_.push_back(std::move(ep)); }

    const std::vector<Endpoint>& endpoints() const { return endpoints_; }

    /// Pure request -> response for one datagram. Returns false and leaves
    /// \p out untouched when nothing should be sent: an unparsable payload, an
    /// action that is not Probe/Resolve, a Probe that matched no endpoint
    /// (WS-Discovery says stay silent), or a Resolve for an unknown endpoint
    /// reference. Socket-free, so unit tests drive it directly.
    bool handle_datagram(const std::string& in, std::string* out) const {
        const Request req = parse_request(in);
        std::vector<const Endpoint*> matches;
        if (req.kind == Request::kProbe) {
            for (const Endpoint& ep : endpoints_)
                if (endpoint_matches(ep, req)) matches.push_back(&ep);
            if (matches.empty()) return false;
            if (out) *out = build_response(matches, req.message_id, false);
            return true;
        }
        if (req.kind == Request::kResolve) {
            for (const Endpoint& ep : endpoints_)
                if (ep.endpoint_reference == req.target_epr) {
                    matches.push_back(&ep);
                    break;
                }
            if (matches.empty()) return false;
            if (out) *out = build_response(matches, req.message_id, true);
            return true;
        }
        return false;
    }

#ifndef _WIN32
    /// Bind the multicast socket and start the listener thread. Returns false
    /// if the socket could not be set up. Idempotent while running.
    bool start() {
        if (running_.load()) return true;
        fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
        if (fd_ < 0) return false;

        int yes = 1;
        ::setsockopt(fd_, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
#ifdef SO_REUSEPORT
        ::setsockopt(fd_, SOL_SOCKET, SO_REUSEPORT, &yes, sizeof(yes));
#endif
        sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_ANY);
        addr.sin_port = htons(port());
        if (::bind(fd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
            close_fd();
            return false;
        }

        ip_mreq mreq;
        std::memset(&mreq, 0, sizeof(mreq));
        mreq.imr_multiaddr.s_addr = ::inet_addr(multicast_group());
        mreq.imr_interface.s_addr = htonl(INADDR_ANY);
        ::setsockopt(fd_, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));

        running_.store(true);
        worker_ = std::thread(&Responder::loop, this);
        return true;
    }

    /// Stop the listener thread and close the socket. Safe to call when not
    /// running and from the destructor.
    void stop() {
        if (!running_.exchange(false)) {
            close_fd();
            return;
        }
        close_fd();  // unblocks recvfrom in loop()
        if (worker_.joinable()) worker_.join();
    }

private:
    void close_fd() {
        if (fd_ >= 0) {
            ::close(fd_);
            fd_ = -1;
        }
    }

    void loop() {
        std::vector<char> buf(8192);
        while (running_.load()) {
            sockaddr_in from;
            std::memset(&from, 0, sizeof(from));
            socklen_t flen = sizeof(from);
            const ssize_t n = ::recvfrom(fd_, buf.data(), buf.size() - 1, 0,
                                         reinterpret_cast<sockaddr*>(&from),
                                         &flen);
            if (n <= 0) {
                if (!running_.load()) break;
                continue;
            }
            const std::string in(buf.data(), static_cast<std::size_t>(n));
            std::string out;
            if (handle_datagram(in, &out) && !out.empty()) {
                ::sendto(fd_, out.data(), out.size(), 0,
                         reinterpret_cast<sockaddr*>(&from), flen);
            }
        }
    }

    int fd_ = -1;
    std::atomic<bool> running_{false};
    std::thread worker_;
#else
    bool start() { return false; }
    void stop() {}
#endif  // _WIN32

private:
    std::vector<Endpoint> endpoints_;
};

}  // namespace wsdiscovery
}  // namespace harpia

#endif  // HARPIA_WSDISCOVERY_H
