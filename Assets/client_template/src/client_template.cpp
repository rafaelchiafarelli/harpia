#include <iostream>
#include <memory>
#include <string>
#include <map>

#include <grpcpp/grpcpp.h>


using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;


class VariableServiceImpl final : public VariableService::Service {
    std::map<std::string, std::string> db;

    Status PushVariable(ServerContext* context, const VariableRequest* request, VariableResponse* reply) override {
        db[request->name()] = request->value();
        std::cout << "Push: " << request->name() << " = " << request->value() << std::endl;
        reply->set_name(request->name());
        reply->set_value(request->value());
        reply->set_success(true);
        return Status::OK;
    }

    Status PullVariable(ServerContext* context, const VariableQuery* request, VariableResponse* reply) override {
        auto it = db.find(request->name());
        reply->set_name(request->name());
        if (it != db.end()) {
            reply->set_value(it->second);
            reply->set_success(true);
        } else {
            reply->set_success(false);
        }
        return Status::OK;
    }
};

void RunServer() {
    std::string server_address("0.0.0.0:50051");
    VariableServiceImpl service;

    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "Servidor rodando em " << server_address << std::endl;
    server->Wait();
}

int main() {
    RunServer();
    return 0;
}
