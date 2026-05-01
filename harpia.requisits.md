# This is a specification file for the external interfaces.
## gRPC 
* one function to pull by ID
* one function to push
* one function per variable to update by id.
* one function per variable and ID

## ORM ???


## RESTFull (json)
* every message will have:
    * one endpoint per message per type 
        - Put a message 
        - Post a message or messages
        - Delete a item or a set of items
        - Get one message by id
    * one endpoint per variable of type Get, Put and Post
        - Get will return a set of elements with the variable type or a unique element if it is defined as UNIQUE
        - Post will return the result of a function call 
        - Put will return the result of a function call 

    
## WebSocket (stream)
* every message will have one.
    * json formatted string
    * binary unformatted data
    
## SOAP
- create a set of messages
- make the SOAP to access these messages and the services within the messages

## CRUDL
- implement the CRUDL (Create, Read, Update, Delete, List) access (database and memory)

## multi-project
- create two projects from 2 harpia files
- make them exchange information between them (one is the server of its set of variables and the client of the other set of variables)

## multi-language
- make it in c++ and java

## multi-thread 
- make a project that have mutliple speakers and multiple listeners



## The pourpose

- the pourpose of this project is to be a seed for future implementations



