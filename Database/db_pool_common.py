"""Shared path constants for the connection-pool runtime
(multi-system-reference / db-concurrency task 1a).

`harpia_db_pool.h` (harpia::db::PooledSession) is copied verbatim into
`generated/cpp/db/` by every adapter that emits a server able to run over a
::soci::connection_pool -- GrpcServiceAdapter today, the REST/SOAP bring-up in
db-concurrency task 2.
"""
import os

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

DB_POOL_RUNTIME = "harpia_db_pool.h"
DB_POOL_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, DB_POOL_RUNTIME)
