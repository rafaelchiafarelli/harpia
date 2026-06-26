#pragma once

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

class VariableServiceImpl final : public VariableService::Service {
    std::map<std::string, std::string> db;

    Status PushVariable(ServerContext* context, const VariableRequest* request, VariableResponse* reply) override {
        try {
            userFunctions::pushVariable(request->name(), request->value());
        } catch (const std::exception& e) {
            std::cerr << "Error pushing variable: " << e.what() << std::endl;
            reply->set_success(false);
            return Status::ERROR;
        }
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
