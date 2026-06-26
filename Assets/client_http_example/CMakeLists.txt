cmake_minimum_required(VERSION 3.10)
project(SimpleHTTPClient)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)

# Find threading library (required by httplib)
find_package(Threads REQUIRED)

# Add the executable
add_executable(MyClient main.cpp)

target_include_directories(MyClient 
    PUBLIC  ../external_libs/         # Folders needed by this target AND its dependents
    PRIVATE client_http_template/             # Folders needed only for building this target
    INTERFACE ../extras/         # Folders needed ONLY by dependents
)

# Link threads
target_link_libraries(MyClient PRIVATE Threads::Threads)