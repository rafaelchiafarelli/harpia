// harpia_test_client.h -- minimal blocking HTTP/1.1 loopback client for the
// generated live-HTTP tests. Replaces cpp-httplib's ::httplib::Client on the
// test side of the cpp-httplib -> Crow migration; Crow ships no client.
//
// Header-only, POSIX sockets only (no asio, no extra vendored dep) so it stays
// trivially portable across the target boards. Speaks just enough HTTP/1.1 to
// drive the CRUDL/SOAP endpoints: one request per connection with
// "Connection: close", response read to EOF, status line + body parsed out.
// Read/connect timeouts (used by the "slower server" test) map to setsockopt
// SO_RCVTIMEO and a non-blocking connect + select.
#ifndef HARPIA_TEST_CLIENT_H
#define HARPIA_TEST_CLIENT_H

#include <string>
#include <utility>
#include <vector>

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

namespace harpia_test {

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
        int fd = connect_();
        if (fd < 0) return r;

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

        if (!send_all_(fd, req)) { ::close(fd); return r; }

        std::string raw;
        char buf[4096];
        for (;;) {
            ssize_t n = ::recv(fd, buf, sizeof buf, 0);
            if (n > 0) { raw.append(buf, static_cast<size_t>(n)); continue; }
            if (n == 0) break;  // peer closed (Connection: close)
            // n < 0: timeout (EAGAIN/EWOULDBLOCK) or error -> failed request
            ::close(fd);
            return r;
        }
        ::close(fd);
        return parse_(raw);
    }

private:
    int connect_() {
        int fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return -1;

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<uint16_t>(port_));
        if (::inet_pton(AF_INET, host_.c_str(), &addr.sin_addr) != 1) {
            ::close(fd);
            return -1;
        }

        if (connect_timeout_ms_ > 0) {
            int flags = ::fcntl(fd, F_GETFL, 0);
            ::fcntl(fd, F_SETFL, flags | O_NONBLOCK);
            int rc = ::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr);
            if (rc < 0 && errno == EINPROGRESS) {
                fd_set wf;
                FD_ZERO(&wf);
                FD_SET(fd, &wf);
                timeval tv{connect_timeout_ms_ / 1000,
                           (connect_timeout_ms_ % 1000) * 1000};
                if (::select(fd + 1, nullptr, &wf, nullptr, &tv) <= 0) {
                    ::close(fd);
                    return -1;
                }
                int err = 0;
                socklen_t len = sizeof err;
                ::getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len);
                if (err != 0) { ::close(fd); return -1; }
            } else if (rc < 0) {
                ::close(fd);
                return -1;
            }
            ::fcntl(fd, F_SETFL, flags);  // back to blocking
        } else if (::connect(fd, reinterpret_cast<sockaddr*>(&addr),
                             sizeof addr) < 0) {
            ::close(fd);
            return -1;
        }

        if (read_timeout_ms_ > 0) {
            timeval tv{read_timeout_ms_ / 1000,
                       (read_timeout_ms_ % 1000) * 1000};
            ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        }
        return fd;
    }

    static bool send_all_(int fd, const std::string& data) {
        size_t sent = 0;
        while (sent < data.size()) {
            ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, 0);
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
