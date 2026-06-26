there is one http file per message
C    R    U     D       L
Put, Get, Post, Delete, Connect (WebSocket)
every message will have:
    * one endpoint get/put/post/delete/connect per message
    * one endpoint get/put/post/delete/connect per ID

every endpoint type (get/put/post/delete/connect) will be implemented and surrounded by a "#ifdef" statement to disable or enable it.

https will have the key-file generated with the password and user defined in the file. 
https will have the same access function and will also be surrounded by a "#ifdef" statement.





