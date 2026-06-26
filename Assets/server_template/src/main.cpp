#include <protofiles/address.pb.h>
#include <protofiles/addressbook.grpc.pb.h>

#include <grpc/grpc.h>
#include <grpcpp/server_builder.h>

#include <iostream>

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

