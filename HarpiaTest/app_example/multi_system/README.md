# Multi-system reference: Windows DB server + Linux C++ + Android Java

Three programs, in two languages, on three operating systems, generated from
**one** `.harpia` schema and talking to each other over **hardened**
transports:

| Program | Language / OS | Role | Folder |
|---|---|---|---|
| `station` | C++, **Windows** (also Linux) | The only database owner (PostgreSQL or a SQLite file). Serves the generated gRPC services: mTLS required, RBAC, bearer sessions, a connection pool. | [`station/`](station/README.md) |
| `edge` | C++, **Linux**, no database | Creates a `reading` on station every interval and publishes a `live_sample` per reading on a CURVE ZMQ PUB (ZAP allowlist). Lists station's field notes. | [`edge/`](edge/README.md) |
| `handheld` | Java, **Android** (and a JVM CLI) | Subscribes to edge's stream, writes a `field_note` to station every N samples, lists station's readings. | [`handheld/`](handheld/README.md) |

The schema, the compliance profile and the identity list live in
[`harpia/`](harpia/).

## Topology

```
                      gRPC :50051 (mTLS + RBAC + bearer session)
        +-------------------------------------------------------------+
        |                                                             |
        v                                                             |
+----------------+    gRPC :50051     +----------------+              |
|    station     |<-------------------|      edge      |              |
|  Windows, C++  |  create reading,   |   Linux, C++   |              |
|  PostgreSQL    |  list field_note   |  (no database) |              |
+----------------+                    +----------------+              |
        ^                                     | ZMQ PUB :5556         |
        |                                     | CURVE + ZAP allowlist |
        |                                     v                       |
        |                             +----------------+              |
        +-----------------------------|    handheld    |--------------+
           create field_note,         | Android, Java  |
           list reading               +----------------+
```

| Message | Written by | Read by | Transport |
|---|---|---|---|
| `reading` | edge (create) | station stores; handheld lists | gRPC |
| `field_note` | handheld (create) | station stores; edge lists | gRPC |
| `live_sample` | edge (publish) | handheld (subscribe); never stored | ZMQ PUB/SUB, CURVE |

## Identities and roles

`harpia/clients.txt` is the single identity list. Both provisioning scripts
read it.

| Identity | Certificate CN | RBAC role | CURVE key allowlisted by edge | Used by |
|---|---|---|---|---|
| `edge` | `edge` | `main` (create/read/update/list) | yes | edge |
| `handheld` | `handheld` | `main` | yes | handheld (CLI and app) |
| `guest` | `guest` | `guest` (read/list only) | yes | nobody; it exists to prove a denied create |
| (server) | `station`'s server cert | n/a | n/a | station; edge is the CURVE *server* for the stream |

Roles come from `rbac_map.txt` (`HARPIA_RBAC_MAP`) on station. A client gets
a bearer token from `heartBeat` with `harpia-issue-session` metadata and
presents it on every call. More identities (e.g. one per device for the load
harness) are just more lines in a copy of `clients.txt`.

## Ports and firewall

| Host | Port | Direction | Purpose |
|---|---|---|---|
| station | 50051/tcp | inbound from edge + every handheld | gRPC (TLS 1.2+/1.3, client cert required) |
| edge | 5556/tcp | inbound from every handheld | ZMQ PUB (CURVE) |
| station | DB port (5432/tcp) | local only, unless PostgreSQL runs elsewhere | PostgreSQL |

On Windows:

```powershell
New-NetFirewallRule -DisplayName "harpia station" -Direction Inbound -Protocol TCP -LocalPort 50051 -Action Allow
```

On Linux (edge):

```sh
sudo ufw allow 5556/tcp
```

## 1. Generate (once, on a machine with Docker)

From the harpia repository:

```sh
Docker/run.sh env HARPIA_DB_BACKEND=postgresql HARPIA_GEN_LANG=java \
    HARPIA_INPUT_FILE=HarpiaTest/app_example/multi_system/harpia/multi_system.harpia \
    HARPIA_INCLUDE_FOLDER=HarpiaTest/app_example/multi_system/harpia/Include \
    HARPIA_COMPLIANCE_CONFIG=HarpiaTest/app_example/multi_system/harpia/project.harpia.yaml \
    HARPIA_OUTPUT_DIR=build/ms_gen python3 main.py
```

- **Database:** `HARPIA_DB_BACKEND` must match station's database. Use
  `postgresql`, or leave it out for SQLite. The migrations are dialect-specific,
  and station refuses a `--db` of the other dialect.
- **Languages:** `HARPIA_GEN_LANG=java` emits the Java side next to the C++.
- **Output:** copy `build/ms_gen` to every build machine. It is self-contained.

## 2. Provision the PKI (once)

```sh
sh Assets/cmake/mtls_provision.sh pki station.lan \
   --san 192.168.1.50 --san station.lan \
   --clients-file HarpiaTest/app_example/multi_system/harpia/clients.txt
sh Assets/cmake/zmq_zap_provision.sh zmq \
   --clients-file HarpiaTest/app_example/multi_system/harpia/clients.txt
```

- Replace `station.lan` / `192.168.1.50` with the name and address station
  is reached by.
- Add `--san 10.0.2.2` for the Android emulator. Every name or address a
  client dials must be in the server certificate.
- Re-running the scripts keeps the CA and every existing identity, and only
  issues new ones.

**Copy to each machine.** Only what it needs; never copy `ca_key.pem` off the
provisioning machine.

| Machine | Files |
|---|---|
| station (Windows) | `pki/ca.pem`, `pki/server.pem`, `pki/server_key.pem`, `pki/rbac_map.txt` |
| edge (Linux) | `pki/ca.pem`, `pki/client_edge.pem`, `pki/client_edge_key.pem`, `zmq/zmq_server_secret.key`, `zmq/allowlist.txt` |
| handheld (Android) | `pki/ca.pem`, `pki/client_handheld.pem`, `pki/client_handheld_key.pem`, `zmq/zmq_server_public.key`, `zmq/zmq_handheld_public.key`, `zmq/zmq_handheld_secret.key` (bundled into the APK, see step 5) |

## 3. station on Windows

Prerequisites: Visual Studio 2022 (C++), CMake 3.16+, vcpkg
(`VCPKG_ROOT` set), PostgreSQL 14+ with a database and user for station.

```powershell
cmake -S HarpiaTest\app_example\multi_system\station -B build\station `
      -DHARPIA_GEN=C:\path\to\ms_gen `
      -DCMAKE_TOOLCHAIN_FILE=$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake
cmake --build build\station --config Release
$env:HARPIA_RBAC_MAP = "C:\harpia\pki\rbac_map.txt"
$env:HARPIA_SESSION_KEY = "<a long random secret>"
build\station\Release\station.exe --listen 0.0.0.0:50051 `
    --db "host=127.0.0.1 dbname=ms user=ms password=..." --pool 16 --certs C:\harpia\pki
```

Expected output:

```
station: listening on 0.0.0.0:50051 (mTLS required, pool 16, postgresql)
station: last 10s calls=118 sessions=2 errors=0 (total calls=118 errors=0)
```

Ctrl-C shuts it down cleanly. See [`station/README.md`](station/README.md)
for every flag and the Windows-specific code.

## 4. edge on Linux

Prerequisites (Ubuntu 24.04):

```sh
sudo apt install cmake g++ libprotobuf-dev protobuf-compiler libgrpc++-dev libzmq3-dev cppzmq-dev
```

```sh
cmake -S HarpiaTest/app_example/multi_system/edge -B build/edge -DHARPIA_GEN=$HOME/ms_gen
cmake --build build/edge
HARPIA_ZMQ_ALLOWLIST=$HOME/harpia/zmq/allowlist.txt \
  build/edge/edge --station station.lan:50051 --certs $HOME/harpia/pki --identity edge \
                  --pub tcp://*:5556 --zmq-keys $HOME/harpia/zmq --device edge-1
```

Expected output:

```
edge: edge -> station station.lan:50051, publishing on tcp://*:5556
edge: field_notes on station: 4
...
```

## 5. handheld on an Android device

On the build machine (JDK 17, Gradle 8.5, Android SDK 34):

```sh
(cd ~/ms_gen/java && gradle build -x test)          # the generated jar
mkdir handheld_assets && cp pki/ca.pem pki/client_handheld*.pem \
    zmq/zmq_server_public.key zmq/zmq_handheld_*.key handheld_assets/
cat > handheld_assets/handheld.properties <<EOF
station.host=192.168.1.50
station.port=50051
sub.endpoint=tcp://192.168.1.60:5556
id.base=500000
notes.every=5
EOF
cd HarpiaTest/app_example/multi_system/handheld
gradle :app:assembleDebug -PwithAndroid -PharpiaGenDir=$HOME/ms_gen -PharpiaPkiDir=$PWD/../../../../handheld_assets
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The `handheld.properties` values:

- `station.host` is station's address, which must be in the server cert's SAN.
- `sub.endpoint` is edge's address.
- Add `station.authority=<name>` only if you dial an address that isn't in
  the SAN.

The screen shows the counters, which also go to logcat (`adb logcat -s harpia-handheld`):

```
samples received: 61
notes written: 12
readings listed: 175
errors: 0
```

Without a device, run the same core as a JVM CLI
([`handheld/README.md`](handheld/README.md)):

```
handheld: done samples=61 notes=12 readings_listed=175 list_calls=6 errors=0
```

## Primary keys

Primary keys are caller-assigned (`int32`), so every writer uses its own
range: edge `--id-base`, handheld `--id-base` / `id.base`. Two writers with
overlapping ranges get `create failed` on the colliding ids. The load harness
gives each spawned client its own range.

## Load mode

edge and handheld (CLI or app) also run as one load client each. A load client
is one identity, with its own cert, CURVE key and session, so N processes are
N distinct clients to station:

```sh
build/edge/edge --load --identity edge-load --rate 20 --duration 60 --mix 8:1:1 \
    --report edge-load.jsonl --id-base 300000 --station station.lan:50051 --certs $HOME/harpia/pki
handheld/cli/build/install/cli/bin/cli --load --identity handheld-load --rate 20 --duration 60 \
    --mix 8:1:1 --report hh-load.jsonl --id-base 700000 --station station.lan:50051 \
    --certs $HOME/harpia/pki [--sub tcp://edge.lan:5556 --zmq-keys $HOME/harpia/zmq]
adb shell am start -n com.harpia.multisystem.handheld.app/.MainActivity \
    --ez load true --ef load.rate 5 --ei load.duration 60 --es load.mix 8:1:1
```

`--mix` is the `create:list:read` weights. The generated gRPC surface is
push / streamSrc / pullByID, so there is no update operation, and the third
weight reads back one of the client's own records. Each operation appends one
JSON line to `--report` (the app writes `files/load.jsonl`):

```
{"t":1759600000.123,"client_kind":"edge","identity":"edge-load","op":"create","ok":true,"grpc_code":"OK","latency_us":812}
```

`op` is `session`, `create`, `list` or `read`. A subscribed handheld also logs
each received sample as `{"t",...,"op":"sub_recv","seq_gap":N}`, where
`seq_gap` counts the samples it missed from that device, so drops are visible.
Load identities need rows in the clients file (e.g. `edge-load main`).

## Proven where

- `UnitTests/test_multi_system_example.py`, part of the full Docker suite. It
  runs station (SQLite; PostgreSQL via `Docker/run_pg_tests.sh`), edge and
  two handheld CLIs at once, asserts every flow, and runs the negatives:
  guest is denied create, and a non-allowlisted CURVE key receives nothing.
- `Docker/run_android_emulator_tests.sh multi_system` runs the real Android
  app in place of one CLI, reaching station and edge as `10.0.2.2`.
- On real Windows + Linux + an Android device: the Windows verification
  session (`Initiatives/multi-system-reference/epics/windows-verification/`).
