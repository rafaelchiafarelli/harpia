#include <protofiles/address.pb.h>
#include <protofiles/addressbook.grpc.pb.h>

#include <grpc/grpc.h>
#include <grpcpp/create_channel.h>

#include <iostream>
/**
 * This is the client template for the gRPC server. The idea is to have a simple client that can be used to test all messages in the proto files.
 * It is not meant to be a full-featured client, but rather a simple example of how to use the generated code from the proto files.
 * The client will call the Getters and Setters of the messages, also will call the functions available in the messages.
 * 
 */

int main(int argc, char* argv[])
{
    // Setup request
    expcmake::NameQuerry query;
    expcmake::StreetQuerry streetQuery;
    expcmake::Address result;
    expcmake::Address streetResult;
    query.set_name("John");
    streetQuery.set_street("Main Street");
    // Call
    auto channel = grpc::CreateChannel("localhost:50051", grpc::InsecureChannelCredentials());
    std::unique_ptr<expcmake::AddressBook::Stub> stub = expcmake::AddressBook::NewStub(channel);
    grpc::ClientContext context;
    grpc::Status status = stub->GetAddress(&context, query, &result);

    // Output result
    std::cout << "I got:" << std::endl;
    std::cout << "Name: " << result.name() << std::endl;
    std::cout << "City: " << result.city() << std::endl;
    std::cout << "Zip:  " << result.zip() << std::endl;
    std::cout << "Street: " << result.street() << std::endl;
    std::cout << "Country: " << result.country() << std::endl;

    grpc::ClientContext streetContext;
    grpc::Status streetStatus = stub->GetAddressByStreet(&streetContext, streetQuery, &streetResult);
    // Output result
    std::cout << "I got, for streetResult:" << std::endl;
    std::cout << "Name: " << streetResult.name() << std::endl;
    std::cout << "City: " << streetResult.city() << std::endl;
    std::cout << "Zip:  " << streetResult.zip() << std::endl;
    std::cout << "Street: " << streetResult.street() << std::endl;
    std::cout << "Country: " << streetResult.country() << std::endl;

    return 0;
}
