0. pre-process check (pre_lex)
    0. 0. check for non-utf8 characters
    0. 0. 1. open file and read all its contents
    0. 0. 2. check each characters for non-utf8 characters (simple regex)
    0. 0. 3. create destination folder
    0. 0. 4. check for inconsistent terminators ( parentesis, comments, brackets, etc)
    0. 0. 5. check for harpia imports in folder, proto imports are handled diferently
    0. 0. 6. create md5hash for the file

1. tokenize harpia file (LexicalAnalyzer)
    1. 0. tokenization is the transformation of every "word" into one token. 
        1. 0. 1. tokenize line-by-line
    1. 1. check for inconsistencies in indexes (indexes >=1)
        1. 1. 1. get all the tokens that are inside messages, after the equal sign and before the ";" token.
        1. 1. 2. non-numeric elements will generate an error.
        1. 1. 3. if a number of indexes is 0 or less then 0, it will generate an error.
        1. 1. 4. all hapia files included must be present in the include folders 
        1. 1. 5. all import lines must end with semi-colomn (;)
    1. 2. remove all comments -- token navigation
        1. 2. 0. remove the tokens from the list
        1. 2. 1. comments starting with double slash will comment the rest of the line
        1. 2. 3. comments starting with slash asterix will finish when a asterix slash is found
    1. 3. separate each message into one separated tmp file (MessageCreator)
        1. 3. 0. messages start after the "message" word until it reaches the closing brackets
            1. 3. 0. 1. messages without name are not allowed
            1. 3. 0. 2. messages without opening brackets are not allowed
            1. 3. 0. 3. messages with sub-messages are allowed
            1. 3. 0. 3. 1. sub-messages that are databases, have a mandatory UNIQUE foreyn_key (one-key per line in database). Sub-messages without database will only be accessed by messages containing it.
            1. 3. 0. 3. 2. sub-messages can be either public or private, but will have a table if the message containing it have a table. If name is not provided, but a table name is present at the containin message, then the sub-message will have a "hash" as a name
            1. 3. 0. 3. 3. sub-messages CANNOT have modifiers (pull, push, event, etc)
                        4. sub-messages can have variables as messages
            1. 3. 0. 4. if message names are "status", "version", "error", the hidden message names will be changed to h_<message_name>
            1. 3. 0. 5. no two messages with equal names are allowed
            1. 3. 0. 6. messages with variable containing itself is not allowed
            1. 3. 0. 7. messages containing messages of other files are allowed, but files must be included
            1. 3. 0. 8. messages containing messages of the same file are allowed, This sub-message will have a NON-UNIQUE forein_key.
            1. 3. 0. 8. 1. If message is contained by others, than it will have a NON-UNIQUE forein-key per inclusion in other messages
            1. 3. 0. 9. sub-messages described inside a message can-not be included in other messages
            1. 3. 0. 10. events of messages internal to other messages can have cascade effect events (change in an internal message can have effect on containing message if the message has the event modifier)
        1. 3. 1. insert the hidden elements (FileCreator):
            1. 3. 1. 1. hidden elements are inserted in the token tree
                1. 3. 1. 1. equal names for hidden variables and/or messages are not allowed
                1. 3. 1. 1. change the name of the hidden element to h_###, where ### is the number formed by the md5 of the file this message resides in.
            1. 3. 1. 1. message originator (unique number related to the sender)
                1. 3. 1. 1. 0. only one method of message originator will be allowed per message.
                1. 3. 1. 1. 1. if the publisher is unique (one-to-many or one-to-one), then this is a compilation problem and not a runtime problem 
                    1. 3. 1. 1. 1. 1. create the number via the hash of the project, and the hash of the generated file.
                    1. 3. 1. 1. 1. 2. the number is used when the sender will register itself into the zmq/socket application
                    1. 3. 1. 1. 1. 3. only one application is available with that unique number. 
                1. 3. 1. 1. 0. if the publisher is many-to-many or many-to-one, then sender unique number is given in runtime.
                    1. 3. 1. 1. 0. 1. unique number is created in time of setup of the sender function, either in zmq or in socket. This means this is a runtime problem, not a compilation problem.
                    1. 3. 1. 1. 0. 2. when the application furst opens the socket and or register itself as a publisher, it receives a unique number from the zmq/socket module
            
        1. 3. 2. insert the ???
    1. 4. create an order of process (if one message uses elements from another )
    1. 5. check for foreing-key existance (variable name as a message type)

2. generate flags for other processes (FileCreator)
    2. 1. flags for access-generators
        2. 1. 1. access-modifier
        2. 1. 2. table names and properties (public private)
        2. 1. 3. 
    2. 2. flags for regex and indexes 
        2. 2. 1. flag for regex: each variable contais a regex
        2. 2. 1. 1. if the regex is not present, the type must generate a regex 
        2. 2. 1. 1. 1. for instance: int a = 2; will have a regex allowing a number of 32 bits with one bit per signal.
        2. 2. 1. 1. 2. for undefined types, such as other messages, the regex is constructed as a simple string.
        2. 2. 2. if the regex is present in the type, a regex checker must exist. 
        2. 2. 2. 1. this is not going to be implemented now but the idea is we have a way to check if a regex is fit to the type we are dealing with.        
        2. 2. 3. 
    2. 3. flags for access types in variables
        2. 3. 1. repeateable flags - will be used to check if can be repeateable
            2. 3. 1. 1. the repeateable can be a constant (memory bound) or no limit (dynamic memory bound)
        2. 3. 2. pagination flags
        2. 3. 3. optional
        2. 3. 4. required
        2. 3. 5. unique

4. check flags for inconsistencies 
    3. 1. a repeateable flag without delimitation and no table name will be created as vector or list.
    3. 2. a option flag cannot exist with a required flag
    3. 3. a required flag can exist with a unique flag
    3. 4. a optional flag can exist with a unique flag
    .
    .
    .

5. check access rights and create passwords (FileCreator)
    4. 1. encrypted passwords be created. They are related to the tokenization result (unchanged by comments)
    4. 1. 1. e
    4. 2. encrypted passwords must be added to the flags of CRUDL
    4. 3.  encrypted passwords must be added to the SOAP access tool

6. create the clean proto file
    5. 1. add all messages into one or as many files as needed to conform with the version of protobuf we are using

7. execute protobuf compiler
    6. 1. this will generate all the access functions from the protobuf

8. create the database accesses
    7. 1. with the data from the tokens and the data from protobuf (functions names, namespaces, etc)
    7. 2. create the validation function for versions
        7. 2. 1. create the "transformative" functions from one version to another. 
        7. 2. 2. create the read functions
        7. 2. 3. create the write functions
        7. 2. 4. create all the creation and deletion functions (drop database etc)
        7. 2. 5. create the final sql-schema file (with all the elements pertinent)

9. create the json addapter
    8. 1. function to generate the json and json-checker
    8. 2. function to generate a message from a json
    8. 3. function to update the database from a json
    8. 4. function to update the json from the database
    8. 5. function to export to json from database
    8. 6. function to import to database from json

10. create the xml addapter
    9. 1. function to generate the xml and the xsd
    9. 2. function to generate a message from a xml
    9. 3. function to update the database from a xml
    9. 4. function to update the json xml the database
    9. 5. function to export to xml from database
    9. 6. function to import to database from xml
11. create the SOAP access
    10. 1. create the xml access tool knonwn as SOAP

12. create the HTML bindings
    11. 1. RESTFull API for json
    11. 2. RESTFull API for xml
    11. 3. RESTFull API for SOAP

13. create the zmq/socket access functions
    12. 1. create the push/pull functions
    12. 2. create the streamming functions
    12. 3. create the gRPC access functions 

14. create the unit tests
    13. 1. test simple access
    13. 2. test database
    13. 3. test access rights
    13. 4. test access modifiers
    13. 5. test json parser
    13. 6. test xml parser
    13. 7. test html RESTFull API
    13. 8. test SOAP API - HTML
    13. 9. test xml API - HTML
    13. 10. test json API - HTML
    13. 11. create/test the "all-good" application tests
    13. 12. create/test the "crash" applications
    13. 13. create/test the "slower" applications
    13. 14. create/test the non-parseable functions
