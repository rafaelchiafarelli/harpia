// A downstream project consuming Harpia-generated code as a black box.
//
// This is YOUR application. It never touches the Harpia repo -- it just includes
// the headers from a project you generated with `run_harpia.sh` and links the
// runtime deps (SOCI, protobuf, Crow/asio). It exercises three generated layers
// for the `users` message: the CRUDL DAO, the JSON adapter, and the REST bindings.
//
// Generated headers are qualified by the md5 hash of your `.harpia` input. Here we
// build against the bundled HarpiaTest example, whose hash is the constant below;
// regenerate from your own `.harpia` and the hash (and these include paths /
// accessor names) change with it.
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>   // pick the backend at your session-open site

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

// #define H is only for this demo's readability; the real names are hash-qualified.
#define HASH c96f8fd7f45108efee5a8ecb43eab1da
#include "db/users_c96f8fd7f45108efee5a8ecb43eab1da_crudl.h"    // harpia::db::users_dao
#include "json/users_c96f8fd7f45108efee5a8ecb43eab1da_json.h"   // harpia::json::to_json
#include "rest/users_c96f8fd7f45108efee5a8ecb43eab1da_rest.h"   // harpia::rest::register_users

int main() {
    // 1) Open a database. Your app owns the session; swap the backend header +
    //    factory to target PostgreSQL instead of SQLite -- the code below is
    //    identical either way.
    ::soci::session db(::soci::sqlite3, ":memory:");

    // 2) Use the generated DAO (create_table / create / read / update / remove / list).
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) { std::cerr << "create_table failed\n"; return 1; }

    ::users alice;
    alice.set_id_c96f8fd7f45108efee5a8ecb43eab1da(1);   // ID_<hash> is caller-assigned
    alice.set_name("alice");
    alice.set_address("wonderland");
    ::users bob;
    bob.set_id_c96f8fd7f45108efee5a8ecb43eab1da(2);
    bob.set_name("bob");
    bob.set_address("builder");
    if (!dao.create(alice) || !dao.create(bob)) { std::cerr << "create failed\n"; return 2; }

    std::vector<::users> everyone;
    dao.list(&everyone);
    std::cout << "rows in the table: " << everyone.size() << "\n";
    for (const auto& u : everyone)
        std::cout << "  #" << u.id_c96f8fd7f45108efee5a8ecb43eab1da()
                  << "  " << u.name() << " (" << u.address() << ")\n";

    // 3) Serialize a row with the generated JSON adapter.
    ::users one;
    dao.read(1, &one);
    std::string j;
    ::harpia::json::to_json(one, &j);
    std::cout << "user #1 as JSON: " << j << "\n";

    // 4) Expose the same table over HTTP with the generated REST bindings, on a
    //    Crow app you own. Routes: GET/POST/PUT/DELETE /api/v1/users[/:id],
    //    gated by the credential X-User: users / X-Pswd: <hash>.
    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    harpia::rest::register_users(app, db, "/api/v1");

    // TLS is opt-in at build time (-DUSE_TLS=ON, see CMakeLists.txt) -- it's
    // your server, so it's your call whether to enable it. Crow's ssl_file()
    // is already there in the vendored header; this just points it at a cert.
#ifdef HARPIA_DEMO_TLS
    app.ssl_file(HARPIA_DEMO_CERT, HARPIA_DEMO_KEY);
#endif

    // A real service would just call app.port(8080).run() (blocking). For this
    // self-contained demo we start on an ephemeral port, confirm it, then stop.
    auto fut = app.bindaddr("127.0.0.1").port(0).multithreaded().run_async();
    app.wait_for_server_start();
    std::cout << "REST server started on "
#ifdef HARPIA_DEMO_TLS
              << "https"
#else
              << "http"
#endif
              << "://127.0.0.1:" << app.port() << "/api/v1/users" << std::endl;

    // Optional hold so an external process can connect before we stop --
    // never set outside the TLS test harness, so the plain demo is unaffected.
    // std::endl above already flushed the URL line so a reader waiting on it
    // (rather than on process exit) sees it before this sleep starts.
    if (const char* hold_ms = std::getenv("HARPIA_DEMO_HOLD_MS")) {
        std::this_thread::sleep_for(std::chrono::milliseconds(std::atoi(hold_ms)));
    }
    app.stop();
    fut.get();

    std::cout << "OK\n";
    return 0;
}
