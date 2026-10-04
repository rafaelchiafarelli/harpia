# handheld -- the Java program (JVM CLI + Android app)

One plain-Java core (`core/`, no Android API) with two thin hosts:

- `cli/` -- a JVM `main`. This is what the load harness runs hundreds of.
- `app/` -- a one-screen Android app showing the core's counters.

See `../README.md` for the whole system.

The core:

- subscribes to edge's `live_sample` stream (JeroMQ SUB with CURVE; edge's
  ZAP handler must allowlist this client's key);
- creates one `field_note` on station every `notesEvery` samples;
- lists `reading`s from station every `listEveryMs`.

The gRPC calls go over mTLS (`HarpiaGrpcTls`) with a bearer session
(`HarpiaSession`), from the generated Java runtime.

```sh
# the generated project (HARPIA_GEN_LANG=java, see ../station/README.md) first
(cd build/ms_gen/java && gradle build -x test)

# JVM CLI
cd HarpiaTest/app_example/multi_system/handheld
gradle :cli:installDist -PharpiaGenDir=$PWD/../../../../build/ms_gen
cli/build/install/cli/bin/cli --station station.lan:50051 --certs pki --identity handheld \
    --sub tcp://edge.lan:5556 --zmq-keys zmq --notes-every 5 --list-every 2000 --id-base 500000

# Android app (needs the Android SDK; the PKI folder is bundled as APK assets)
gradle :app:assembleDebug -PwithAndroid -PharpiaGenDir=<gen> -PharpiaPkiDir=<dir>
```

| CLI flag | Default | Meaning |
|---|---|---|
| `--station` | `127.0.0.1:50051` | station's gRPC address |
| `--authority` | the station host | TLS name to verify station's certificate against |
| `--certs` / `--identity` | `.` / `handheld` | `ca.pem` + `client_<identity>.pem` / `_key.pem` (key in PKCS#8, which `mtls_provision.sh` writes) |
| `--sub` | (required) | edge's PUB endpoint |
| `--zmq-keys` | `.` | `zmq_server_public.key` (edge's) + `zmq_<identity>_public.key` / `_secret.key` |
| `--notes-every` | 5 | one field note per N samples |
| `--list-every` | 2000 | ms between reading lists |
| `--id-base` | 1 | first `field_note` primary key (keys are caller-assigned; give each handheld its own range) |
| `--duration` | 0 | stop after S seconds (0 = until Ctrl-C) |

Every 2 s, and once more on exit, the CLI prints:

```
handheld: samples=61 notes=12 readings_listed=175 list_calls=6 errors=0
handheld: done samples=61 notes=12 readings_listed=175 list_calls=6 errors=0
```

The app's `-PharpiaPkiDir` folder holds:

- `ca.pem`, `client_handheld.pem` and `client_handheld_key.pem`;
- `zmq_server_public.key`, `zmq_handheld_public.key` and `zmq_handheld_secret.key`;
- `handheld.properties`, with `station.host`, `station.port`, `station.authority`, `sub.endpoint`, `id.base` and `notes.every`.

It is bundled as APK assets, the equivalent of `res/raw` that keeps the
provisioning scripts' file names.

`field_note` is create-only here: the generated gRPC surface is `push` (create),
`pullByID` (read) and `streamSrc` (list). There is no update RPC.
