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

/**
* Implementation of the server side.
* - push, pull and pushpull functions are implemented here.
* - The server maintains an in-memory database (std::map) to store variable names and their corresponding values.
* - The PushVariable function allows clients to push a variable name and value to.
* 
*/
