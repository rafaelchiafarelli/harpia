
#include "httplib.h"
#include <thread>
#include "json.hpp"
#include "CRUDL_Service_%MESSAGE_NAME%_config.h"

#define SERVER_CERT_FILE "./%MESSAGE_NAME%_cert.pem"
#define SERVER_PRIVATE_KEY_FILE "./%MESSAGE_NAME%_key.pem"

using namespace httplib;
using json = nlohmann::json;

#ifdef CRUDL_SERVICE%MESSAGE_NAME%_ACTIVE
int CRUDL_Service(void) {
    // CRUD server

    
    #ifdef WEBSOCKET_%MESSAGE_NAME%_ACTIVE
    Server svrWS_%MESSAGE_NAME%;

    const std::string msg_root = "%MESSAGE_NAME%";
    svrWS_%MESSAGE_NAME%.WebSocket(msg_root, [](const httplib::Request &req, httplib::ws::WebSocket &ws) {
        std::cout << "WebSocket connection established" << std::endl;
        if (req.has_param("id")) 
        {
            std::string id = req.get_param_value("id");
            try
            {
                
                srvWS_%MESSAGE_NAME%.send(ws%MESSAGE_NAME%.run(id));
            }
            catch(const std::exception& e)
            {
                std::cerr << "WebSocket error at:"<<msg_root<<" e: " << e.what() << std::endl;
            }
        }
        else
        {
            try
            {
                
                srvWS_%MESSAGE_NAME%.send(ws%MESSAGE_NAME%.run());
            }
            catch(const std::exception& e)
            {
                std::cerr << "WebSocket error at:"<<msg_root<<" e: " << e.what() << std::endl;
            }
        }
    });
    #endif
    #ifdef CRUD_%MESSAGE_NAME%_ACTIVE
    Server CRUD_%MESSAGE_NAME%;
    const std::string crud_root = "Get_%MESSAGE_NAME%";
    CRUD_%MESSAGE_NAME%.Get(crud_root, [=](const Request & req, Response &res) {
        std::cout<< "Received request on " << crud_root << std::endl;
        if (req.has_param("id")) 
        {
            std::string id = req.get_param_value("id");
            try 
            {
                std::string crud_result = CRUD_%MESSAGE_NAME%.Get(id);
                res.set_content(crud_result, "text/plain");
            }
            catch(const std::exception& e)
            {
                std::cerr << "Error handling GET request at:"<<crud_root<<" e: " << e.what() << std::endl;
                res.status = 500; // Internal Server Error
                res.set_content("Internal Server Error", "text/plain");
            }  
        }
        else 
        {
            try 
            {
                std::string crud_result = CRUD_%MESSAGE_NAME%.Get();
                res.set_content(crud_result, "text/plain");
            }
            catch(const std::exception& e)
            {
                std::cerr << "Error handling GET request at:"<<crud_root<<" e: " << e.what() << std::endl;
                res.status = 500; // Internal Server Error
                res.set_content("Internal Server Error", "text/plain");
            }  
        }
    });

    const std::string put_root = "Put_%MESSAGE_NAME%";
    CRUD_%MESSAGE_NAME%.Put(put_root, [](const Request & req, Response &res) {
        std::cout<< "Received request on " << put_root << std::endl;
        std::string raw_body = req.body;
        std::cout << "Received raw body: " << raw_body << std::endl;
        // 2. Parse using a JSON library
        try 
        {
            auto json_data = nlohmann::json::parse(raw_body);
            std::cout << "Parsed JSON: " << json_data.dump() << std::endl;
            try
            {
                std::string res = CRUD_%MESSAGE_NAME%.Put(json_data);
                res.set_content(res, "text/plain");
            }
            catch(const std::exception& e)
            {
                std::cerr << "Error handling PUT request at:"<<put_root<<" e: " << e.what() << std::endl;
                res.status = 500; // Internal Server Error
                res.set_content("Internal Server Error", "text/plain");
            }
            
            res.set_content(res, "text/plain");
        } 
        catch (const std::exception& e) 
        {
            std::cerr << "Error handling parse request at:"<<put_root<<" e: " << e.what() << std::endl;
            res.status = 400; // Bad Request
            res.set_content("Invalid JSON", "text/plain");
        }
    });

    const std::string post_root = "Post_%MESSAGE_NAME%";
    CRUD_%MESSAGE_NAME%.Post(post_root, [](const httplib::Request &req, httplib::Response &res,
                                        const httplib::ContentReader &content_reader) {
        std::cout<< "Received request on " << post_root << std::endl;
        std::string raw_body;
        for (auto &[key, val] : req.params) {
            raw_body += key + " = " + val + "\n";
        }
        std::cout << "Received raw body: " << raw_body << std::endl;
        // 2. Parse using a JSON library
        try {
            auto json_data = nlohmann::json::parse(raw_body);
            std::cout << "Parsed JSON: " << json_data.dump() << std::endl;
                try{
                std::string res = CRUD_%MESSAGE_NAME%.Post(json_data);
                res.set_content(res, "text/plain");
                }
                catch(const std::exception& e){
                    std::cerr << "Error handling POST request at:"<<post_root<<" e: " << e.what() << std::endl;
                    res.status = 500; // Internal Server Error
                    res.set_content("Internal Server Error", "text/plain");
                }

        } catch (const std::exception& e) {
            std::cerr << "Error handling POST request at:"<<post_root<<" e: " << e.what() << std::endl;
            res.status = 400; // Bad Request
            res.set_content("Invalid JSON", "text/plain");
        }
    });

    CRUD_%MESSAGE_NAME%.set_error_handler([](const Request & /*req*/, Response &res) {
        std::cout<< "Received set_error_handler on CRUD server" << std::endl;
        res.set_content("Error " + std::to_string(res.status), "text/plain");
    });

    const std::string stop_root = "Stop_%MESSAGE_NAME%";
    CRUD_%MESSAGE_NAME%.Get(stop_root, [&](const Request & /*req*/, Response & /*res*/) {
        CRUD_%MESSAGE_NAME%.stop();
    });
    
    // Run servers
    auto CRUDThread = std::thread([&]() { CRUD_%MESSAGE_NAME%.listen("localhost", 8080); });
    #endif
    #ifdef WEBSOCKET_%MESSAGE_NAME%_ACTIVE
    auto svrThread = std::thread([&]() { svrWS_%MESSAGE_NAME%.listen("localhost", 8081); });
    #endif
    #ifdef CRUD_%MESSAGE_NAME%_ACTIVE
    CRUDThread.join();
    #endif
    #ifdef WEBSOCKET_%MESSAGE_NAME%_ACTIVE
    svrThread.join();
    #endif

    return 0;
}
#endif
