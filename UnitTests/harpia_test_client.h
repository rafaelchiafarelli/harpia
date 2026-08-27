// harpia_test_client.h -- minimal blocking HTTP/1.1 loopback client for the
// generated live-HTTP tests. Replaces cpp-httplib's ::httplib::Client on the
// test side of the cpp-httplib -> Crow migration; Crow ships no client.
//
// Header-only (no asio, no extra vendored dep) so it stays trivially portable
// across the target boards. Speaks just enough HTTP/1.1 to drive the CRUDL/
// SOAP endpoints: one request per connection with "Connection: close",
// response read to EOF, status line + body parsed out. Read/connect timeouts
// (used by the "slower server" test) map to setsockopt SO_RCVTIMEO and a
// non-blocking connect + select. POSIX sockets on Linux; Winsock2 on Windows
// (thin #ifdef shims below map the handful of divergent names/types --
// closesocket vs. close, ioctlsocket vs. fcntl(O_NONBLOCK), WSAGetLastError
// vs. errno -- the request/response logic itself is shared).
#ifndef HARPIA_TEST_CLIENT_H
#define HARPIA_TEST_CLIENT_H

#include <string>
#include <utility>
#include <vector>

#include <cstring>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using harpia_sockfd_t = SOCKET;
using harpia_socklen_t = int;
static constexpr harpia_sockfd_t kHarpiaInvalidSocket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
using harpia_sockfd_t = int;
using harpia_socklen_t = socklen_t;
static constexpr harpia_sockfd_t kHarpiaInvalidSocket = -1;
#endif

namespace harpia_test {

#ifdef _WIN32
// One process-wide WSAStartup/WSACleanup pair, RAII'd via a function-local
// static so it runs exactly once no matter how many Client instances/
// translation units include this header (each generated test is its own
// process, so this is the whole program's socket lifetime).
struct WinsockInit {
    WinsockInit() {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
    }
    ~WinsockInit() { WSACleanup(); }
};
inline void ensure_winsock() { static WinsockInit init; }

inline void close_socket(harpia_sockfd_t fd) { ::closesocket(fd); }
inline int last_error() { return WSAGetLastError(); }
inline void set_nonblocking(harpia_sockfd_t fd, bool nonblocking) {
    u_long mode = nonblocking ? 1 : 0;
    ::ioctlsocket(fd, FIONBIO, &mode);
}
#else
inline void ensure_winsock() {}
inline void close_socket(harpia_sockfd_t fd) { ::close(fd); }
inline int last_error() { return errno; }
inline void set_nonblocking(harpia_sockfd_t fd, bool nonblocking) {
    int flags = ::fcntl(fd, F_GETFL, 0);
    ::fcntl(fd, F_SETFL, nonblocking ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK));
}
#endif

struct Response {
    bool ok = false;   // false on connect/send/recv failure or timeout
    int status = 0;    // parsed HTTP status code
    std::string body;  // response body (after the header block)
    explicit operator bool() const { return ok; }
};

using Headers = std::vector<std::pair<std::string, std::string>>;

class Client {
public:
    Client(std::string host, int port)
        : host_(std::move(host)), port_(port) {}

    void set_default_headers(Headers h) { defaults_ = std::move(h); }
    // 0 = no timeout (block indefinitely). Milliseconds.
    void set_read_timeout_ms(int ms) { read_timeout_ms_ = ms; }
    void set_connection_timeout_ms(int ms) { connect_timeout_ms_ = ms; }

    Response Get(const std::string& path, const Headers& extra = {}) {
        return request("GET", path, "", "", extra);
    }
    Response Post(const std::string& path, const std::string& body,
                  const std::string& content_type, const Headers& extra = {}) {
        return request("POST", path, body, content_type, extra);
    }
    Response Put(const std::string& path, const std::string& body,
                 const std::string& content_type, const Headers& extra = {}) {
        return request("PUT", path, body, content_type, extra);
    }
    Response Delete(const std::string& path, const Headers& extra = {}) {
        return request("DELETE", path, "", "", extra);
    }

    Response request(const std::string& method, const std::string& path,
                     const std::string& body, const std::string& content_type,
                     const Headers& extra) {
        Response r;
        harpia_sockfd_t fd = connect_();
        if (fd == kHarpiaInvalidSocket) return r;

        std::string req = method + " " + path + " HTTP/1.1\r\n";
        req += "Host: " + host_ + ":" + std::to_string(port_) + "\r\n";
        req += "Connection: close\r\n";
        for (const auto& h : defaults_) req += h.first + ": " + h.second + "\r\n";
        for (const auto& h : extra) req += h.first + ": " + h.second + "\r\n";
        if (!content_type.empty())
            req += "Content-Type: " + content_type + "\r\n";
        req += "Content-Length: " + std::to_string(body.size()) + "\r\n";
        req += "\r\n";
        req += body;

        if (!send_all_(fd, req)) { close_socket(fd); return r; }

        std::string raw;
        char buf[4096];
        for (;;) {
            long n = ::recv(fd, buf, sizeof buf, 0);
            if (n > 0) { raw.append(buf, static_cast<size_t>(n)); continue; }
            if (n == 0) break;  // peer closed (Connection: close)
            // n < 0: timeout (EAGAIN/EWOULDBLOCK) or error -> failed request
            close_socket(fd);
            return r;
        }
        close_socket(fd);
        return parse_(raw);
    }

private:
    harpia_sockfd_t connect_() {
        ensure_winsock();
        harpia_sockfd_t fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd == kHarpiaInvalidSocket) return kHarpiaInvalidSocket;

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<uint16_t>(port_));
        if (::inet_pton(AF_INET, host_.c_str(), &addr.sin_addr) != 1) {
            close_socket(fd);
            return kHarpiaInvalidSocket;
        }

        if (connect_timeout_ms_ > 0) {
            set_nonblocking(fd, true);
            int rc = ::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr);
#ifdef _WIN32
            bool in_progress = (rc != 0 && last_error() == WSAEWOULDBLOCK);
#else
            bool in_progress = (rc < 0 && last_error() == EINPROGRESS);
#endif
            if (in_progress) {
                fd_set wf;
                FD_ZERO(&wf);
                FD_SET(fd, &wf);
                timeval tv{connect_timeout_ms_ / 1000,
                           (connect_timeout_ms_ % 1000) * 1000};
                if (::select(static_cast<int>(fd) + 1, nullptr, &wf, nullptr, &tv) <= 0) {
                    close_socket(fd);
                    return kHarpiaInvalidSocket;
                }
                int err = 0;
                harpia_socklen_t len = sizeof err;
                ::getsockopt(fd, SOL_SOCKET, SO_ERROR,
                             reinterpret_cast<char*>(&err), &len);
                if (err != 0) { close_socket(fd); return kHarpiaInvalidSocket; }
            } else if (rc != 0) {
                close_socket(fd);
                return kHarpiaInvalidSocket;
            }
            set_nonblocking(fd, false);
        } else if (::connect(fd, reinterpret_cast<sockaddr*>(&addr),
                             sizeof addr) != 0) {
            close_socket(fd);
            return kHarpiaInvalidSocket;
        }

        if (read_timeout_ms_ > 0) {
#ifdef _WIN32
            DWORD tv = static_cast<DWORD>(read_timeout_ms_);
            ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO,
                         reinterpret_cast<const char*>(&tv), sizeof tv);
#else
            timeval tv{read_timeout_ms_ / 1000,
                       (read_timeout_ms_ % 1000) * 1000};
            ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
#endif
        }
        return fd;
    }

    static bool send_all_(harpia_sockfd_t fd, const std::string& data) {
        size_t sent = 0;
        while (sent < data.size()) {
            long n = ::send(fd, data.data() + sent,
                             static_cast<int>(data.size() - sent), 0);
            if (n <= 0) return false;
            sent += static_cast<size_t>(n);
        }
        return true;
    }

    static Response parse_(const std::string& raw) {
        Response r;
        // status line: "HTTP/1.1 <code> <reason>\r\n"
        size_t sp = raw.find(' ');
        if (sp == std::string::npos) return r;
        r.status = std::atoi(raw.c_str() + sp + 1);
        size_t hdr_end = raw.find("\r\n\r\n");
        if (hdr_end != std::string::npos) r.body = raw.substr(hdr_end + 4);
        r.ok = r.status != 0;
        return r;
    }

    std::string host_;
    int port_;
    Headers defaults_;
    int read_timeout_ms_ = 0;
    int connect_timeout_ms_ = 0;
};

}  // namespace harpia_test

#endif  // HARPIA_TEST_CLIENT_H
