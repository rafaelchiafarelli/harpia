#include <iostream>
#include <memory>
#include <string>
#include <map>

#include <grpcpp/grpcpp.h>
#include "variables.grpc.pb.h"

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using varsync::VariableService;
using varsync::VariableRequest;
using varsync::VariableQuery;
using varsync::VariableResponse;


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
