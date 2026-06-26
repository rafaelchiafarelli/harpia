/**
* this example will create a simple CRUD server that listens on port 8080 and redirects the messages to the other CRUD servers
* one server 8080 is the hello world server, the other server 8081 is the stream server, the third server 8082 is the random number generator server
* the client can send a request to the server 8080 with the path /hello, the server will redirect the request to the hello world server and return the response to the client
* the client can send a request to the server 8080 with the path /random, the server will redirect the request to the random number generator server and return the response to the client.
* the client can send a request to the server 8080 with the path /stream, the server will redirect the request to the stream server and return the response to the client (this is a text continuous stream).
 */



#include "httplib.h"
#include <thread>
#include "json.hpp"

#define SERVER_CERT_FILE "./cert.pem"
#define SERVER_PRIVATE_KEY_FILE "./key.pem"

using namespace httplib;
using json = nlohmann::json;

int main(void) {
  // CRUD server
Server CRUD;
Server svr;

svr.WebSocket("/ws", [](const httplib::Request &req, httplib::ws::WebSocket &ws) {
    std::string msg;
    while (ws.read(msg)) {
        std::cout << "Received WebSocket message: " << msg << std::endl;
        ws.send("echo: " + msg);
    }
});

CRUD.Get("/", [=](const Request & /*req*/, Response &res) {
    std::cout<< "Received root" << std::endl;
    res.set_redirect("/test");
  });

CRUD.Get("/test", [](const Request & /*req*/, Response &res) {
  std::cout<< "Received request on /test" << std::endl;
  res.set_content("Test\n", "text/plain");
});

CRUD.Put("/baba", [](const Request & req, Response &res) {
    std::cout<< "Received request on /baba" << std::endl;
    std::string raw_body = req.body;
    std::cout << "Received raw body: " << raw_body << std::endl;
    // 2. Parse using a JSON library
    try {
        auto json_data = nlohmann::json::parse(raw_body);
        std::cout << "Parsed JSON: " << json_data.dump() << std::endl;
        std::string name = json_data.value("name", "unknown");
        res.set_content("Received: " + name, "text/plain");
    } catch (const std::exception& e) {
        res.status = 400; // Bad Request
        res.set_content("Invalid JSON", "text/plain");
    }
});

CRUD.Post("/dada", [](const httplib::Request &req, httplib::Response &res,
                      const httplib::ContentReader &content_reader) {
    std::cout<< "Received request on /dada" << std::endl;
    std::string raw_body;
    for (auto &[key, val] : req.params) {
        raw_body += key + " = " + val + "\n";
    }
    std::cout << "Received raw body: " << raw_body << std::endl;
    // 2. Parse using a JSON library
    try {
        auto json_data = nlohmann::json::parse(raw_body);
        std::cout << "Parsed JSON: " << json_data.dump() << std::endl;
        std::string name = json_data.value("name", "unknown");
        res.set_content("Received: " + name, "text/plain");
    } catch (const std::exception& e) {
        res.status = 400; // Bad Request
        res.set_content("Invalid JSON", "text/plain");
    }
});

CRUD.set_error_handler([](const Request & /*req*/, Response &res) {
  std::cout<< "Received set_error_handler on CRUD server" << std::endl;
  res.set_content("Error " + std::to_string(res.status), "text/plain");
});

CRUD.Get("/stop", [&](const Request & /*req*/, Response & /*res*/) {
  CRUD.stop();
});

// Run servers
auto CRUDThread = std::thread([&]() { CRUD.listen("localhost", 8080); });

auto svrThread = std::thread([&]() { svr.listen("localhost", 8081); });

CRUDThread.join();
svrThread.join();


return 0;
}
