


#include "httplib.h"
#include <thread>
#include "json.hpp"

#define SERVER_CERT_FILE "./cert.pem"
#define SERVER_PRIVATE_KEY_FILE "./key.pem"

using namespace httplib;
using json = nlohmann::json;

int main(void) {
  // HTTP server

httplib::ws::WebSocketClient httpWS("ws://localhost:8081/ws");

if (httpWS.connect()) {
    httpWS.send("hello there.");

    std::string msg;
    int msg_counter = 0;
    while (httpWS.read(msg) && msg_counter++ < 500) {
        httpWS.send("hello there.");
        std::cout << msg << std::endl;  // "echo: hello"
    }
    httpWS.close();
}
  return 0;
}
